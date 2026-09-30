-- Timeline-driven Flycast harness (Dreamcast reference runs), the counterpart of tools/mame/timeline.lua.
-- GB2_TIMELINE = path of a text file with lines "<vblank> <command> [args]":
--   press <btn...> / release <btn...> / tap <n> <btn...>   buttons: A B X Y Start Up Down Left Right (player 1)
--   snap <file.png>            screenshot (flycast.emulator.screenshot, patched build tools/local/flycast-src)
--   poke8/poke16/poke32 <addr> <value> (hex)   peek <addr> <n>   dumpmem <addr> <len> <file> (hex addr/len)
--   trace <file> <player x> <player hit ptr> <hit objs> <hit list> <hit count>   per-frame trace (trace_frame)
--   until <addr> <lo> <hi>     pause the timeline (later frames shift) until the u16 at addr is in [lo, hi] (hex)
--   timer <addr> <lo> <hi>     as until, but the u16 must also count down by 1 per frame for 5 frames (a live
--                              countdown, e.g. the select timer on the stack, not stale stack contents)
--   sndlog <file>              log sound-effect plays of the DC effect player 0x8C01BCE0: its 8 slots hold the last
--                              id (u16 0x8C16D3A0 + 2 * slot) and a timer set to 10 on every play (u8 0x8C16D27C + slot);
--                              a new id or a rising timer is a play: "<frame> <slot> <id hex>"
--   exit
local BTN = { A = 0x4, B = 0x2, X = 0x400, Y = 0x200, Start = 0x8, Up = 0x10, Down = 0x20, Left = 0x40, Right = 0x80 }
local mem, inp = flycast.memory, flycast.input
local events, idx, frame = {}, 1, 0
for line in io.lines(os.getenv("GB2_TIMELINE")) do
  local f, rest = line:match("^%s*(%d+)%s+(.+)$")
  if f then events[#events + 1] = { frame = tonumber(f), cmd = rest } end
end
table.sort(events, function(a, b) return a.frame < b.frame end)

local held = {}              -- mask -> release frame (-1 = until release)
local gate, shift = nil, 0   -- 'until' condition, frames the timeline has waited
local tr = nil
local snd = nil              -- sndlog: file, previous ids / timers per slot

local function mask(names)
  local m = 0
  for n in names:gmatch("%S+") do m = m | (BTN[n] or 0) end
  return m
end

-- per-frame trace: player position (16.16 at px, py = px + 4), the player's hit rectangles, and for every active
-- hit object owned by a task (x pointer - 0x30) that task's HP (s32 at task + 0x54); one line per frame:
-- F <frame> <x> <y> | P <rect...> | T <task>:<hp> ...
local function s16(v) if v >= 0x8000 then return v - 0x10000 end return v end
local function s32(v) if v >= 0x80000000 then return v - 0x100000000 end return v end
local function trace_frame()
  local px = tr.px
  local out = { string.format("F %d %d %d L %d %d", frame, s32(mem.read32(px)), s32(mem.read32(px + 4)),
                               mem.read8(px + 0x49), mem.read16(px + 0x4A)) }   -- shot level, power
  local n = s16(mem.read16(tr.cnt))
  local rects, tasks = {}, {}
  for i = 0, n - 1 do
    local k = mem.read16(tr.list + 2 * i)
    local e = tr.objs + k * 0x18
    local xp = mem.read32(e)
    local r = string.format("%d,%d,%d,%d", s16(mem.read16(e + 8)), s16(mem.read16(e + 10)),
                            s16(mem.read16(e + 12)), s16(mem.read16(e + 14)))
    if xp == tr.phit then rects[#rects + 1] = r
    elseif xp >= 0x8C000000 and xp < 0x8D000000 then          -- task x (s16 at task + 0x30)
      local t = xp - 0x30
      if not tasks[t] then tasks[t] = true; out[#out + 1] = string.format("T %x:%d:%x", t, s32(mem.read32(t + 0x54)),
                                                                          mem.read32(t + 0x58)) end
    end
  end
  table.insert(out, 2, "P " .. table.concat(rects, " "))
  tr.fh:write(table.concat(out, " "), "\n")
end

local function run(cmd)
  local op, args = cmd:match("^(%S+)%s*(.*)$")
  if op == "press" then held[mask(args)] = -1
  elseif op == "release" then local m = mask(args); held[m] = nil; inp.releaseButtons(1, m)
  elseif op == "tap" then local n, names = args:match("^(%d+)%s+(.+)$"); held[mask(names)] = frame + tonumber(n)
  elseif op == "snap" then flycast.emulator.screenshot(args)
  elseif op == "poke8" or op == "poke16" or op == "poke32" then
    local a, v = args:match("^(%x+)%s+(%x+)$"); a = tonumber(a, 16); v = tonumber(v, 16)
    if op == "poke8" then mem.write8(a, v) elseif op == "poke16" then mem.write16(a, v) else mem.write32(a, v) end
  elseif op == "peek" then
    local a, n = args:match("^(%x+)%s+(%d+)$"); a = tonumber(a, 16); local s = {}
    for i = 0, tonumber(n) - 1 do s[#s + 1] = string.format("%02x", mem.read8(a + i)) end
    print(string.format("PEEK %d %08x %s", frame, a, table.concat(s, " ")))
  elseif op == "dumpmem" then
    local a, n, file = args:match("^(%x+)%s+(%x+)%s+(.+)$"); a = tonumber(a, 16); n = tonumber(n, 16)
    local fh = io.open(file, "wb")
    for i = 0, n - 1 do fh:write(string.char(mem.read8(a + i))) end
    fh:close()
  elseif op == "trace" then
    local file, px, phit, objs, list, cnt = args:match("^(%S+)%s+(%x+)%s+(%x+)%s+(%x+)%s+(%x+)%s+(%x+)$")
    tr = { fh = io.open(file, "w"), px = tonumber(px, 16), phit = tonumber(phit, 16), objs = tonumber(objs, 16),
           list = tonumber(list, 16), cnt = tonumber(cnt, 16) }
  elseif op == "until" or op == "timer" then
    local a, lo, hi = args:match("^(%x+)%s+(%x+)%s+(%x+)$")
    gate = { a = tonumber(a, 16), lo = tonumber(lo, 16), hi = tonumber(hi, 16), timer = op == "timer", run = 0 }
  elseif op == "sndlog" then
    snd = { fh = io.open(args, "w"), id = {}, t = {} }
  elseif op == "exit" then
    if tr then tr.fh:close() end
    if snd then snd.fh:close() end
    io.stdout:flush()
    os.exit(0)
  end
end

function cbVBlank()
  frame = frame + 1
  if frame % 300 == 0 then print(string.format("FRAME %d %.1f", frame, os.clock())); io.stdout:flush() end
  for m, until_f in pairs(held) do
    if until_f ~= -1 and frame >= until_f then held[m] = nil; inp.releaseButtons(1, m)
    else inp.pressButtons(1, m) end
  end
  if gate then
    local v = mem.read16(gate.a)
    local ok = v >= gate.lo and v <= gate.hi
    if gate.timer then
      if ok and gate.prev and v == gate.prev - 1 then gate.run = gate.run + 1 else gate.run = 0 end
      gate.prev = v; ok = gate.run >= 5
    end
    if ok then print(string.format("UNTIL met at %d (shift %d)", frame, shift)); gate = nil
    else shift = shift + 1 end
  end
  while not gate and idx <= #events and events[idx].frame + shift <= frame do run(events[idx].cmd); idx = idx + 1 end
  if tr then trace_frame() end
  if snd then
    for c = 0, 7 do
      local id, t = mem.read16(0x8C16D3A0 + 2 * c), mem.read8(0x8C16D27C + c)
      if snd.id[c] ~= nil and (id ~= snd.id[c] or t > snd.t[c]) then
        snd.fh:write(string.format("%d %d %x\n", frame, c, id))
      end
      snd.id[c], snd.t[c] = id, t
    end
  end
end

flycast_callbacks = { vblank = cbVBlank }
