-- KeystoneLens: one compact Warcraft Logs Mythic+ line in the normal WoW/Raider.IO tooltip.
-- Raider.IO remains the owner of its score/profile rendering. KeystoneLens only appends
-- cached WCL DPS/HPS percentile data after Raider.IO has built the tooltip.
--
-- The cache is intentionally fail-closed: character, active LFG activity, specialization,
-- metric, cache version and freshness all have to match before anything is rendered.

local hooked = setmetatable({}, { __mode = "k" })
local tooltipKey = nil
local unitTooltipRegistered = false
local raiderIOScoreHookRegistered = false
local raiderIOInjecting = false
local KL_ICON = "|TInterface\\AddOns\\KeystoneLensBridge\\Media\\KeystoneLensIcon:16:16:0:0|t"
local UNIT_HOOK_DELAY_SECONDS = 1.0

local function IsSecretValue(value)
    local api = _G.issecretvalue
    if api == nil then return false end
    if type(api) ~= "function" then return true end
    local ok, secret = pcall(api, value)
    return not ok or secret == true
end

local function NormalizeFullName(fullName)
    if IsSecretValue(fullName) or type(fullName) ~= "string" or fullName == "" then
        return nil
    end
    return fullName
end

local function NormalizeRealm(realm)
    if IsSecretValue(realm) or type(realm) ~= "string" or realm == "" then
        return nil
    end
    return realm:gsub("%s+", "")
end

local function CurrentRealm()
    if type(GetNormalizedRealmName) ~= "function" then return nil end
    local ok, realm = pcall(GetNormalizedRealmName)
    if not ok then return nil end
    return NormalizeRealm(realm)
end

local function BuildFullName(name, realm)
    if IsSecretValue(name) or type(name) ~= "string" or name == "" then
        return nil
    end

    realm = NormalizeRealm(realm) or CurrentRealm()
    if realm then return name .. "-" .. realm end
    return name
end

local function CurrentListingActivityID()
    if not C_LFGList or type(C_LFGList.GetActiveEntryInfo) ~= "function" then
        return nil
    end

    local ok, entry = pcall(C_LFGList.GetActiveEntryInfo)
    if not ok or IsSecretValue(entry) or type(entry) ~= "table" then
        return nil
    end

    local activityIDs = entry.activityIDs
    if IsSecretValue(activityIDs) or type(activityIDs) ~= "table" then
        return nil
    end

    local activityID = activityIDs[1]
    if IsSecretValue(activityID) then return nil end
    activityID = tonumber(activityID)
    return activityID and activityID > 0 and activityID or nil
end

local REQUIRED_DATASET_VERSION = 4
local REQUIRED_SEASON = "midnight-s2"

local function DungeonKey(value)
    if IsSecretValue(value) or type(value) ~= "string" or value == "" then
        return nil
    end
    local key = string.lower(value):gsub("[^%w]", "")
    return key ~= "" and key or nil
end

local function CurrentDungeonKey()
    local activityID = CurrentListingActivityID()
    if not activityID
       or not C_LFGList
       or type(C_LFGList.GetActivityInfoTable) ~= "function" then
        return nil
    end

    local ok, info = pcall(C_LFGList.GetActivityInfoTable, activityID)
    if not ok or IsSecretValue(info) or type(info) ~= "table" then
        return nil
    end
    return DungeonKey(info.fullName or info.name or info.shortName)
end

local function Dataset()
    local data = _G.KeystoneLensPreloadV4
    if type(data) ~= "table"
       or tonumber(data.version) ~= REQUIRED_DATASET_VERSION
       or data.season ~= REQUIRED_SEASON
       or type(data.entries) ~= "table"
       or type(data.unitEntries) ~= "table" then
        return nil
    end

    local region = tonumber(data.region)
    if region and region > 0 and type(GetCurrentRegion) == "function" then
        local ok, currentRegion = pcall(GetCurrentRegion)
        if not ok or tonumber(currentRegion) ~= region then
            return nil
        end
    end

    local now = type(time) == "function" and time() or 0
    local generatedAt = tonumber(data.generatedAt) or 0
    local maxAge = tonumber(data.maxAge) or 0
    if maxAge <= 0 then return nil end
    if now > 0 and generatedAt > 0 and now - generatedAt > maxAge then
        return nil
    end
    return data
end

local function ValidateTuple(tuple, data)
    if type(tuple) ~= "table" or type(data) ~= "table" then return nil end
    local code = tuple[1]
    local percentile = tonumber(tuple[2])
    local fetchedAt = tonumber(tuple[3]) or tonumber(data.generatedAt) or 0
    if code ~= "D" and code ~= "H" then return nil end
    if not percentile or percentile < 0 or percentile > 100 then return nil end

    local maxAge = tonumber(data.maxAge) or 0
    local now = type(time) == "function" and time() or 0
    if maxAge <= 0 then return nil end
    if now > 0 and fetchedAt > 0 and now - fetchedAt > maxAge then return nil end

    return {
        metric = code == "H" and "HPS" or "DPS",
        percentile = percentile,
        fetchedAt = fetchedAt,
    }
