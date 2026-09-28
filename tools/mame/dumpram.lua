-- dump main RAM after N frames, then exit. env: GB2_FRAMES, GB2_OUT
local frames = tonumber(os.getenv("GB2_FRAMES") or "600")
local out = os.getenv("GB2_OUT") or "ram.bin"
local n = 0
emu.register_frame_done(function()
  n = n + 1
  if n == frames then
    local sp = manager.machine.devices[":maincpu"].spaces["program"]
    local f = io.open(out, "wb")
    for a = 0x06000000, 0x060FFFFF, 4 do
      local v = sp:read_u32(a)
      f:write(string.char((v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255))
    end
    f:close()
    manager.machine:exit()
  end
end)
