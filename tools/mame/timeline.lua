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
--   usage <start> <end>        record every byte read/written in [start,end] (needs -nodrc: RAM is DRC fastram);
--                              printed at exit as "USAGE r|w <addr> <pc,pc,...>"
--   field <value> <name...>   set any input field (all ports), e.g. "1 field 0 Region" (0 = Japan)
--   sndlog                     poll the sound-effect slots every frame (pending 0x06079DD8 = id+1, current
--                              0x06079E08 = id, slots 0x0E-0x17); distinct ids printed at exit as "SND <id> <first frame>"
--   sndtrace                   print sound-effect starts as "SNDT <frame> <channel> <id>"
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
  elseif op == "sndtrace" then
    sndt = sndt or {}
  elseif op == "exit" then
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

emu.register_frame_done(function()
  frame = frame + 1
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