end

local function ApplicantKey(fullName, specID, dungeonKey)
    local normalized = NormalizeFullName(fullName)
    specID = IsSecretValue(specID) and nil or tonumber(specID)
    if not normalized or not specID or specID <= 0 or not dungeonKey then return nil end
    return normalized .. "|" .. tostring(specID) .. "|" .. dungeonKey
end

local function UnitKey(fullName, dungeonKey)
    local normalized = NormalizeFullName(fullName)
    if not normalized or not dungeonKey then return nil end
    return normalized .. "|" .. dungeonKey
end

local function GetFreshEntry(fullName, specID)
    local data = Dataset()
    local dungeonKey = CurrentDungeonKey()
    local key = ApplicantKey(fullName, specID, dungeonKey)
    if not data or not key then return nil end

    local entry = ValidateTuple(data.entries[key], data)
    if not entry then return nil end
    return entry, key, tonumber(specID)
end

local function GetFreshEntryForUnit(name, realm)
    local data = Dataset()
    local dungeonKey = CurrentDungeonKey()
    if not data or not dungeonKey then return nil end

    local normalizedRealm = NormalizeRealm(realm)
    local fullName = BuildFullName(name, normalizedRealm)
    local key = UnitKey(fullName, dungeonKey)
    local entry = key and ValidateTuple(data.unitEntries[key], data) or nil

    local localRealm = CurrentRealm()
    if not entry
       and (not normalizedRealm
            or (localRealm and string.lower(normalizedRealm) == string.lower(localRealm))) then
        key = UnitKey(BuildFullName(name, localRealm), dungeonKey)
        entry = key and ValidateTuple(data.unitEntries[key], data) or nil
    end

    if not entry then return nil end
    return entry, key, nil
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

local function AppendEntryLine(tooltip, entry, key, specID)
    if not tooltip or type(tooltip.AddDoubleLine) ~= "function" or not entry or not key then
        return false
    end

    local percentile = tonumber(entry.percentile) or 0
    local metric = tostring(entry.metric or "DPS"):upper()
    local uniqueKey = table.concat({
        tostring(key),
        tostring(specID or entry.specID or 0),
        metric,
        string.format("%.2f", percentile),
    }, ":")

    if tooltipKey == uniqueKey then return false end
    tooltipKey = uniqueKey

    local label = metric == "HPS" and "Healing" or "DPS"
    local r, g, b = PercentileColor(percentile)

    tooltip:AddDoubleLine(
        KL_ICON .. " Warcraft Logs M+",
        string.format("%s %d%%", label, math.floor(percentile + 0.5)),
        0.72, 0.72, 0.76,
        r, g, b
    )
    return true
end

local function CleanUnitGUID(unit)
    if type(UnitGUID) ~= "function" then return nil end
    local ok, guid = pcall(UnitGUID, unit)
    if not ok or IsSecretValue(guid) or type(guid) ~= "string" or guid == "" then
        return nil
    end
    return guid
end

local function GetTooltipGUID(tooltip)
    if not tooltip or type(tooltip.GetPrimaryTooltipData) ~= "function" then
        return nil
    end
    local ok, data = pcall(tooltip.GetPrimaryTooltipData, tooltip)
    if not ok or IsSecretValue(data) or type(data) ~= "table" then return nil end
    local guid = data.guid
    if IsSecretValue(guid) or type(guid) ~= "string" or guid == "" then return nil end
    return guid
end

local function GetGroupUnitTokenFromGUID(guid)
    if not guid then return nil end
    if CleanUnitGUID("player") == guid then return "player" end

    local inRaid = false
    if type(IsInRaid) == "function" then
        local ok, value = pcall(IsInRaid)
        if ok and not IsSecretValue(value) and value == true then
            inRaid = true
        end
    end

    local prefix = inRaid and "raid" or "party"
    local limit = inRaid and 40 or 4
    for index = 1, limit do
        local unit = prefix .. tostring(index)
        if CleanUnitGUID(unit) == guid then return unit end
    end
    return nil
end

local function GetDisplayedUnit(tooltip)
    if TooltipUtil and type(TooltipUtil.GetDisplayedUnit) == "function" then
        local ok, _, unit = pcall(TooltipUtil.GetDisplayedUnit, tooltip)
        if ok and unit and not IsSecretValue(unit) then return unit end
    end

    if tooltip and type(tooltip.GetUnit) == "function" then
        local ok, _, unit = pcall(tooltip.GetUnit, tooltip)
        if ok and unit and not IsSecretValue(unit) then return unit end
    end

    local guid = GetTooltipGUID(tooltip)
    if not guid then return nil end

    if type(UnitTokenFromGUID) == "function" then
        local ok, unit = pcall(UnitTokenFromGUID, guid)
        if ok and unit and not IsSecretValue(unit) then return unit end
    end
    return GetGroupUnitTokenFromGUID(guid)
