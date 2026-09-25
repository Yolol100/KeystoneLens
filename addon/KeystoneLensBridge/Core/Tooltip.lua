-- KeystoneLens: compact Warcraft Logs Mythic+ tooltip.
-- The Bridge only renders cached WCL role-performance percentiles.
-- No Raider.IO score, Blizzard score, combined score, confidence or extra UI.

local hooked = setmetatable({}, { __mode = "k" })
local tooltipKey = nil
local KL_ICON = "|TInterface\\AddOns\\KeystoneLensBridge\\Media\\KeystoneLensIcon:16:16:0:0|t"
local REQUIRED_CACHE_VERSION = 3

local function IsSecretValue(value)
    local api = _G.issecretvalue
    if api == nil then return false end
    if type(api) ~= "function" then return true end
    local ok, secret = pcall(api, value)
    return not ok or secret == true
end

local function NormalizeFullName(fullName)
    if IsSecretValue(fullName) or type(fullName) ~= "string" or fullName == "" then return nil end
    return fullName
end

local function CurrentListingActivityID()
    if not C_LFGList or type(C_LFGList.GetActiveEntryInfo) ~= "function" then return nil end

    local ok, entry = pcall(C_LFGList.GetActiveEntryInfo)
    if not ok or IsSecretValue(entry) or type(entry) ~= "table" then return nil end

    local activityIDs = entry.activityIDs
    if IsSecretValue(activityIDs) or type(activityIDs) ~= "table" then return nil end

    local activityID = activityIDs[1]
    if IsSecretValue(activityID) then return nil end
    activityID = tonumber(activityID)
    return activityID and activityID > 0 and activityID or nil
end

local function GetFreshEntry(fullName, specID)
    local cache = _G.KeystoneLensTooltipCacheV3
    if type(cache) ~= "table"
       or tonumber(cache.version) ~= REQUIRED_CACHE_VERSION
       or type(cache.entries) ~= "table" then
        return nil
    end

    specID = IsSecretValue(specID) and nil or tonumber(specID)
    if not specID or specID <= 0 then return nil end

    local activityID = CurrentListingActivityID()
    if not activityID then return nil end

    local key = NormalizeFullName(fullName)
    if not key then return nil end

    local entry = cache.entries[key]
    if type(entry) ~= "table" then
        local legacyKey = string.lower(key)
        entry = cache.entries[legacyKey]
        if type(entry) == "table" then key = legacyKey end
    end
    if type(entry) ~= "table" then return nil end

    if tonumber(entry.activityID) ~= activityID or tonumber(entry.specID) ~= specID then
        return nil
    end

    local percentile = tonumber(entry.percentile)
    if not percentile or percentile < 0 or percentile > 100 then return nil end

    local metric = tostring(entry.metric or ""):upper()
    if metric ~= "DPS" and metric ~= "HPS" then return nil end

    local now = time and time() or 0
    local fetched = tonumber(entry.fetchedAt) or tonumber(cache.generatedAt) or 0
    local maxAge = tonumber(cache.maxAge) or 43200
    if now > 0 and fetched > 0 and now - fetched > maxAge then return nil end

    return entry, key
end

local function PercentileColor(percentile)
    percentile = tonumber(percentile) or 0
    if percentile >= 100 then return 0.90, 0.80, 0.50 end
    if percentile >= 99 then return 0.89, 0.41, 0.66 end
    if percentile >= 95 then return 1.00, 0.50, 0.00 end
    if percentile >= 75 then return 0.64, 0.21, 0.93 end
    if percentile >= 50 then return 0.00, 0.44, 0.87 end
    if percentile >= 25 then return 0.12, 1.00, 0.00 end
    return 0.40, 0.40, 0.40
end

local function AppendCachedLine(fullName, specID)
    local entry, key = GetFreshEntry(fullName, specID)
    if not entry or not GameTooltip or not GameTooltip:IsShown() then return end

    local uniqueKey = key .. ":" .. tostring(specID)
    if tooltipKey == uniqueKey then return end
    tooltipKey = uniqueKey

    local percentile = tonumber(entry.percentile) or 0
    local metric = tostring(entry.metric or "DPS"):upper()
    local label = metric == "HPS" and "Healing" or "DPS"
    local r, g, b = PercentileColor(percentile)

    GameTooltip:AddDoubleLine(
        KL_ICON .. " Warcraft Logs M+",
        string.format("%s %d%%", label, math.floor(percentile + 0.5)),
        0.72, 0.72, 0.76,
        r, g, b
    )
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

    if not memberIdx or not applicantID or not C_LFGList or not C_LFGList.GetApplicantMemberInfo then
        return
    end

    local results = { pcall(C_LFGList.GetApplicantMemberInfo, applicantID, memberIdx) }
    if results[1] ~= true then return end

    local fullName = results[2]
    local specID = results[17]
    if not NormalizeFullName(fullName) or IsSecretValue(specID) then return end

    specID = tonumber(specID)
    if not specID or specID <= 0 then return end

    if C_Timer and C_Timer.After then
        local button = self
        C_Timer.After(0, function()
            if button and button.IsMouseOver and button:IsMouseOver() then
                AppendCachedLine(fullName, specID)
            end
        end)
    else
        AppendCachedLine(fullName, specID)
    end
end

local function HookMember(button)
    if not button or hooked[button] then return end
    hooked[button] = true
    if button.HookScript then button:HookScript("OnEnter", OnMemberEnter) end
end

local function HookApplicantRow(row)
    if not row then return end

    for i = 1, 5 do HookMember(row["Member" .. i]) end

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

    if not hooked[scrollBox]
       and type(scrollBox.RegisterCallback) == "function"
       and ScrollBoxListMixin
       and ScrollBoxListMixin.Event
       and ScrollBoxListMixin.Event.OnUpdate then
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
        if C_Timer and C_Timer.After then
            C_Timer.After(0, HookVisibleRows)
        else
            HookVisibleRows()
        end
        return
    end
    HookVisibleRows()
end)
