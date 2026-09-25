-- Controlled-runtime contract for KeystoneLens tooltip integration.
-- Executes the real Tooltip.lua with minimal WoW API doubles under Lua 5.1.

local function fail(message)
    error("tooltip contract failed: " .. message, 2)
end

local function assertEq(actual, expected, message)
    if actual ~= expected then
        fail((message or "values differ") .. " (expected " .. tostring(expected) .. ", got " .. tostring(actual) .. ")")
    end
end

local function assertTrue(value, message)
    if not value then fail(message or "expected true") end
end

local now = 2000
local activeActivity = 777
local currentSpec = 62
local currentMetric = "DPS"
local currentPercentile = 97.4
local currentOwner = nil
local displayedUnit = nil
local displayedRealm = "Draenor"
local eventFrame = nil
local unitPostCall = nil

_G.issecretvalue = function() return false end
_G.time = function() return now end
_G.GetNormalizedRealmName = function() return "Draenor" end
_G.GetCurrentRegion = function() return 3 end
_G.UnitIsPlayer = function(unit) return unit == "unit-player" end
_G.UnitFullName = function(unit)
    if unit == "unit-player" then return "Alice", displayedRealm end
end

_G.TooltipUtil = {
    GetDisplayedUnit = function()
        if displayedUnit then return "Alice", displayedUnit end
        return nil, nil
    end,
}

_G.Enum = { TooltipDataType = { Unit = 1 } }
_G.TooltipDataProcessor = {
    AddTooltipPostCall = function(_, callback)
        unitPostCall = callback
    end,
}

