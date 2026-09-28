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
--   exit
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
  elseif op == "exit" then
    manager.machine:exit()
  end
end

emu.register_frame_done(function()
  frame = frame + 1
  for name, until_f in pairs(held) do
    if until_f ~= -1 and frame >= until_f then port.fields[name]:set_value(0); held[name] = nil end
  end
  while idx <= #events and events[idx].frame <= frame do
    run(events[idx].cmd); idx = idx + 1
  end
end)
