-- Controlled-runtime regression for existing KeystoneLens transport group-API safety.
-- Loads the real CapturePolicy, TransportState and Transport.lua, then injects
-- failing Blizzard group APIs. Existing transport behavior must fail closed,
-- never propagate the API failure.

local function fail(message)
    error("transport secret-safety contract failed: " .. message, 2)
end

local state = nil

_G.SlashCmdList = {}
_G.C_AddOns = {
    GetAddOnMetadata = function(_addon, field)
        if field == "Version" then return "fixture" end
        return nil
    end,
}

local function frame_stub()
    return {
        RegisterEvent = function() end,
        SetScript = function() end,
    }
end

_G.CreateFrame = function() return frame_stub() end
_G.C_Timer = {
    NewTicker = function() return { Cancel = function() end } end,
    After = function() end,
}
_G.issecretvalue = function() return false end

local TWO32 = 4294967296
local function norm32(value)
    value = math.floor(tonumber(value) or 0) % TWO32
    if value < 0 then value = value + TWO32 end
    return value
end
local function bit_loop(left, right, predicate)
    left, right = norm32(left), norm32(right)
    local result, bitValue = 0, 1
    for _ = 1, 32 do
        local leftBit, rightBit = left % 2, right % 2
        if predicate(leftBit, rightBit) then result = result + bitValue end
        left = math.floor(left / 2)
        right = math.floor(right / 2)
        bitValue = bitValue * 2
    end
    return result
end
_G.bit = {
    bxor = function(left, right)
        return bit_loop(left, right, function(a, b) return a ~= b end)
    end,
    band = function(left, right)
        return bit_loop(left, right, function(a, b) return a == 1 and b == 1 end)
    end,
    rshift = function(value, bits)
        return math.floor(norm32(value) / (2 ^ bits))
    end,
}

local KL = {}

local function load_module(path)
    local chunk = assert(loadfile(path))
    chunk("KeystoneLensBridge", KL)
end

load_module("addon/KeystoneLensBridge/Core/CapturePolicy.lua")
load_module("addon/KeystoneLensBridge/Core/TransportState.lua")

load_module("addon/KeystoneLensBridge/Core/ScreenshotController.lua")

local original_new = assert(KL.TransportState and KL.TransportState.New)
KL.TransportState.New = function(...)
    state = original_new(...)
    return state
end

load_module("addon/KeystoneLensBridge/Core/Transport.lua")

if type(state) ~= "table" then fail("transport state was not created") end
if type(state.CaptureAutoPauseReason) ~= "function" then
    fail("CaptureAutoPauseReason was not installed")
end

_G.GetNumGroupMembers = function()
    error("synthetic group-size read failure")
end
_G.IsInRaid = function() return false end
_G.C_ChallengeMode = {
    IsChallengeModeActive = function() return false end,
}
_G.IsInInstance = function() return false, "none" end

local ok, result = pcall(state.CaptureAutoPauseReason)
if not ok then
    fail("group-size API failure propagated: " .. tostring(result))
end
if result ~= nil then
    fail("unknown group size produced a pause reason: " .. tostring(result))
end

if type(state.CanUseOwnedKeystoneForListingFallback) ~= "function" then
    fail("CanUseOwnedKeystoneForListingFallback was not installed")
end
_G.IsInGroup = function()
    error("synthetic grouped-state read failure")
end
_G.UnitIsGroupLeader = function() return false end
ok, result = pcall(state.CanUseOwnedKeystoneForListingFallback)
if not ok then
    fail("grouped-state API failure propagated: " .. tostring(result))
end
if result ~= false then
    fail("unknown grouped state must fail closed for owned-key fallback")
end

-- CaptureAutoPauseReason already had an IsInRaid pcall before this benchmark.
-- Preserve that existing behavior and prove no extra product hardening is needed.
_G.GetNumGroupMembers = function() return 4 end
_G.IsInRaid = function()
    error("synthetic raid-state read failure")
end
ok, result = pcall(state.CaptureAutoPauseReason)
if not ok then
    fail("existing raid-state guard regressed: " .. tostring(result))
end
if result ~= nil then
    fail("raid-state API failure unexpectedly changed capture pause decision")
end

print("KeystoneLens transport secret-safety contract passed.")
