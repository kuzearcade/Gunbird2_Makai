-- Timeline-driven MAME harness for Gunbird 2 testing.
-- GB2_TIMELINE = path to a text file with lines:  <frame> <command> [args]
--   press <field name...>      hold an input (e.g. "press P1 Up")
--   release <field name...>    release it
--   tap <n> <field name...>    press for n frames
--   snap <file.png>            save a screenshot of the screen
--   dumpram <file.bin>         dump main RAM 0x06000000-0x060FFFFF
--   poke8/poke16/poke32 <addr> <value>   write memory (hex)
--   peek <addr> <len>          print bytes (hex) to stdout
--   dbg <debugger command...>  run a debugger command (needs -debug)
--   rtap <start> <end>         log each distinct PC that reads [start,end] (hex; print "RTAP pc addr data")
--   wtap <start> <end>         print every write to [start,end] (hex): "WTAP pc pr addr data mask frame"
--   usage <start> <end>        record every byte read/written in [start,end] (needs -nodrc: RAM is DRC fastram);
--                              printed at exit as "USAGE r|w <addr> <pc,pc,...>"
--   field <value> <name...>   set any input field (all ports), e.g. "1 field 0 Region" (0 = Japan)
--   sndlog                     poll the sound-effect slots every frame (pending 0x06079DD8 = id+1, current
--                              0x06079E08 = id, slots 0x0E-0x17); distinct ids printed at exit as "SND <id> <first frame>"
--   sndtrace                   print sound-effect starts as "SNDT <frame> <channel> <id>"
--   ymflog <file>              log every CPU write to the YMF278B (PS5 0x03100000-7) as
--                              "<frame> <time us> <addr> <data> <mask>" (register/data write sequence and timing)
--   trace <file> <player x> <player hit ptr> <hit objs> <hit list> <hit count>   per-frame trace, same format as
--                              tools/flycast/timeline.lua: F <frame> <x> <y> P <rects> T <task>:<hp>:<type> ...
--   phash <n> <file>           every n frames: "<frame> <screen hash> <stage counter> <1P score> <2P score> <GameLoop state>"
--                              (whole-game regression: tools/mame/regress_game.py)
--   pc                         print the main CPU's program counter ("PC <frame> <pc>")
--   weaken <hit objs> <hit list> <hit count> <hp>   every frame, cap the HP (s32 16.16 at task + 0x54) of every
--                              task owning an active hit object at <hp> (hex): stages clear fast (test runs only)
--   exit
--   until <addr> <mask> <value> <interval> <field...>   pause the timeline (later frame numbers shift) and
--                              tap <field> every <interval> frames until (u16 @addr & mask) == value
-- Frame numbers count from machine start (frame_done callbacks).
local path = os.getenv("GB2_TIMELINE")
local events = {}
for line in io.lines(path) do
  local f, rest = line:match("^%s*(%d+)%s+(.+)$")
  if f then
    events[#events + 1] = { frame = tonumber(f), cmd = rest }
  end
end
table.sort(events, function(a, b) return a.frame < b.frame end)

local port = manager.machine.ioport.ports[":INPUTS"]
local taps = {}      -- keep read taps alive
local usage = nil
local snd = nil      -- sndlog: id -> first frame
local ymffh = nil
local tr = nil      -- trace
local weak = nil    -- weaken
local ph = nil      -- phash
local sndt = nil     -- sndtrace: slot -> last pending value
local gate = nil     -- active "until" command
local shift = 0      -- frames the timeline has been paused
local held = {}      -- field name -> release frame (or -1 for hold)
local frame = 0
local idx = 1
local space = manager.machine.devices[":maincpu"].spaces["program"]

local function field(name)
  local fld = port.fields[name]
  if not fld then print("no field " .. name) end
  return fld
end

local function run(cmd)
  local op, args = cmd:match("^(%S+)%s*(.*)$")
  if op == "press" then
    local f = field(args); if f then f:set_value(1); held[args] = -1 end
  elseif op == "release" then
    local f = field(args); if f then f:set_value(0); held[args] = nil end
  elseif op == "tap" then
    local n, name = args:match("^(%d+)%s+(.+)$")
    local f = field(name); if f then f:set_value(1); held[name] = frame + tonumber(n) end
  elseif op == "snap" then
    manager.machine.video:snapshot()
    local scr = manager.machine.screens[":screen"]
    scr:snapshot(args)
  elseif op == "dumpram" then
    local fh = io.open(args, "wb")
    for a = 0x06000000, 0x060FFFFF, 4 do
      local v = space:read_u32(a)
      fh:write(string.char((v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255))
    end
    fh:close()
  elseif op == "dumpmem" then
    local a, n, file = args:match("^(%x+)%s+(%x+)%s+(.+)$")
    a = tonumber(a, 16); n = tonumber(n, 16)
    local fh = io.open(file, "wb")
    for x = a, a + n - 1, 4 do
      local v = space:read_u32(x)
      fh:write(string.char((v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255))
    end
    fh:close()
  elseif op == "poke8" or op == "poke16" or op == "poke32" then
    local a, v = args:match("^(%x+)%s+(%x+)$")
    a = tonumber(a, 16); v = tonumber(v, 16)
    if op == "poke8" then space:write_u8(a, v) elseif op == "poke16" then space:write_u16(a, v) else space:write_u32(a, v) end
  elseif op == "peek" then
    local a, n = args:match("^(%x+)%s+(%d+)$")
    a = tonumber(a, 16); local s = {}
    for i = 0, tonumber(n) - 1 do s[#s + 1] = string.format("%02x", space:read_u8(a + i)) end
    print(string.format("PEEK %08x %s", a, table.concat(s, " ")))
  elseif op == "dbg" then
    manager.machine.debugger:command(args)
  elseif op == "rtap" then
    local a, b = args:match("^(%x+)%s+(%x+)$")
    a = tonumber(a, 16); b = tonumber(b, 16)
    local cpu = manager.machine.devices[":maincpu"]
    local seen = {}
    taps[#taps + 1] = space:install_read_tap(a, b, "rtap" .. #taps, function(offset, data, mask)
      local pc = cpu.state["PC"].value
      local k = pc .. ":" .. offset
      if not seen[k] then seen[k] = true; print(string.format("RTAP pc=%08x addr=%08x data=%08x frame=%d", pc, offset, data, frame)) end
      return data
    end)
  elseif op == "wtap" then
    local a, b = args:match("^(%x+)%s+(%x+)$")
    a = tonumber(a, 16); b = tonumber(b, 16)
    local cpu = manager.machine.devices[":maincpu"]
    taps[#taps + 1] = space:install_write_tap(a, b, "wtap" .. #taps, function(offset, data, mask)
      local task = space:read_u32(0x0604005C)                -- seq VM: current task, its script pointer
      local spc = task ~= 0 and space:read_u32(space:read_u32(task + 0x20) + 0x10) or 0
      print(string.format("WTAP pc=%08x pr=%08x addr=%08x data=%08x mask=%08x frame=%d task=%08x script=%08x",
                          cpu.state["PC"].value, cpu.state["PR"].value, offset, data, mask, frame, task, spc))
      return data
    end)
  elseif op == "usage" then
    local a, b = args:match("^(%x+)%s+(%x+)$")
    a = tonumber(a, 16); b = tonumber(b, 16)
    usage = usage or { r = {}, w = {}, base = a }
    local cpu = manager.machine.devices[":maincpu"]
    local function mark(t, offset, mask)
      local pc = cpu.state["PC"].value
      for k = 0, 3 do
        if ((mask >> (8 * (3 - k))) & 0xff) ~= 0 then
          local o = (offset & ~3) + k
          t[o] = t[o] or {}
          t[o][pc] = true
        end
      end
    end
    taps[#taps + 1] = space:install_read_tap(a, b, "ur", function(offset, data, mask) mark(usage.r, offset, mask); return data end)
    taps[#taps + 1] = space:install_write_tap(a, b, "uw", function(offset, data, mask) mark(usage.w, offset, mask); return data end)
  elseif op == "field" then
    local v, name = args:match("^(%d+)%s+(.+)$")
    for tag, p in pairs(manager.machine.ioport.ports) do
      local f = p.fields[name]
      if f then f:set_value(tonumber(v)); print("FIELD " .. tag .. " " .. name .. " = " .. v) end
    end
  elseif op == "until" then
    local a, m, v, iv, name = args:match("^(%x+)%s+(%x+)%s+(%x+)%s+(%d+)%s+(.+)$")
    gate = { a = tonumber(a, 16), m = tonumber(m, 16), v = tonumber(v, 16), iv = tonumber(iv), name = name, next = frame }
  elseif op == "sndlog" then
    snd = snd or {}
  elseif op == "trace" then
    local file, px, phit, objs, list, cnt = args:match("^(%S+)%s+(%x+)%s+(%x+)%s+(%x+)%s+(%x+)%s+(%x+)$")
    tr = { fh = io.open(file, "w"), px = tonumber(px, 16), phit = tonumber(phit, 16), objs = tonumber(objs, 16),
           list = tonumber(list, 16), cnt = tonumber(cnt, 16) }
  elseif op == "phash" then
    local n, file = args:match("^(%d+)%s+(.+)$")
    ph = { n = tonumber(n), fh = io.open(file, "w"), scr = manager.machine.screens[":screen"] }
  elseif op == "pc" then
    print(string.format("PC %d %08x", frame, manager.machine.devices[":maincpu"].state["PC"].value))
  elseif op == "weaken" then
    local objs, list, cnt, hp = args:match("^(%x+)%s+(%x+)%s+(%x+)%s+(%x+)$")
    weak = { objs = tonumber(objs, 16), list = tonumber(list, 16), cnt = tonumber(cnt, 16), hp = tonumber(hp, 16) }
  elseif op == "ymflog" then
    local fh = io.open(args, "w")
    taps[#taps + 1] = space:install_write_tap(0x03100000, 0x03100007, "ymflog", function(offset, data, mask)
      fh:write(string.format("%d %.3f %x %08x %08x\n", frame, manager.machine.time:as_double() * 1e6, offset, data, mask))
      return data
    end)
    ymffh = fh
  elseif op == "sndtrace" then
    sndt = sndt or {}
  elseif op == "exit" then
    if ymffh then ymffh:close() end
    if tr then tr.fh:close() end
    if ph then ph.fh:close() end
    if snd then
      local l = {}
      for id in pairs(snd) do l[#l + 1] = id end
      table.sort(l)
      for _, id in ipairs(l) do print(string.format("SND %03x %d", id, snd[id])) end
    end
    if usage then
      for _, kind in ipairs({ "r", "w" }) do
        local l = {}
        for o in pairs(usage[kind]) do l[#l + 1] = o end
        table.sort(l)
        for _, o in ipairs(l) do
          local pcs = {}
          for pc in pairs(usage[kind][o]) do pcs[#pcs + 1] = string.format("%x", pc) end
          table.sort(pcs)
          print(string.format("USAGE %s %x %s", kind, o, table.concat(pcs, ",")))
        end
      end
    end
    manager.machine:exit()
  end
end

local function s16(v) if v >= 0x8000 then return v - 0x10000 end return v end
local function s32(v) if v >= 0x80000000 then return v - 0x100000000 end return v end
local function trace_frame()
  local out = { string.format("F %d %d %d L %d %d", frame, s32(space:read_u32(tr.px)), s32(space:read_u32(tr.px + 4)),
                               space:read_u8(tr.px + 0x49), space:read_u16(tr.px + 0x4A)) }   -- shot level, power
  local n = s16(space:read_u16(tr.cnt))
  local rects, seen = {}, {}
  for i = 0, n - 1 do
    local k = space:read_u16(tr.list + 2 * i)
    local e = tr.objs + k * 0x18
    local xp = space:read_u32(e)
    local r = string.format("%d,%d,%d,%d", s16(space:read_u16(e + 8)), s16(space:read_u16(e + 10)),
                            s16(space:read_u16(e + 12)), s16(space:read_u16(e + 14)))
    if xp == tr.phit then rects[#rects + 1] = r
    elseif xp >= 0x06000000 and xp < 0x06100000 then            -- task x (s16 at task + 0x30)
      local t = xp - 0x30
      if not seen[t] then seen[t] = true; out[#out + 1] = string.format("T %x:%d:%x", t, s32(space:read_u32(t + 0x54)),
                                                                        space:read_u32(t + 0x58)) end
    end
  end
  table.insert(out, 2, "P " .. table.concat(rects, " "))
  tr.fh:write(table.concat(out, " "), "\n")
end

local function phash_frame()
  local px, w, h = ph.scr:pixels()
  local hsh = 2166136261
  for i = 1, #px - 7, 8 do                                  -- FNV-1a over 64-bit words, folded to 32 bits
    local a = string.unpack("<i8", px, i)
    hsh = ((hsh ~ a) * 16777619) & 0xFFFFFFFF
  end
  ph.fh:write(string.format("%d %08x %02x %d %d %d\n", frame, hsh, space:read_u8(0x0604C8C0),
                            space:read_u32(0x06055030), space:read_u32(0x060550E0), space:read_u32(0x0604C744)))
end

local function weaken_frame()
  local n = s16(space:read_u16(weak.cnt))
  for i = 0, n - 1 do
    local xp = space:read_u32(weak.objs + space:read_u16(weak.list + 2 * i) * 0x18)
    if xp >= 0x06000000 and xp < 0x06100000 and (xp < 0x06055000 or xp >= 0x06055160) then   -- not a player block
      local t = xp - 0x30
      if s32(space:read_u32(t + 0x54)) > weak.hp then space:write_u32(t + 0x54, weak.hp) end
    end
  end
end

emu.register_frame_done(function()
  frame = frame + 1
  if tr then trace_frame() end
  if weak then weaken_frame() end
  if ph and frame % ph.n == 0 then phash_frame() end
  if sndt then                   -- a start sets the channel's id (0x06079E08) and its counter (0x06079D90) to 10
    for i = 0x0E, 0x17 do
      local id, cnt = space:read_u16(0x06079E08 + 2 * i), space:read_u8(0x06079D90 + i)
      local k = id * 256 + cnt
      if cnt == 10 and k ~= (sndt[i] or -1) then print(string.format("SNDT %d %x %03x", frame, i, id)) end
      sndt[i] = k
    end
  end
  if snd then
    for i = 0x0E, 0x17 do
      local p = space:read_u16(0x06079DD8 + 2 * i)
      if p ~= 0 and p <= 0x200 and not snd[p - 1] then snd[p - 1] = frame end
      local c = space:read_u16(0x06079E08 + 2 * i)
      if c ~= 0 and c < 0x200 and not snd[c] then snd[c] = frame end
    end
  end
  for name, until_f in pairs(held) do
    if until_f ~= -1 and frame >= until_f then port.fields[name]:set_value(0); held[name] = nil end
  end
  if gate then
    if (space:read_u16(gate.a) & gate.m) == gate.v then
      print(string.format("UNTIL met at frame %d (shift %d)", frame, shift)); gate = nil
    else
      shift = shift + 1
      if frame >= gate.next and not held[gate.name] then
        local f = field(gate.name); if f then f:set_value(1); held[gate.name] = frame + 4 end
        gate.next = frame + gate.iv
      end
      return
    end
  end
  while idx <= #events and events[idx].frame + shift <= frame do
    run(events[idx].cmd); idx = idx + 1
  end
end)
