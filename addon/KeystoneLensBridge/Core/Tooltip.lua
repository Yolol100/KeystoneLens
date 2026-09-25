-- KeystoneLens: one compact Warcraft Logs Mythic+ line in the normal WoW/Raider.IO tooltip.
-- Raider.IO remains the owner of its score/profile rendering. KeystoneLens only appends
-- cached WCL DPS/HPS percentile data after Raider.IO has built the tooltip.
--
-- The cache is intentionally fail-closed: character, active LFG activity, specialization,
-- metric, cache version and freshness all have to match before anything is rendered.

local hooked = setmetatable({}, { __mode = "k" })
local tooltipKey = nil
local unitTooltipRegistered = false
local KL_ICON = "|TInterface\\AddOns\\KeystoneLensBridge\\Media\\KeystoneLensIcon:16:16:0:0|t"
local REQUIRED_CACHE_VERSION = 3
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

local function BuildFullName(name, realm)
    if IsSecretValue(name) or type(name) ~= "string" or name == "" then
        return nil
    end

    realm = NormalizeRealm(realm)
    if not realm and type(GetNormalizedRealmName) == "function" then
        local ok, currentRealm = pcall(GetNormalizedRealmName)
        if ok then realm = NormalizeRealm(currentRealm) end
    end

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

local function Cache()
    local cache = _G.KeystoneLensTooltipCacheV3
    if type(cache) ~= "table"
       or tonumber(cache.version) ~= REQUIRED_CACHE_VERSION
       or type(cache.entries) ~= "table" then
        return nil
    end
    return cache
end

local function FindEntry(fullName)
    local cache = Cache()
    local key = NormalizeFullName(fullName)
    if not cache or not key then return nil end

    local entry = cache.entries[key]
    if type(entry) == "table" then
        return entry, key, cache
    end

    local lowerKey = string.lower(key)
    entry = cache.entries[lowerKey]
    if type(entry) == "table" then
        return entry, lowerKey, cache
    end

    -- UnitFullName can include the local realm while some LFG payloads are short names.
    -- The generated cache is intentionally tiny (current applicants only), so this
    -- bounded fallback is safe and avoids silently missing same-realm players.
    local shortName = key:match("^([^-]+)")
    if shortName and shortName ~= key then
        entry = cache.entries[shortName] or cache.entries[string.lower(shortName)]
        if type(entry) == "table" then
            return entry, shortName, cache
        end
    end

    return nil
end

local function ValidateEntry(entry, cache, activityID, specID)
    if type(entry) ~= "table" or type(cache) ~= "table" then return nil end

    activityID = tonumber(activityID)
    if not activityID or activityID <= 0 or tonumber(entry.activityID) ~= activityID then
        return nil
    end

    if specID ~= nil then
        specID = IsSecretValue(specID) and nil or tonumber(specID)
        if not specID or specID <= 0 or tonumber(entry.specID) ~= specID then
            return nil
        end
    else
        specID = tonumber(entry.specID)
        if not specID or specID <= 0 then return nil end
    end

    local percentile = tonumber(entry.percentile)
    if not percentile or percentile < 0 or percentile > 100 then return nil end

    local metric = tostring(entry.metric or ""):upper()
    if metric ~= "DPS" and metric ~= "HPS" then return nil end

    local now = type(time) == "function" and time() or 0
    local fetched = tonumber(entry.fetchedAt) or tonumber(cache.generatedAt) or 0
    local maxAge = tonumber(cache.maxAge) or 43200
    if maxAge <= 0 then return nil end
    if now > 0 and fetched > 0 and now - fetched > maxAge then return nil end

    return entry, specID
end

local function GetFreshEntry(fullName, specID)
    local entry, key, cache = FindEntry(fullName)
    if not entry then return nil end

    local activityID = CurrentListingActivityID()
    if not activityID then return nil end

    entry, specID = ValidateEntry(entry, cache, activityID, specID)
    if not entry then return nil end
    return entry, key, specID
end

local function GetFreshEntryForUnit(name, realm)
    local fullName = BuildFullName(name, realm)
    local entry, key, cache = FindEntry(fullName)
    if not entry then return nil end

    local activityID = CurrentListingActivityID()
    if not activityID then return nil end

    local specID
    entry, specID = ValidateEntry(entry, cache, activityID, nil)
    if not entry then return nil end
    return entry, key, specID
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

local function AppendCachedLine(fullName, specID)
    if not GameTooltip or not GameTooltip:IsShown() then return false end
    local entry, key, resolvedSpecID = GetFreshEntry(fullName, specID)
    if not entry then return false end
    if AppendEntryLine(GameTooltip, entry, key, resolvedSpecID) then
        GameTooltip:Show()
        return true
    end
    return false
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
    return nil
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

local function OnMemberEnter(self)
    local applicantID, memberIdx = ResolveApplicantContext(self)
    if not applicantID or not memberIdx
       or IsSecretValue(applicantID)
       or not C_LFGList
       or type(C_LFGList.GetApplicantMemberInfo) ~= "function" then
        return
    end

    local results = { pcall(C_LFGList.GetApplicantMemberInfo, applicantID, memberIdx) }
    if results[1] ~= true then return end

    local fullName = results[2]
    local specID = results[17] -- pcall adds one slot before the API's 16th specID return.
    if not NormalizeFullName(fullName) or IsSecretValue(specID) then return end

    specID = tonumber(specID)
    if not specID or specID <= 0 then return end

    local function appendIfStillHovered()
        if self and self.IsMouseOver and self:IsMouseOver()
           and GameTooltip and GameTooltip:IsShown() then
            AppendCachedLine(fullName, specID)
        end
    end

    -- Raider.IO builds its LFG tooltip synchronously. Deferring to the next
    -- frame makes KeystoneLens append after Raider.IO instead of competing
    -- with or rebuilding its tooltip.
    if C_Timer and type(C_Timer.After) == "function" then
        C_Timer.After(0, appendIfStillHovered)
    else
        appendIfStillHovered()
    end
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
