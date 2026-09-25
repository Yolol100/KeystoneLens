-- KeystoneLens: one compact Warcraft Logs Mythic+ line in the normal WoW/Raider.IO tooltip.
-- Raider.IO remains the owner of its score/profile rendering. KeystoneLens only appends
-- cached WCL DPS/HPS percentile data after Raider.IO has built the tooltip.
--
-- The cache is intentionally fail-closed: character, active LFG activity, specialization,
-- metric, cache version and freshness all have to match before anything is rendered.
-- New applicants do not need /reload: the addon reserves this row, sends its exact
-- screen coordinates through APS1, and the Companion paints the live WCL value there.

local _, KL = ...
KL = type(KL) == "table" and KL or {}

local hooked = setmetatable({}, { __mode = "k" })
local tooltipKey = nil
local unitTooltipRegistered = false
local raiderIOScoreHookRegistered = false
local raiderIOInjecting = false
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
    local normalizedRealm = NormalizeRealm(realm)
    local localRealm = CurrentRealm()
    local fullName = BuildFullName(name, normalizedRealm)
    local entry, key, cache = FindEntry(fullName)

    -- LFG may store a same-realm player as a short name. Only use that fallback
    -- when the displayed unit is definitely on the local realm; never let a
    -- cross-realm player collide with a same-name local applicant.
    if not entry
       and (not normalizedRealm
            or (localRealm and string.lower(normalizedRealm) == string.lower(localRealm))) then
        entry, key, cache = FindEntry(name)
    end
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

local function GetApplicantIdentity(button)
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
    applicantID = tonumber(applicantID)
    memberIdx = tonumber(memberIdx)
    if not specID or specID <= 0
       or not applicantID or applicantID <= 0
       or not memberIdx or memberIdx <= 0 then
        return nil
    end

    return {
        applicantID = applicantID,
        memberIdx = memberIdx,
        fullName = fullName,
        specID = specID,
    }
end

local function ClampNorm16(value)
    value = tonumber(value) or 0
    if value < 0 then value = 0 end
    if value > 1 then value = 1 end
    return math.floor(value * 65535 + 0.5)
end

local function NormalizedFrameRect(frame)
    if not frame or not UIParent
       or type(frame.GetLeft) ~= "function"
       or type(frame.GetBottom) ~= "function"
       or type(frame.GetWidth) ~= "function"
       or type(frame.GetHeight) ~= "function"
       or type(UIParent.GetWidth) ~= "function"
       or type(UIParent.GetHeight) ~= "function" then
        return nil
    end

    local parentW, parentH = UIParent:GetWidth(), UIParent:GetHeight()
    local left, bottom = frame:GetLeft(), frame:GetBottom()
    local width, height = frame:GetWidth(), frame:GetHeight()
    if not parentW or not parentH or parentW <= 0 or parentH <= 0
       or not left or not bottom or not width or not height
       or width <= 0 or height <= 0 then
        return nil
    end

    return {
        x = ClampNorm16(left / parentW),
        y = ClampNorm16(bottom / parentH),
        w = ClampNorm16(width / parentW),
        h = ClampNorm16(height / parentH),
    }
end

local function RequestLiveHoverValue(tooltip, owner, identity, lineIndex)
    if type(KL.RequestLiveHover) ~= "function"
       or not tooltip or not owner or not identity or not lineIndex then
        return
    end

    local activityID = CurrentListingActivityID()
    if not activityID then return end

    local leftLine = _G["GameTooltipTextLeft" .. tostring(lineIndex)]
    if not leftLine then return end

    local lineRect = NormalizedFrameRect(leftLine)
    local ownerRect = NormalizedFrameRect(owner)
    if not lineRect or not ownerRect then return end

    -- Reserve the right-most third of this exact tooltip row for the Companion.
    -- The transparent/no-activate overlay paints only inside this rectangle.
    local tooltipRect = NormalizedFrameRect(tooltip)
    if not tooltipRect then return end
    local valueWidth = math.max(math.floor(tooltipRect.w * 0.34), 1)
    local valueX = math.max(0, math.min(65535, tooltipRect.x + tooltipRect.w - valueWidth))

    KL.RequestLiveHover({
        applicantID = identity.applicantID,
        memberIdx = identity.memberIdx,
        name = identity.fullName,
        specID = identity.specID,
        activityID = activityID,
        valueX = valueX,
        valueY = lineRect.y,
        valueW = valueWidth,
        valueH = math.max(lineRect.h, 1),
        ownerX = ownerRect.x,
        ownerY = ownerRect.y,
        ownerW = ownerRect.w,
        ownerH = ownerRect.h,
    })
end

local function AppendApplicantLine(tooltip, owner)
    if not tooltip or tooltip ~= GameTooltip or not owner then return false end

    local identity = GetApplicantIdentity(owner)
    if not identity then return false end

    -- Group Finder is live-only. Never draw a potentially stale Data.lua number
    -- underneath the Companion overlay; reserve an empty right-hand cell instead.
    local uniqueKey = "live:" .. identity.fullName .. ":" .. tostring(identity.specID)
    if tooltipKey == uniqueKey then return false end
    tooltipKey = uniqueKey
    tooltip:AddDoubleLine(
        KL_ICON .. " Warcraft Logs M+",
        "",
        0.72, 0.72, 0.76,
        0.55, 0.55, 0.55
    )

    tooltip:Show()
    local lineIndex = type(tooltip.NumLines) == "function" and tooltip:NumLines() or nil
    if lineIndex then
        local function requestIfStillHovered()
            if owner and owner.IsMouseOver and owner:IsMouseOver()
               and tooltip and tooltip:IsShown() then
                RequestLiveHoverValue(tooltip, owner, identity, lineIndex)
            end
        end
        if C_Timer and type(C_Timer.After) == "function" then
            C_Timer.After(0, requestIfStillHovered)
        else
            requestIfStillHovered()
        end
    end
    return true
end

local function OnMemberEnter(self)
    local function appendIfStillHovered()
        if not self or not self.IsMouseOver or not self:IsMouseOver()
           or not GameTooltip or not GameTooltip:IsShown() then
            return
        end
        AppendApplicantLine(GameTooltip, self)
    end

    -- Fallback ordering path: Raider.IO builds its LFG tooltip synchronously.
    -- The dedicated AddDoubleLine hook below normally reserves KeystoneLens
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
        raiderIOInjecting = true
        local appended = AppendApplicantLine(tooltip, owner)
        raiderIOInjecting = false
        if appended then return true end
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