end

local function OnUnitTooltip(tooltip)
    if tooltip ~= GameTooltip then return end

    local unit = GetDisplayedUnit(tooltip)
    if not unit then return end

    local okPlayer, isPlayer = pcall(UnitIsPlayer, unit)
    if not okPlayer or not isPlayer then return end

    local okName, name, realm = pcall(UnitFullName, unit)
    if not okName or IsSecretValue(name) or IsSecretValue(realm) or not name then return end

    local entry, key, specID = GetFreshEntryForUnit(name, realm)
    if not entry then return end
    AppendEntryLine(tooltip, entry, key, specID)
end

local function RegisterUnitTooltipHook()
    if unitTooltipRegistered then return end
    unitTooltipRegistered = true

    if TooltipDataProcessor
       and type(TooltipDataProcessor.AddTooltipPostCall) == "function"
       and Enum and Enum.TooltipDataType and Enum.TooltipDataType.Unit then
        TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Unit, OnUnitTooltip)
    elseif GameTooltip and type(GameTooltip.HookScript) == "function" then
        GameTooltip:HookScript("OnTooltipSetUnit", OnUnitTooltip)
    end
end

local function ResolveApplicantContext(button)
    if not button then return nil end

    local memberIdx = tonumber(button.memberIdx)
    local applicantID = button.applicantID
    local parent = button

    for _ = 1, 4 do
        if applicantID then
            if not memberIdx and type(parent.Members) == "table" then
                for index, member in pairs(parent.Members) do
                    if member == button then
                        memberIdx = tonumber(index)
                        break
                    end
                end
            end
            if memberIdx then return applicantID, memberIdx end
        end

        parent = parent and parent.GetParent and parent:GetParent()
        applicantID = parent and parent.applicantID
    end

    return nil
end

local function GetApplicantEntry(button)
    local applicantID, memberIdx = ResolveApplicantContext(button)
    if not applicantID or not memberIdx
       or IsSecretValue(applicantID)
       or not C_LFGList
       or type(C_LFGList.GetApplicantMemberInfo) ~= "function" then
        return nil
    end

    local results = { pcall(C_LFGList.GetApplicantMemberInfo, applicantID, memberIdx) }
    if results[1] ~= true then return nil end

    local fullName = results[2]
    local specID = results[17] -- pcall adds one slot before the API's 16th specID return.
    if not NormalizeFullName(fullName) or IsSecretValue(specID) then return nil end

    specID = tonumber(specID)
    if not specID or specID <= 0 then return nil end
    return GetFreshEntry(fullName, specID)
end

local function OnMemberEnter(self)
    local function appendIfStillHovered()
        if not self or not self.IsMouseOver or not self:IsMouseOver()
           or not GameTooltip or not GameTooltip:IsShown() then
            return
        end

        local entry, key, specID = GetApplicantEntry(self)
        if entry and AppendEntryLine(GameTooltip, entry, key, specID) then
            GameTooltip:Show()
        end
    end

    -- Fallback ordering path: Raider.IO builds its LFG tooltip synchronously.
    -- The dedicated AddDoubleLine hook below normally inserts KeystoneLens
    -- immediately after Raider.IO's M+ score. This next-frame append keeps the
    -- feature working when Raider.IO changes its score label or is not installed.
    if C_Timer and type(C_Timer.After) == "function" then
        C_Timer.After(0, appendIfStillHovered)
    else
        appendIfStillHovered()
    end
end

local function IsRaiderIOScoreLabel(leftText)
    if IsSecretValue(leftText) or type(leftText) ~= "string" then return false end
    local plain = leftText:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")

    -- Raider.IO's current-season/default headline is "Raider.IO M+ Score".
    -- In its Best Season / Best Run headline modes, the current-season line is
    -- "Current M+ Score". Deliberately ignore "Raider.IO M+ Score (S#)" so a
    -- current WCL percentile never sits under a previous-season headline.
    return plain == "Raider.IO M+ Score" or plain == "Current M+ Score"
end

local function GetTooltipOwner(tooltip)
    if not tooltip or type(tooltip.GetOwner) ~= "function" then return nil end
    local ok, owner = pcall(tooltip.GetOwner, tooltip)
    if ok and owner and not IsSecretValue(owner) then return owner end
    return nil
end

