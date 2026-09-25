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
local currentOwner = nil
local displayedUnit = nil
local displayedRealm = "Draenor"
local eventFrame = nil
local unitPostCall = nil
local liveRequests = {}

_G.issecretvalue = function() return false end
_G.time = function() return now end
_G.GetNormalizedRealmName = function() return "Draenor" end
_G.UnitIsPlayer = function(unit) return unit == "unit-player" end
_G.UnitFullName = function(unit)
    if unit == "unit-player" then return "Alice", displayedRealm end
end

_G.UIParent = {
    GetWidth = function() return 1920 end,
    GetHeight = function() return 1080 end,
}

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

local function rectFrame(left, bottom, width, height)
    return {
        GetLeft = function() return left end,
        GetBottom = function() return bottom end,
        GetWidth = function() return width end,
        GetHeight = function() return height end,
    }
end

local tooltipScripts = {}
_G.GameTooltip = {
    shown = true,
    lines = {},
    AddDoubleLine = function(self, left, right)
        self.lines[#self.lines + 1] = { left = left, right = right }
        local index = #self.lines
        _G["GameTooltipTextLeft" .. tostring(index)] = rectFrame(
            1010,
            500 + (index * 18),
            180,
            16
        )
    end,
    NumLines = function(self) return #self.lines end,
    Show = function(self) self.shown = true end,
    IsShown = function(self) return self.shown end,
    GetOwner = function() return currentOwner end,
    GetUnit = function() return nil, displayedUnit end,
    GetLeft = function() return 1000 end,
    GetBottom = function() return 500 end,
    GetWidth = function() return 300 end,
    GetHeight = function() return 180 end,
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
function member:HookScript(event, callback) self[event] = callback end
function member:GetLeft() return 780 end
function member:GetBottom() return 390 end
function member:GetWidth() return 220 end
function member:GetHeight() return 32 end

local row = {
    applicantID = 42,
    Members = { member },
}
member.parent = row

local scrollBox = { framesChanged = nil }
function scrollBox:ForEachFrame(callback) callback(row) end

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
    GetApplicantMemberInfo = function(applicantID, memberIdx)
        if applicantID ~= 42 or memberIdx ~= 1 then return nil end
        return "Alice-Draenor",
            nil, nil, nil, nil, nil, nil, nil,
            nil, nil, nil, nil, nil, nil, nil,
            currentSpec
    end,
}

_G.CreateFrame = function()
    eventFrame = { events = {}, scripts = {} }
    function eventFrame:RegisterEvent(event) self.events[event] = true end
    function eventFrame:SetScript(event, callback) self.scripts[event] = callback end
    return eventFrame
end

local KL = {
    RequestLiveHover = function(context)
        liveRequests[#liveRequests + 1] = context
        return true
    end,
}

local function setCache(spec, metric, percentile, fetchedAt)
    _G.KeystoneLensTooltipCacheV3 = {
        version = 3,
        generatedAt = fetchedAt or now,
        maxAge = 43200,
        entries = {
            ["Alice-Draenor"] = {
                activityID = 777,
                specID = spec,
                metric = metric,
                percentile = percentile,
                fetchedAt = fetchedAt or now,
            },
        },
    }
end

local function emptyCache()
    _G.KeystoneLensTooltipCacheV3 = {
        version = 3,
        generatedAt = now,
        maxAge = 43200,
        entries = {},
    }
end

local function clearTooltip()
    GameTooltip.lines = {}
    GameTooltip.shown = true
    liveRequests = {}
    for i = 1, 20 do _G["GameTooltipTextLeft" .. tostring(i)] = nil end
    for _, callback in ipairs(tooltipScripts.OnTooltipCleared or {}) do
        callback(GameTooltip)
    end
end

setCache(62, "DPS", 97.4, now)

local chunk, loadError = loadfile("addon/KeystoneLensBridge/Core/Tooltip.lua")
assertTrue(chunk ~= nil, loadError or "Tooltip.lua could not be loaded")
chunk("KeystoneLensBridge", KL)
assertTrue(eventFrame and eventFrame.scripts.OnEvent, "Tooltip.lua did not install its event frame")

eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
assertTrue(type(unitPostCall) == "function", "unit tooltip post-call was not registered")
assertTrue(type(member.OnEnter) == "function", "LFG applicant member was not hooked")
assertTrue(type(scrollBox.framesChanged) == "function", "recycled LFG frame callback was not registered")

-- 1. Exact placement: Group Finder always reserves a blank live cell directly
-- under Raider.IO, even when a warm Data.lua value exists. This prevents an
-- old cached number from ghosting underneath the Companion's live value.
clearTooltip()
currentOwner = member
displayedUnit = nil
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3000")
assertEq(#GameTooltip.lines, 2, "WCL line was not injected directly after Raider.IO score")
assertEq(GameTooltip.lines[1].left, "Raider.IO M+ Score", "Raider.IO score line moved")
assertTrue(GameTooltip.lines[2].left:find("Warcraft Logs M+", 1, true) ~= nil, "WCL label missing")
assertEq(GameTooltip.lines[2].right, "", "Group Finder must reserve a blank live value cell")
assertEq(#liveRequests, 1, "cached applicant did not publish live hover geometry")
assertEq(liveRequests[1].applicantID, 42, "live hover applicant ID changed")
assertEq(liveRequests[1].memberIdx, 1, "live hover member index changed")
assertEq(liveRequests[1].activityID, 777, "live hover activity changed")
assertTrue(liveRequests[1].valueW > 0 and liveRequests[1].valueH > 0, "live value rectangle was not captured")
assertTrue(liveRequests[1].ownerW > 0 and liveRequests[1].ownerH > 0, "hover owner rectangle was not captured")

-- 2. Critical no-reload path: a brand-new player with no Data.lua entry still gets
-- a reserved WCL row and sends a live request to the Companion.
clearTooltip()
emptyCache()
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3001")
assertEq(#GameTooltip.lines, 2, "new applicant did not get a reserved WCL row")
assertTrue(GameTooltip.lines[2].left:find("Warcraft Logs M+", 1, true) ~= nil, "new applicant WCL label missing")
assertEq(GameTooltip.lines[2].right, "", "new applicant placeholder must not invent a value")
assertEq(#liveRequests, 1, "new applicant did not request live Companion data")

-- 3. Best Season / Best Run modes anchor below the explicit current score.
clearTooltip()
setCache(62, "DPS", 97.4, now)
GameTooltip:AddDoubleLine("Raider.IO M+ Score (S1)", "±3200")
assertEq(#GameTooltip.lines, 1, "WCL was attached to a previous-season Raider.IO headline")
GameTooltip:AddDoubleLine("Current M+ Score", "3000")
assertEq(#GameTooltip.lines, 3, "WCL was not attached below Current M+ Score")
assertEq(GameTooltip.lines[2].left, "Current M+ Score", "current Raider.IO score line moved")
assertTrue(GameTooltip.lines[3].left:find("Warcraft Logs M+", 1, true) ~= nil, "WCL line missing after current score")

-- 4. Fallback OnEnter must not duplicate the line already injected by the score hook.
member.OnEnter(member)
assertEq(#GameTooltip.lines, 3, "fallback LFG hook duplicated the WCL line")

-- 5. Healers use the same reserved live row; the Companion owns the rendered HPS value.
clearTooltip()
currentSpec = 65
setCache(65, "HPS", 94.2, now)
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3010")
assertEq(#GameTooltip.lines, 2, "healing WCL line missing")
assertEq(GameTooltip.lines[2].right, "", "Group Finder healer row must stay live-only")
assertEq(#liveRequests, 1, "healer did not publish live hover geometry")

-- 6. Wrong spec never leaks cached data; it falls back to the blank live row.
clearTooltip()
currentSpec = 62
setCache(63, "DPS", 88.0, now)
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3020")
assertEq(#GameTooltip.lines, 2, "wrong-spec applicant lost the live placeholder")
assertEq(GameTooltip.lines[2].right, "", "wrong specialization leaked cached WCL data")
assertEq(#liveRequests, 1, "wrong-spec applicant did not request fresh live data")

-- 7. Wrong active dungeon never leaks cached data; live request follows current activity.
clearTooltip()
setCache(62, "DPS", 97.0, now)
activeActivity = 778
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3030")
assertEq(#GameTooltip.lines, 2, "wrong-activity applicant lost the live placeholder")
assertEq(GameTooltip.lines[2].right, "", "wrong activity leaked cached WCL data")
assertEq(liveRequests[1].activityID, 778, "live request did not follow current activity")
activeActivity = 777

-- 8. Stale cache never renders a stale number; Companion live path stays available.
clearTooltip()
setCache(62, "DPS", 97.0, 1)
now = 50000
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3040")
assertEq(#GameTooltip.lines, 2, "stale-cache applicant lost the live placeholder")
assertEq(GameTooltip.lines[2].right, "", "stale WCL data was rendered")
assertEq(#liveRequests, 1, "stale cache did not fall through to live Companion data")
now = 2000

-- 9. Protected/unreadable layout geometry fails closed without breaking the tooltip.
clearTooltip()
currentOwner = member
displayedUnit = nil
local originalGetLeft = member.GetLeft
member.GetLeft = function() error("protected layout") end
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3045")
assertEq(#GameTooltip.lines, 2, "protected layout removed the WCL placeholder")
assertEq(#liveRequests, 0, "protected layout must not publish unsafe geometry")
member.GetLeft = originalGetLeft

-- 10. Normal player tooltip still uses safely preloaded local cache.
clearTooltip()
currentOwner = {}
displayedUnit = "unit-player"
setCache(62, "DPS", 91.6, now)
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3050")
assertEq(#GameTooltip.lines, 2, "unit tooltip did not inject WCL under Raider.IO score")
assertEq(GameTooltip.lines[2].right, "DPS 92%", "unit tooltip percentile formatting changed")
assertEq(#liveRequests, 0, "normal unit tooltip must not invent an LFG live request")

-- 11. Same-name cross-realm players never inherit a short local cache key.
clearTooltip()
displayedRealm = "Kazzak"
_G.KeystoneLensTooltipCacheV3.entries = {
    ["Alice"] = {
        activityID = 777,
        specID = 62,
        metric = "DPS",
        percentile = 99,
        fetchedAt = now,
    },
}
GameTooltip:AddDoubleLine("Raider.IO M+ Score", "3060")
assertEq(#GameTooltip.lines, 1, "cross-realm player matched a same-realm short cache key")
displayedRealm = "Draenor"
setCache(62, "DPS", 91.6, now)

-- 11. Without Raider.IO, LFG OnEnter still creates the same row and live request.
clearTooltip()
currentOwner = member
displayedUnit = nil
emptyCache()
member.OnEnter(member)
assertEq(#GameTooltip.lines, 1, "standalone live WCL row missing")
assertTrue(GameTooltip.lines[1].left:find("Warcraft Logs M+", 1, true) ~= nil, "standalone WCL label missing")
assertEq(GameTooltip.lines[1].right, "", "standalone placeholder invented a value")
assertEq(#liveRequests, 1, "standalone LFG hover did not request live data")

-- 12. Unit post-call fallback remains independent of the Raider.IO score hook.
clearTooltip()
currentOwner = {}
displayedUnit = "unit-player"
setCache(62, "DPS", 91.6, now)
unitPostCall(GameTooltip)
assertEq(#GameTooltip.lines, 1, "unit post-call fallback did not render WCL")
assertEq(GameTooltip.lines[1].right, "DPS 92%", "unit post-call fallback value changed")

print("KeystoneLens live tooltip integration contract passed.")