local tooltipScripts = {}
_G.GameTooltip = {
    shown = true,
    lines = {},
    AddDoubleLine = function(self, left, right)
        self.lines[#self.lines + 1] = { left = left, right = right }
    end,
    Show = function(self) self.shown = true end,
    IsShown = function(self) return self.shown end,
    GetOwner = function() return currentOwner end,
    GetUnit = function() return nil, displayedUnit end,
    HookScript = function(self, event, callback)
        tooltipScripts[event] = tooltipScripts[event] or {}
        table.insert(tooltipScripts[event], callback)
    end,
}

_G.hooksecurefunc = function(target, methodName, hook)
    local original = target[methodName]
    target[methodName] = function(self, ...)
        local results = { original(self, ...) }
        hook(self, ...)
        return unpack(results)
    end
end

local timers = {}
_G.C_Timer = {
    After = function(delay, callback)
        timers[#timers + 1] = { delay = delay, callback = callback }
        callback()
    end,
}

local member = {
    mouseOver = true,
}
function member:GetParent() return self.parent end
function member:IsMouseOver() return self.mouseOver end
function member:HookScript(event, callback)
    self[event] = callback
end

local row = {
    applicantID = 42,
    Members = { member },
}
member.parent = row

local scrollBox = {
    framesChanged = nil,
}
function scrollBox:ForEachFrame(callback)
    callback(row)
end

_G.ScrollBoxUtil = {
    OnViewFramesChanged = function(_, box, callback)
        box.framesChanged = callback
    end,
}

_G.LFGListFrame = {
    ApplicationViewer = {
        ScrollBox = scrollBox,
    },
}

_G.C_LFGList = {
    GetActiveEntryInfo = function()
        return { activityIDs = { activeActivity } }
    end,
    GetActivityInfoTable = function(activityID)
        if activityID == 777 then return { fullName = "Altar of Fangs" } end
        if activityID == 778 then return { fullName = "Murder Row" } end
        return nil
    end,
    GetApplicantMemberInfo = function(applicantID, memberIdx)
        if applicantID ~= 42 or memberIdx ~= 1 then return nil end
        return "Alice-Draenor",
            nil, nil, nil, nil, nil, nil, nil,
            nil, nil, nil, nil, nil, nil, nil,
            currentSpec
    end,
}

_G.CreateFrame = function()
    eventFrame = {
        events = {},
        scripts = {},
    }
    function eventFrame:RegisterEvent(event)
        self.events[event] = true
    end
    function eventFrame:SetScript(event, callback)
        self.scripts[event] = callback
    end
    return eventFrame
end

local function setCache(spec, metric, percentile, fetchedAt)
    local code = metric == "HPS" and "H" or "D"
    local stamp = fetchedAt or now
    _G.KeystoneLensPreloadV4 = {
        version = 4,
        generatedAt = stamp,
        maxAge = 7 * 24 * 60 * 60,
        region = 3,
        season = "midnight-s2",
        entries = {
            ["alice-draenor|" .. tostring(spec) .. "|altaroffangs"] = {
                code, percentile, stamp,
            },
        },
        unitEntries = {
            ["alice-draenor|altaroffangs"] = {
                code, percentile, stamp,
            },
        },
    }
end

local function clearTooltip()
    GameTooltip.lines = {}
    GameTooltip.shown = true
    for _, callback in ipairs(tooltipScripts.OnTooltipCleared or {}) do
        callback(GameTooltip)
    end
end

setCache(62, "DPS", 97.4, now)

dofile("addon/KeystoneLensBridge/Core/Tooltip.lua")
assertTrue(eventFrame and eventFrame.scripts.OnEvent, "Tooltip.lua did not install its event frame")

-- Login registers the Raider.IO score hook, unit post-call and LFG frame hooks.
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
assertTrue(type(unitPostCall) == "function", "unit tooltip post-call was not registered")
assertTrue(type(member.OnEnter) == "function", "LFG applicant member was not hooked")
assertTrue(type(scrollBox.framesChanged) == "function", "recycled LFG frame callback was not registered")

-- 1. Exact requested placement: Raider.IO score line first, KeystoneLens immediately after it.
clearTooltip()
currentOwner = member
displayedUnit = nil
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3000")
assertEq(#GameTooltip.lines, 2, "WCL line was not injected directly after Raider.IO score")
assertEq(GameTooltip.lines[1].left, "Raider.IO M+ Score", "Raider.IO score line moved")
assertTrue(GameTooltip.lines[2].left:find("Warcraft Logs M+", 1, true) ~= nil, "WCL label missing")
assertEq(GameTooltip.lines[2].right, "DPS 97%", "DPS percentile formatting changed")

-- 2. Best Season / Best Run modes: ignore a previous-season headline and
-- insert directly after Raider.IO's explicit current-season score.
clearTooltip()
GameTooltip:AddDoubleLine("Raider.IO M+ Score (S1)", "±3200")
assertEq(#GameTooltip.lines, 1, "WCL was attached to a previous-season Raider.IO headline")
GameTooltip:AddDoubleLine("Current M+ Score", "3000")
assertEq(#GameTooltip.lines, 3, "WCL was not attached below Current M+ Score")
assertEq(GameTooltip.lines[2].left, "Current M+ Score", "current Raider.IO score line moved")
assertTrue(GameTooltip.lines[3].left:find("Warcraft Logs M+", 1, true) ~= nil, "WCL line missing after current score")

-- 3. Fallback OnEnter must not duplicate the line already injected by the score hook.
member.OnEnter(member)
assertEq(#GameTooltip.lines, 3, "fallback LFG hook duplicated the WCL line")

-- 4. Healing role uses the same compact line with Healing label.
clearTooltip()
currentSpec = 65
setCache(65, "HPS", 94.2, now)
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3010")
assertEq(#GameTooltip.lines, 2, "healing WCL line missing")
assertEq(GameTooltip.lines[2].right, "Healing 94%", "healing percentile formatting changed")

-- 5. Wrong spec fails closed.
clearTooltip()
currentSpec = 62
setCache(63, "DPS", 88.0, now)
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3020")
assertEq(#GameTooltip.lines, 1, "wrong specialization leaked WCL data")

-- 6. Wrong active dungeon fails closed.
clearTooltip()
currentSpec = 62
setCache(62, "DPS", 97.0, now)
activeActivity = 778
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3030")
assertEq(#GameTooltip.lines, 1, "wrong activity leaked WCL data")
activeActivity = 777

-- 7. Stale data fails closed.
clearTooltip()
setCache(62, "DPS", 97.0, 1)
now = 50000
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3040")
assertEq(#GameTooltip.lines, 1, "stale WCL data was rendered")
now = 2000

-- 8. Normal player tooltip path also appends after Raider.IO while an LFG activity is active.
clearTooltip()
currentOwner = {}
displayedUnit = "unit-player"
setCache(62, "DPS", 91.6, now)
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3050")
assertEq(#GameTooltip.lines, 2, "unit tooltip did not inject WCL under Raider.IO score")
assertEq(GameTooltip.lines[2].right, "DPS 92%", "unit tooltip percentile formatting changed")

-- 9. A same-name player on another realm must never inherit the local player's cache.
clearTooltip()
currentOwner = {}
displayedUnit = "unit-player"
displayedRealm = "Kazzak"
_G.KeystoneLensPreloadV4.entries = {
    ["alice-draenor|62|altaroffangs"] = { "D", 99, now },
}
_G.KeystoneLensPreloadV4.unitEntries = {
    ["alice-draenor|altaroffangs"] = { "D", 99, now },
}
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3060")
assertEq(#GameTooltip.lines, 1, "cross-realm player matched a same-realm short cache key")
displayedRealm = "Draenor"
setCache(62, "DPS", 91.6, now)

-- 10. If Raider.IO is absent/changes label, the LFG OnEnter fallback still renders.
clearTooltip()
currentOwner = member
displayedUnit = nil
GameTooltip.lines = {}
member.OnEnter(member)
assertEq(#GameTooltip.lines, 1, "standalone/fallback WCL line missing")
assertTrue(GameTooltip.lines[1].left:find("Warcraft Logs M+", 1, true) ~= nil, "fallback WCL label missing")

-- 11. The unit post-call fallback works independently of the Raider.IO score hook.
clearTooltip()
currentOwner = {}
displayedUnit = "unit-player"
GameTooltip.lines = {}
unitPostCall(GameTooltip)
assertEq(#GameTooltip.lines, 1, "unit post-call fallback did not render WCL")
assertEq(GameTooltip.lines[1].right, "DPS 92%", "unit post-call fallback value changed")

print("KeystoneLens tooltip integration contract passed.")