local function AppendCurrentTooltipContext(tooltip)
    if raiderIOInjecting or tooltip ~= GameTooltip then return false end

    local owner = GetTooltipOwner(tooltip)
    if owner then
        local entry, key, specID = GetApplicantEntry(owner)
        if entry then
            raiderIOInjecting = true
            local appended = AppendEntryLine(tooltip, entry, key, specID)
            raiderIOInjecting = false
            return appended
        end
    end

    local unit = GetDisplayedUnit(tooltip)
    if not unit then return false end

    local okPlayer, isPlayer = pcall(UnitIsPlayer, unit)
    if not okPlayer or not isPlayer then return false end

    local okName, name, realm = pcall(UnitFullName, unit)
    if not okName or IsSecretValue(name) or IsSecretValue(realm) or not name then
        return false
    end

    local entry, key, specID = GetFreshEntryForUnit(name, realm)
    if not entry then return false end

    raiderIOInjecting = true
    local appended = AppendEntryLine(tooltip, entry, key, specID)
    raiderIOInjecting = false
    return appended
end

local function RegisterRaiderIOScoreHook()
    if raiderIOScoreHookRegistered
       or type(hooksecurefunc) ~= "function"
       or not GameTooltip
       or type(GameTooltip.AddDoubleLine) ~= "function" then
        return
    end

    raiderIOScoreHookRegistered = true
    hooksecurefunc(GameTooltip, "AddDoubleLine", function(tooltip, leftText)
        if raiderIOInjecting or not IsRaiderIOScoreLabel(leftText) then return end
        AppendCurrentTooltipContext(tooltip)
    end)
end

local function HookMember(button)
    if not button or hooked[button] then return end
    if type(button.HookScript) ~= "function" then return end
    hooked[button] = true
    button:HookScript("OnEnter", OnMemberEnter)
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

local function HookRows(buttons)
    if type(buttons) ~= "table" then return end
    for _, row in pairs(buttons) do HookApplicantRow(row) end
end

local function HookVisibleRows()
    local viewer = _G.LFGListFrame and _G.LFGListFrame.ApplicationViewer
    local scrollBox = viewer and viewer.ScrollBox
    if not scrollBox then return false end

    if type(scrollBox.ForEachFrame) == "function" then
        pcall(scrollBox.ForEachFrame, scrollBox, HookApplicantRow)
    elseif type(scrollBox.GetFrames) == "function" then
        local ok, frames = pcall(scrollBox.GetFrames, scrollBox)
        if ok then HookRows(frames) end
    elseif type(scrollBox.buttons) == "table" then
        HookRows(scrollBox.buttons)
    end

    if hooked[scrollBox] then return true end
    hooked[scrollBox] = true

    -- Current Raider.IO uses this same public ScrollBox utility to follow
    -- recycled LFG frames. Prefer it when available, then fall back to the
    -- lower-level callback used by older UI revisions.
    if ScrollBoxUtil and type(ScrollBoxUtil.OnViewFramesChanged) == "function" then
        pcall(ScrollBoxUtil.OnViewFramesChanged, ScrollBoxUtil, scrollBox, HookRows)
    elseif type(scrollBox.RegisterCallback) == "function"
       and ScrollBoxListMixin
       and ScrollBoxListMixin.Event then
        local event = ScrollBoxListMixin.Event.OnDataRangeChanged
            or ScrollBoxListMixin.Event.OnUpdate
        if event then
            pcall(scrollBox.RegisterCallback, scrollBox, event, HookVisibleRows)
        end
    end

    return true
end

local function ResetTooltipKey()
    tooltipKey = nil
end

if GameTooltip and type(GameTooltip.HookScript) == "function" then
    GameTooltip:HookScript("OnHide", ResetTooltipKey)
    GameTooltip:HookScript("OnTooltipCleared", ResetTooltipKey)
end

local function Schedule(delay, callback)
    if C_Timer and type(C_Timer.After) == "function" then
        C_Timer.After(delay or 0, callback)
    else
        callback()
    end
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("LFG_LIST_APPLICANT_LIST_UPDATED")
frame:RegisterEvent("LFG_LIST_APPLICANT_UPDATED")
frame:SetScript("OnEvent", function(_, event, addonName)
    if event == "PLAYER_LOGIN" then
        -- Raider.IO is an OptionalDep, so if it is enabled it loads before
        -- KeystoneLens. The small delay additionally ensures our unit post-call
        -- is registered after Raider.IO's own tooltip renderer.
        Schedule(0, RegisterRaiderIOScoreHook)
        Schedule(UNIT_HOOK_DELAY_SECONDS, RegisterUnitTooltipHook)
        Schedule(0, HookVisibleRows)
        return
    end

    if event == "ADDON_LOADED" then
        if addonName == "Blizzard_GroupFinder"
           or addonName == "Blizzard_LFGList"
           or addonName == "RaiderIO" then
            Schedule(0, HookVisibleRows)
        end
        return
    end

    HookVisibleRows()
end)
