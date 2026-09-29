-- MAME -autoboot_script: run the debugger commands in the file named by env GB2_DBGCMDS (one per line, e.g.
-- 'bpset 0600c7b8,1,{printf "B %x\n",r4;g}' then 'g'), exit after GB2_FRAMES frames (default 3600).  Run MAME with
-- -debug -debugger none -debuglog: printf output goes to debug.log (-debugscript is ignored without a debugger UI).
local dbg = manager.machine.debugger
local f = io.open(os.getenv("GB2_DBGCMDS"), "r")
for line in f:lines() do if #line > 0 then dbg:command(line) end end
f:close()
local n = 0
emu.register_frame_done(function()
  n = n + 1
  if n == tonumber(os.getenv("GB2_FRAMES") or "3600") then manager.machine:exit() end
end)
