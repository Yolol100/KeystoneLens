-- KeystoneLens cached applicant tooltip integration.
-- Raider.IO owns its tooltip rendering. KeystoneLens only appends cached,
-- non-secret WCL/combined-score lines after Raider.IO has rendered.

local addonName = ...
local hooked = setmetatable({}, { __mode = "k" })
local tooltipKey = nil
local KL_ICON = "|TInterface\\AddOns\\KeystoneLensBridge\\Media\\KeystoneLensIcon:16:16:0:0|t"

local function NormalizeFullName(fullName)
    if type(fullName) ~= "string" or fullName == "" then return nil end
    return fullName
end

local function GetFreshEntry(fullName)
    local cache = _G.KeystoneLensTooltipCache
    if type(cache) ~= "table" or type(cache.entries) ~= "table" then return nil end
    local key = NormalizeFullName(fullName)
    if not key then return nil end
    local entry = cache.entries[key]
    -- 0.8.3 wrote lowercase keys. Keep an ASCII-compatible fallback for one
    -- release, but prefer the exact byte identity so localized names do not
    -- depend on Python-vs-Lua Unicode case conversion behavior.
    if type(entry) ~= "table" then
        local legacyKey = string.lower(key)
        entry = cache.entries[legacyKey]
        if type(entry) == "table" then key = legacyKey end
    end
    if type(entry) ~= "table" then return nil end
    local now = time and time() or 0
    local fetched = tonumber(entry.fetchedAt) or tonumber(cache.generatedAt) or 0
    local maxAge = tonumber(cache.maxAge) or 43200
    if now > 0 and fetched > 0 and now - fetched > maxAge then return nil end
    return entry, key
end

local function ScoreColor(score)
    score = tonumber(score) or 0
    if score >= 85 then return 0.72, 0.42, 1.00 end
    if score >= 70 then return 0.30, 0.84, 0.52 end
    if score >= 55 then return 0.96, 0.77, 0.25 end
    return 0.93, 0.34, 0.34
end

local function AppendCachedLines(fullName)
    local entry, key = GetFreshEntry(fullName)
    if not entry or tooltipKey == key then return end
    if not GameTooltip or not GameTooltip:IsShown() then return end

    tooltipKey = key
    local score = tonumber(entry.score) or 0
    local r, g, b = ScoreColor(score)
    GameTooltip:AddLine(" ")
    GameTooltip:AddDoubleLine(
        KL_ICON .. "  KL Score",
        string.format("%d/100 %s", score, tostring(entry.label or "")),
        0.36, 0.66, 1.00,
        r, g, b
    )

    local rioComponent = tonumber(entry.rioComponent)
    if rioComponent then
        local parts = { string.format("RIO %d", math.floor(rioComponent + 0.5)) }
        local wclComponent = tonumber(entry.wclComponent)
        if wclComponent then table.insert(parts, string.format("WCL %d", math.floor(wclComponent + 0.5))) end
        GameTooltip:AddDoubleLine(
            "KL bronnen", table.concat(parts, "  |  "),
            0.72, 0.72, 0.76, 0.82, 0.82, 0.86
        )
    end

    local pct = tonumber(entry.wclPercentile)
    if pct then
        local keyLevel = tonumber(entry.wclKey) or 0
        local runs = tonumber(entry.wclRuns) or 0
        GameTooltip:AddDoubleLine(
            "Warcraft Logs gemiddelde",
            string.format(
                "%d/100  |  +%d  |  %d run%s",
                math.floor(pct + 0.5), keyLevel, runs, runs == 1 and "" or "s"
            ),
            0.72, 0.72, 0.76,
            0.78, 0.62, 1.00
        )
    else
        GameTooltip:AddDoubleLine(
            "Warcraft Logs",
            "geen WCL • WCL-deel 0/100",
            0.72, 0.72, 0.76,
            0.55, 0.55, 0.60
        )
    end
    GameTooltip:AddLine("Cache van companion • /reload voor nieuwere online data", 0.45, 0.45, 0.50)
    GameTooltip:Show()
end

local function OnMemberEnter(self)
    local memberIdx = tonumber(self and self.memberIdx)
    local applicantID = self and self.applicantID
    local parent = self
    for _ = 1, 4 do
        if applicantID then break end
        parent = parent and parent.GetParent and parent:GetParent()
        applicantID = parent and parent.applicantID
    end
    if not memberIdx or not applicantID or not C_LFGList or not C_LFGList.GetApplicantMemberInfo then return end
    local ok, fullName = pcall(C_LFGList.GetApplicantMemberInfo, applicantID, memberIdx)
    if not ok or not fullName then return end
    if type(issecretvalue) == "function" and issecretvalue(fullName) then return end
    -- Raider.IO also hooks this button. Defer one frame so its lines are present
    -- first, making KeystoneLens appear immediately underneath them.
    if C_Timer and C_Timer.After then
        local button = self
        C_Timer.After(0, function()
            if button and button.IsMouseOver and button:IsMouseOver() then
                AppendCachedLines(fullName)
            end
        end)
    else
        AppendCachedLines(fullName)
    end
end

local function HookMember(button)
    if not button or hooked[button] then return end
    hooked[button] = true
    if button.HookScript then
        button:HookScript("OnEnter", OnMemberEnter)
    end
end

local function HookApplicantRow(row)
    if not row then return end

    -- Blizzard has used both named Member1..Member5 children and collections
    -- across Group Finder revisions. Support both, then fall back to direct
    -- children carrying memberIdx. This mirrors Raider.IO's member-button hook
    -- location without depending on one fragile FrameXML layout.
    for i = 1, 5 do
        HookMember(row["Member" .. i])
    end
    for _, field in ipairs({ "Members", "members", "MemberButtons", "memberButtons" }) do
        local members = row[field]
        if type(members) == "table" then
            for _, member in pairs(members) do HookMember(member) end
        end
    end
    if row.memberIdx then HookMember(row) end
    if type(row.GetChildren) == "function" then
        local children = { row:GetChildren() }
        for _, child in ipairs(children) do
            if child and child.memberIdx then HookMember(child) end
        end
    end
end

local function HookVisibleRows()
    local viewer = _G.LFGListFrame and _G.LFGListFrame.ApplicationViewer
    local scrollBox = viewer and viewer.ScrollBox
    if not scrollBox then return false end
    if type(scrollBox.GetFrames) == "function" then
        local frames = scrollBox:GetFrames()
        if type(frames) == "table" then
            for _, row in pairs(frames) do HookApplicantRow(row) end
        end
    elseif type(scrollBox.buttons) == "table" then
        for _, row in pairs(scrollBox.buttons) do HookApplicantRow(row) end
    end
    if not hooked[scrollBox] and type(scrollBox.RegisterCallback) == "function"
       and ScrollBoxListMixin and ScrollBoxListMixin.Event and ScrollBoxListMixin.Event.OnUpdate then
        hooked[scrollBox] = true
        scrollBox:RegisterCallback(ScrollBoxListMixin.Event.OnUpdate, HookVisibleRows)
    end
    return true
end

if GameTooltip and GameTooltip.HookScript then
    GameTooltip:HookScript("OnHide", function() tooltipKey = nil end)
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("LFG_LIST_APPLICANT_LIST_UPDATED")
frame:RegisterEvent("LFG_LIST_APPLICANT_UPDATED")
frame:SetScript("OnEvent", function(_, event)
    if event == "ADDON_LOADED" or event == "PLAYER_LOGIN" then
        if C_Timer and C_Timer.After then C_Timer.After(0, HookVisibleRows) else HookVisibleRows() end
        return
    end
    HookVisibleRows()
end)
