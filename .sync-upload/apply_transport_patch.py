from pathlib import Path

path = Path("addon/KeystoneLensBridge/Core/Transport.lua")
text = path.read_text()

marker = "local function SafeRoundedNumber(v, default)\n"
helper = '''local function SafeOptionalNumber(v)
    if IsSecretValue(v) or v == nil then return nil end
    local tv = type(v)
    if tv ~= "number" and tv ~= "string" then return nil end
    local n = tonumber(v)
    if n == nil or n ~= n or n == math.huge or n == -math.huge then
        return nil
    end
    return n
end

'''

assert "local function SafeOptionalNumber(v)" not in text
assert text.count(marker) == 1
text = text.replace(marker, helper + marker, 1)

replacements = {
    "SafeNumber(converted, nil)": "SafeOptionalNumber(converted)",
    "SafeNumber(physicalHeight, nil)": "SafeOptionalNumber(physicalHeight)",
    "SafeNumber(effectiveScale, nil)": "SafeOptionalNumber(effectiveScale)",
    "SafeNumber(rawCount, nil)": "SafeOptionalNumber(rawCount)",
}
for old, new in replacements.items():
    assert text.count(old) == 1, (old, text.count(old))
    text = text.replace(old, new, 1)

path.write_text(text)
