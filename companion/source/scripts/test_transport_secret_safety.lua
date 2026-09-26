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

local KL = {}

local function load_module(path)
    local chunk = assert(loadfile(path))
    chunk("KeystoneLensBridge", KL)
end

load_module("addon/KeystoneLensBridge/Core/CapturePolicy.lua")
load_module("addon/KeystoneLensBridge/Core/TransportState.lua")

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

print("KeystoneLens transport secret-safety contract passed.")
