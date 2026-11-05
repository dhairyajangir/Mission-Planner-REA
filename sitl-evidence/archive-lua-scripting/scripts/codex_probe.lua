local n = 0
local function update()
  n = n + 1
  gcs:send_text(6, "CODEX_LUA_PROBE " .. n)
  return update, 1000
end
return update, 1000
