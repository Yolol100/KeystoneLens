-- KeystoneLens transport (forked from ApplicantScout) — encodes Mythic+ applicant
-- snapshots as QR frames and triggers Screenshot() for the external companion.
-- Raider.IO data is read locally in WoW; Warcraft Logs enrichment happens only
-- in the companion. The QR is normally transient and can be moved for support.
--
-- WHY raw frame, not Ace3: Ace3 shares CallbackHandler-1.0 with other addons
-- (BetterBags, AlterEgo, ...); their taint contaminates our handler stack and
-- can block protected-mode APIs. Raw frame + NewTicker drains the dirty flag
-- from a clean C-side scheduler, immune to peer-addon taint propagation.
--
-- WHY screenshot transport, not chatlog/SendChatMessage: WoW chatlog delivery
-- is buffered and unsuitable for real-time addon-to-companion transport in
-- Midnight 12.x. Screenshot() is used as the addon-safe optical handoff to the
-- local companion, with no chat anti-spam or chat-log buffering. KeystoneLens
-- takes a short PNG-format lease so the transport QR stays lossless and can be
-- rendered as a compact one-physical-pixel-per-module QR.
--
-- WHY QR over custom pixel marker: Reed-Solomon ECC built in (15% recovery at
-- level M); industry-standard finder/alignment patterns survive any DPI scale,
-- rotation, partial occlusion. Custom marker had zero error correction and
-- broke on dark-terrain backgrounds + non-integer DPI scales.

local addonName, KL = ...
KL = type(KL) == "table" and KL or {}
local CapturePolicy = KL.CapturePolicy
if type(CapturePolicy) ~= "table" then return end
local ADDON_VERSION = (C_AddOns and C_AddOns.GetAddOnMetadata or GetAddOnMetadata)(addonName, "Version") or "?"

local DB_DEFAULTS = {
    enabled = true,
    debug = false,
    -- Legacy key kept only so old SavedVariables can be normalized away.
    -- Visual QR support mode is session-only in 0.9.3: an old debug toggle
    -- must never make the transport stay visible after a reload.
    qrAlwaysVisible = false,
    -- One-shot migration sentinel. Existing installs may have `debug=true`
    -- stuck from a prior `/klbridge debug on` (default flipped from "on-stuck"
    -- to "off after explicit toggle" in this version). When the key is
    -- absent we force `debug=false` exactly once, then mark migrated so
    -- subsequent user toggles persist normally.
    debugDefaultMigrated = false,
    -- Pre-capture screenshot CVar values. Each QR screenshot takes a short
    -- lossless-PNG lease and restores the user's prior value afterwards;
    -- persistence lets the next load recover if a reload interrupts a lease.
    -- nil = no value currently owned by KeystoneLens.
    priorScreenshotQuality = nil,
    priorScreenshotFormat = nil,
    -- QR frame position. nil = default TOPLEFT. Stored as canonical top-left
    -- offsets relative to UIParent: {x=number, y=number}. y is normally <= 0.
    qrFramePosition = nil,
    -- `/kl off` pauses all applicant capture/lookups for the current hosting
    -- session, but arms an automatic resume when a later NEW LFG listing is
    -- detected. Persist this across /reload so pause semantics stay predictable.
    autoResumePending = false,
    pausedListingSignature = "",
    pausedSawNoListing = false,
}

-- Session lifecycle. INVARIANT: isSessionActive == true means an applicant-
-- recruitment transport session is active. A party roster by itself no longer
-- keeps screenshot capture alive after the LFG listing ends.
local isSessionActive = false
local sessionGen = 0             -- bumped in StartSession; deferred cleanups verify match
-- Separate LFG-listing generation. A transport session can stay alive because
-- the player remains in a party after delisting, so sessionGen alone cannot
-- distinguish a same-dungeon re-queue. Cycle 1..255; 0 stays reserved for
-- older Bridges/"unknown" on the Companion side.
local listingGeneration = 0
local wasHostingListing = false

-- Set by event handlers (pure boolean assignment; primitives can't carry
-- taint to readers). Drained by scan-tick from a clean native-scheduler frame.
local scanDirty = false

-- ───────────────────────────────────────────────────────────
-- QR Code transport
--
-- Companion side decodes via zxing-cpp (current native QR reader with a
-- Windows x64 ABI3 wheel). Earlier opencv-based decoder was
-- swapped out: cv2.QRCodeDetector empirically fails on QR Version ≥25 produced
-- by 30-applicant payloads at typical 3-4 px module sizes; ZXing handles them.
--
-- WHY row-RLE rendering: a Version 25 QR has 117x117 = 13689 modules. One
-- texture per module crashes WoW's renderer (verified empirically with the
-- prior 23400-tile pixel-marker design — UI hard-froze on Show). Row-based
-- run-length encoding folds adjacent black modules into single rectangle
-- textures. Large QR versions with high-entropy byte payloads can still reach
-- several thousand runs. Matrix analysis and texture painting are therefore
-- chunked across frames; BuildQRMatrix rejects only modes whose total pooled
-- texture count would exceed QR_TEXTURE_RENDER_BUDGET.
--
-- WHY transient QR uses a settle lease, not alpha-flicker: Screenshot() in the
-- After(0) callback empirically fired before SetAlpha(1) reached the GPU
-- framebuffer on real-world WoW setups, capturing alpha=0 (= no QR in the screenshot, no APS1 marker,
-- companion logs "skip — no APS1 marker" forever). The QR is now
-- normally hidden, but a changed snapshot Show()s it, waits
-- QR_RENDER_SETTLE_S, captures, then keeps the lease until Blizzard reports
-- SCREENSHOT_SUCCEEDED/FAILED. This avoids hiding the QR before an asynchronous
-- framebuffer capture has actually finished.
--
-- Reliability-first capture sizing. One physical pixel per module proved too
-- fragile on real Retail clients because Screenshot() completion is asynchronous
-- and the captured framebuffer can be scaled/compressed differently from the UI
-- paint pass. Three physical pixels per module matches the proven upstream
-- ApplicantScout transport and leaves enough contrast for ZXing even when the
-- user's screenshot settings are restored immediately after completion.
-- The QR remains transient: it is shown only for the capture window.
local QR_MODULE_PX = 1                 -- smallest physical-pixel module; visible only during the capture lease
local QR_RENDER_SETTLE_S = 0.16        -- enough render passes while keeping capture nearly imperceptible
-- Keep the standard four-module quiet zone. Dense QR captures have proven that
-- Decoder tolerance for a two-module border is not a delivery guarantee.
local QR_QUIET_ZONE = 4                -- modules of white border around QR
local QR_EC_LEVEL = 2                  -- error correction: 1=L 2=M 3=Q 4=H. M=15% recovery

---@type any
local qrFrame = nil                    -- containing frame
local qrTexturePool = {}               -- pool of black-module rectangle textures (reused)
local qrTextureUsed = 0                -- count of textures CURRENTLY shown (rest hidden)
local qrFrameCreated = false           -- one-shot init guard
local qrCurrentSize = 0                -- current frame side length in UI units (0 = unknown)

-- forward-decl locals so helpers and consumers can reference each other regardless
-- of definition order; assignment via `name = function(...)` lands on the LOCAL slot.
-- WHY MaybeTriggerScreenshot here: EndSession calls it before MaybeTriggerScreenshot
-- is defined further down. Without the forward-decl, Lua resolves the name as
-- _G.MaybeTriggerScreenshot (= nil) and call fails with "attempt to call a nil value".
local SafeStr, APSPrint, InitDB, StartSession, EndSession, CheckSessionTransition,
      MarkDirty, MaybeTriggerScreenshot,
      _SetEnabled, _SetDebug, _PauseUntilNextListing,
      -- Visibility coordinator + interaction-frame tracking. Replaces direct
      -- qrFrame:Show/Hide calls so a single function decides visibility from
      -- three orthogonal axes: isSessionActive (auto), _qrSuppressedByInteraction
      -- (auto, see below), qrAlwaysVisible (manual debug override).
      _RefreshQRVisibility, _RefreshQRMouse, _RecomputeInteractionSuppression,
      _TryHookInfoPanels, _OnInteractionEvent,
      -- Group Finder entry hooks only capture the host key level. They never
      -- prefill or submit Blizzard's listing form.
      _SetupLFGEntryCreationHooks
-- Forward-decl mutable state used by StartSession/EndSession/reset. WHY: those
-- functions assign via bare `x = ...`; without forward-decl, the `local` keyword
-- on declarations later in this file would shadow them and the bare assignments
-- silently target globals.
-- qrAlwaysVisible is forward-decl'd here so EndSession (above the slash handler
-- that owns the toggle) can preserve the user's debug visibility setting when
-- session ends.
-- qrMoveMode is opt-in mouse/drag mode. Normal visible QR must not capture
-- mouse input because it sits over gameplay HUD while hosting.
-- _qrSuppressedByInteraction: orthogonal to session/debug — true while any
-- tracked Blizzard interaction frame (vendor, NPC, quest, mail, bank, taxi,
-- character, map, etc.) is open. Hides QR so user can read those windows
-- without the QR overlay obscuring text. Companion misses ~10-30s of emits
-- while user has interaction window open — acceptable per scope.
-- qrForceVisibleForShot is a transport-only visibility lease for force shots
-- such as EndSession's final clear while an interaction frame has hidden QR.
local lastSnapshotHash, lastShotTime, pendingShotDirty,
      qrAlwaysVisible, qrMoveMode, suppressShotsUntil,
      _qrSuppressedByInteraction, qrForceVisibleForShot,
      qrForceVisibleShotGen, lastQREncodeMode, lastQREncodeBytes,
      lastQREncodeError

local lfgEntryCreationHookState = {
    hooksSetup = false,
    hookError = nil,
}
local lfgEntryCreationKeyCaptureHooked = setmetatable({}, { __mode = "k" })
local entryCreationKeyState = {
    END_SESSION_CLEAR_RETRY_DELAY_S = QR_RENDER_SETTLE_S * 2,
    TERMINAL_CLEAR_MAX_DISPATCHES = 2,
    terminalClearDispatchCount = 0,
    terminalClearSessionGen = nil,
    terminalClearRetryScheduled = false,
    DISABLE_CVAR_RESTORE_AFTER_CLEAR_DELAY_S = QR_RENDER_SETTLE_S * 3,
    entryCreationKeyLevelCache = nil,
    pendingEntryCreationKeyLevelCache = nil,
    activeListingCacheContext = nil,
    activeListingGeneration = 0,
    activeListingMaybeChanged = false,
    lfgEntryCreationKeyCapturePending = false,
    listingCreatePending = false,
    entryCreationKeyLevelCacheDecision = "none",
    lastPayloadApplicantCount = 0,
    lastPayloadRosterCount = 0,
    lastPayloadRosterIncomplete = false,
    lastEmittedApplicantCount = 0,
    rosterChangedSinceLastPayload = false,
    ROSTER_CHANGE_PREFLIGHT_DEADLINE_S = 2.0,
    ROSTER_INSPECT_RETRY_COOLDOWN_S = 15.0,
    ROSTER_INSPECT_MAX_TIMEOUTS_PER_SESSION = 2,
    -- Retry the expensive roster/RaiderIO builder only on a bounded backoff.
    -- The 0.5s transport poll must keep listing/applicant state fresh without
    -- rebuilding a roster surface that is already known to be incomplete.
    ROSTER_LOAD_RETRY_DELAYS_S = { 0.5, 2.0, 5.0, 15.0 },
    rosterLoadRetryAttempt = 0,
    rosterLoadRetryReady = true,
    rosterLoadRetryExhausted = false,
    rosterChangePreflightDeadline = nil,
    rosterChangePreflightToken = 0,
    pendingTtl = 10,
    NONTERMINAL_SNAPSHOT_MIN_SENDS = 1,
    lastDeliverySnapshotHash = nil,
    lastDeliverySnapshotSendCount = 0,
    -- Overflow snapshots are transmitted as bounded APS1 v10 fragment
    -- envelopes containing one frozen, complete logical payload. Keep this state on
    -- the existing table: the file is close to Lua 5.1's 200-local limit.
    QR_OVERFLOW_WIRE_VERSION = 0x0A,
    QR_OVERFLOW_FRAGMENT_BYTES = 320,
    QR_OVERFLOW_MAX_FRAGMENTS = 128,
    QR_OVERFLOW_MIN_SENDS = 1,
    QR_OVERFLOW_SHOT_INTERVAL_S = 0.45,
    qrOverflowStreamID = nil,
    qrOverflowGenerationCounter = 0,
    qrOverflowState = nil,
    qrOverflowSupersededCount = 0,
    qrOverflowLastFailure = nil,
    lastPayloadBuildError = nil,
    lastPayloadTotalBytes = 0,
    groupTransportGen = 0,
    rioMPlusSummaryCache = {},
    cleanUnknownLabel = nil,
    cleanUnknownObjectLabel = nil,
    -- Read-only by convention: payload builders only serialize these zero fields.
    emptyRaiderIOMPlusSummary = {
        currentScore = 0,
        mainScore = 0,
        hasProfile = false,
        bestKey = 0,
        bestDungeonKey = 0,
        timedAtOrAbove = 0,
        timedAtOrAboveMinus1 = 0,
        timedAtOrAboveMinus2 = 0,
        completedAtOrAboveMinus1 = 0,
        dungeonCount = 0,
    },
    qrPaintJobGen = 0,
    qrPaintInProgress = false,
    qrCaptureInProgress = false,
    qrPaintDirtyDuringPaint = false,
    qrTransportJobStartedAt = nil,
    qrTransportJobTerminalClear = false,
    SCREENSHOT_CVAR_RESTORE_DELAY_S = 0.05,
    screenshotCVarLeaseGeneration = 0,
    SCREENSHOT_FAILURE_MAX_ATTEMPTS = 2,
    screenshotFailureHash = nil,
    screenshotFailureAttemptCount = 0,
    screenshotAwaitingResult = false,
    screenshotAwaitingJobGen = nil,
    screenshotAwaitingSuperseded = false,
    screenshotResultHandler = nil,
    screenshotPendingForce = false,
    screenshotPendingTerminalClear = false,
    screenshotPendingSessionGen = nil,
    screenshotPendingLFGReadsAllowed = true,
    screenshotLastResult = "never",
    QR_TRANSPORT_JOB_TIMEOUT_S = 8.0,
    QR_RECOVERY_NOTICE_COOLDOWN_S = 30,
    qrTransportRecoveryCount = 0,
    qrTransportLastRecoveryReason = "never",
    qrTransportLastRecoveryPrintAt = nil,
    qrTextureVisibleHighWater = 0,
    transportDirtyGeneration = 0,
    LEADER_KEY_TTL_S = 60,
    LEADER_KEY_REQUEST_THROTTLE_S = 3,
    LEADER_KEY_REQUEST_RETRY_DELAY_S = 1.0,
    LEADER_KEY_REQUEST_MAX_RETRIES = 5,
    leaderKeystone = nil,
    leaderKeystoneLastRequestAt = 0,
    leaderKeystoneLastRequestStatus = "never",
    leaderKeystoneRequestRetryToken = 0,
    leaderKeystoneRequestRetryDeadline = nil,
    leaderKeystoneRequestRetryGeneration = nil,
    leaderKeystoneRefreshToken = 0,
    leaderKeystoneRefreshDeadline = nil,
    leaderKeystoneRefreshGeneration = nil,
    leaderKeystoneContextCombatDeferred = false,
    leaderKeystoneCallbackRegistered = false,
    leaderKeystoneLib = nil,
    leaderKeystoneCallbackOwner = {},
    libKeystonePrefixRegistered = false,
    libKeystoneShim = nil,
    libKeystoneShimCallbacks = {},
    libKeystoneLastSendStatus = "never",
    LIB_KEYSTONE_RESPONSE_RETRY_DELAY_S = 1.0,
    LIB_KEYSTONE_RESPONSE_MAX_RETRIES = 3,
    libKeystoneResponseRetryToken = 0,
    libKeystoneResponseRetryDeadline = nil,
    libKeystoneResponseRetryGeneration = nil,
    rosterInspectIlvlByGUID = {},
    rosterInspectKnownGUIDs = {},
}

entryCreationKeyState.ClearScreenshotFailureState = function()
    entryCreationKeyState.screenshotFailureHash = nil
    entryCreationKeyState.screenshotFailureAttemptCount = 0
end

-- ───────────────────────────────────────────────────────────
-- helpers

local function IsSecretValue(v)
    local issv = _G.issecretvalue
    if issv == nil then return false end
    if type(issv) ~= "function" then return true end
    local ok, isSecret = pcall(issv, v)
    if not ok then return true end
    return isSecret == true
end

entryCreationKeyState.ClearPendingForcedScreenshot = function()
    entryCreationKeyState.screenshotPendingForce = false
    entryCreationKeyState.screenshotPendingTerminalClear = false
    entryCreationKeyState.screenshotPendingSessionGen = nil
    entryCreationKeyState.screenshotPendingLFGReadsAllowed = true
end

entryCreationKeyState.QueuePendingForcedScreenshot = function(
    terminalClear,
    lfgReadsAllowed
)
    entryCreationKeyState.screenshotPendingForce = true
    if terminalClear then
        entryCreationKeyState.screenshotPendingTerminalClear = true
    end
    entryCreationKeyState.screenshotPendingSessionGen = sessionGen
    entryCreationKeyState.screenshotPendingLFGReadsAllowed =
        lfgReadsAllowed ~= false
end

entryCreationKeyState.TakePendingForcedScreenshot = function()
    local pending = entryCreationKeyState.screenshotPendingForce == true
    local terminalClear =
        entryCreationKeyState.screenshotPendingTerminalClear == true
    local pendingSessionGen = entryCreationKeyState.screenshotPendingSessionGen
    local lfgReadsAllowed =
        entryCreationKeyState.screenshotPendingLFGReadsAllowed ~= false
    entryCreationKeyState.ClearPendingForcedScreenshot()
    return pending, terminalClear, pendingSessionGen, lfgReadsAllowed
end

entryCreationKeyState.TerminalClearOwnsTransport = function()
    if isSessionActive
       or entryCreationKeyState.terminalClearSessionGen ~= sessionGen then
        return false
    end
    return entryCreationKeyState.screenshotPendingTerminalClear == true
        or entryCreationKeyState.qrTransportJobTerminalClear == true
        or entryCreationKeyState.terminalClearRetryScheduled == true
end

entryCreationKeyState.DispatchPendingForcedScreenshot = function()
    local pendingForce, pendingTerminalClear,
          pendingSessionGen, pendingLFGReadsAllowed =
        entryCreationKeyState.TakePendingForcedScreenshot()
    if not pendingForce or pendingSessionGen ~= sessionGen then
        return false
    end
    if pendingTerminalClear then
        if not isSessionActive
           and entryCreationKeyState.terminalClearSessionGen
               == pendingSessionGen then
            MaybeTriggerScreenshot(true, nil, true)
            return true
        end
        return false
    end
    if entryCreationKeyState.TerminalClearOwnsTransport() then
        return false
    end
    MaybeTriggerScreenshot(true, nil, nil, pendingLFGReadsAllowed)
    return true
end

entryCreationKeyState.CleanUnitAPIBoolean = function(api, ...)
    if type(api) ~= "function" then return nil end
    local ok, value = pcall(api, ...)
    if not ok then return nil end
    local okSecret, isSecret = pcall(IsSecretValue, value)
    if not okSecret or isSecret then return nil end
    local okTrue, isTrue = pcall(function() return value == true end)
    if okTrue and isTrue then return true end
    local okFalse, isFalse = pcall(function() return value == false end)
    if okFalse and isFalse then return false end
    return nil
end

entryCreationKeyState.CleanUnitIsGroupLeader = function(unit)
    return entryCreationKeyState.CleanUnitAPIBoolean(UnitIsGroupLeader, unit)
end

entryCreationKeyState.NoteRosterIdentityReadUnknown = function(reason)
    entryCreationKeyState.rosterInspectBatchLastBlockReason = reason
    if entryCreationKeyState.CleanUnitAPIBoolean(InCombatLockdown) == true then
        entryCreationKeyState.rosterInspectBatchCombatDeferred = true
    end
end

entryCreationKeyState.CleanRosterGUIDValue = function(guid)
    local okSecret, isSecret = pcall(IsSecretValue, guid)
    if not okSecret or isSecret then return "", true end
    if guid == nil or guid == "" then return "", false end
    if type(guid) ~= "string" then return "", true end
    return guid, false
end

entryCreationKeyState.UnitGUIDForRoster = function(unit)
    if not UnitGUID then
        entryCreationKeyState.NoteRosterIdentityReadUnknown("unit-guid-unknown")
        return ""
    end
    local ok, guid = pcall(UnitGUID, unit)
    if not ok then
        entryCreationKeyState.NoteRosterIdentityReadUnknown("unit-guid-unknown")
        return ""
    end
    local cleanGUID, blocked = entryCreationKeyState.CleanRosterGUIDValue(guid)
    if blocked then
        entryCreationKeyState.NoteRosterIdentityReadUnknown("unit-guid-unknown")
    end
    return cleanGUID
end

SafeStr = function(v, secretFallback)
    -- Boundary cleanse for C_LFGList field reads. Secret detection must be
    -- the first operation on potential API values: even tostring(secret), type
    -- checks after stringification, or string ops can propagate secret-taint.
    if IsSecretValue(v) then
        if secretFallback ~= nil then return secretFallback end
        return "?"
    end
    if v == nil then return "" end
    if type(v) == "boolean" then return v and "1" or "0" end
    local s = tostring(v)
    -- ~ historically used as field separator in chatlog era; kept as defensive
    -- substitution since some companion code paths still parse on it as a
    -- delimiter when displaying free-text fields.
    s = s:gsub("~", "-")
    s = s:gsub("|c%x%x%x%x%x%x%x%x", "")  -- color start |cAARRGGBB
    s = s:gsub("|c%x%x%x%x%x%x", "")      -- short color |cRRGGBB
    s = s:gsub("|r", "")                   -- color reset
    s = s:gsub("|K[^|]*|k", "")            -- protected player link text
    s = s:gsub("|H[^|]*|h", "")            -- link start
    s = s:gsub("|h", "")                   -- link end
    s = s:gsub("|T[^|]*|t", "")            -- texture
    s = s:gsub("|t", "")                   -- texture end
    s = s:gsub("|n", " ")                  -- newline → space
    s = s:gsub("|", "")                    -- any remaining bare | (defensive)
    -- Newlines/tabs in clipboard-pasted comments would corrupt our binary
    -- length-prefixed encoding (the count byte covers utf-8 bytes, but companion
    -- displays the string verbatim — multi-line comments look broken in overlay).
    s = s:gsub("[\r\n\t]+", " ")
    return s
end

local function SafeDiag(v)
    if IsSecretValue(v) then return "<secret>" end
    if v == nil then return "nil" end
    return tostring(v)
end

local function SafeNumber(v, default)
    if IsSecretValue(v) then return default or 0 end
    if v == nil then return default or 0 end
    local tv = type(v)
    if tv ~= "number" and tv ~= "string" then return default or 0 end
    local n = tonumber(v)
    if n == nil or n ~= n or n == math.huge or n == -math.huge then
        return default or 0
    end
    return n
end

local function SafeRoundedNumber(v, default)
    return math.floor(SafeNumber(v, default) + 0.5)
end

local function SafeTable(v)
    if IsSecretValue(v) then return nil end
    if type(v) == "table" then return v end
    return nil
end

local function SafeEnumKey(v, default)
    if IsSecretValue(v) then return default end
    local tv = type(v)
    if tv == "string" or tv == "number" then return v end
    return default
end

local function IsChatMessagingLockdown()
    return C_ChatInfo and C_ChatInfo.InChatMessagingLockdown
           and C_ChatInfo.InChatMessagingLockdown() or false
end

-- Return a prefix no longer than maxBytes that never ends inside a UTF-8
-- sequence. Lua 5.1 has byte strings and no native utf8 library.
entryCreationKeyState.TruncateUTF8Bytes = function(str, maxBytes)
    if #str <= maxBytes then return str end

    local start = maxBytes
    while start > 0 do
        local b = string.byte(str, start)
        if not (b and b >= 128 and b <= 191) then
            break
        end
        start = start - 1
    end

    if start <= 0 then return "" end

    local b = string.byte(str, start)
    local len
    if b <= 127 then
        len = 1
    elseif b >= 194 and b <= 223 then
        len = 2
    elseif b >= 224 and b <= 239 then
        len = 3
    elseif b >= 240 and b <= 244 then
        len = 4
    else
        return str:sub(1, start - 1)
    end

    local endsAt = start + len - 1
    if endsAt > maxBytes then
        return str:sub(1, start - 1)
    end

    for i = start + 1, endsAt do
        local cb = string.byte(str, i)
        if not (cb and cb >= 128 and cb <= 191) then
            return str:sub(1, start - 1)
        end
    end

    return str:sub(1, maxBytes)
end

entryCreationKeyState.NormalizeSavedBoolean = function(value)
    if IsSecretValue(value) then return false end
    local valueType = type(value)
    if valueType == "boolean" then return value end
    if valueType == "number" then
        if value ~= value then return false end
        return value == 1
    end
    if valueType == "string" then
        local token = value:gsub("^%s+", ""):gsub("%s+$", ""):lower()
        return token == "true" or token == "1"
            or token == "on" or token == "yes"
    end
    return false
end

InitDB = function()
    if type(KeystoneLensBridgeDB) ~= "table" then KeystoneLensBridgeDB = {} end
    for k, v in pairs(DB_DEFAULTS) do
        if KeystoneLensBridgeDB[k] == nil then KeystoneLensBridgeDB[k] = v end
    end
    KeystoneLensBridgeDB.enabled =
        entryCreationKeyState.NormalizeSavedBoolean(KeystoneLensBridgeDB.enabled)
    KeystoneLensBridgeDB.debug =
        entryCreationKeyState.NormalizeSavedBoolean(KeystoneLensBridgeDB.debug)
    KeystoneLensBridgeDB.autoResumePending =
        entryCreationKeyState.NormalizeSavedBoolean(KeystoneLensBridgeDB.autoResumePending)
    KeystoneLensBridgeDB.pausedSawNoListing =
        entryCreationKeyState.NormalizeSavedBoolean(KeystoneLensBridgeDB.pausedSawNoListing)
    if IsSecretValue(KeystoneLensBridgeDB.pausedListingSignature)
       or type(KeystoneLensBridgeDB.pausedListingSignature) ~= "string" then
        KeystoneLensBridgeDB.pausedListingSignature = ""
    end
    -- Never resurrect a visible QR debug mode from a prior session. The
    -- `/klbridge qrvisible` support toggle is deliberately runtime-only.
    KeystoneLensBridgeDB.qrAlwaysVisible = false
    entryCreationKeyState.SetQRAlwaysVisible(false)
    KeystoneLensBridgeDB.debugDefaultMigrated =
        entryCreationKeyState.NormalizeSavedBoolean(
            KeystoneLensBridgeDB.debugDefaultMigrated
        )
    if not KeystoneLensBridgeDB.debugDefaultMigrated then
        KeystoneLensBridgeDB.debug = false
        KeystoneLensBridgeDB.debugDefaultMigrated = true
    end

    -- Remove beta-only features from old SavedVariables. They are deliberately
    -- unsupported in the release bridge so transport has no chat/form/UI side effects.
    KeystoneLensBridgeDB.autoCompetitivePlaystyle = nil
    KeystoneLensBridgeDB.autoMPlusPlaystyle = nil
    KeystoneLensBridgeDB.autoHiMessage = nil
    KeystoneLensBridgeDB.autoHiGreetNewPartyMembers = nil
    KeystoneLensBridgeDB.pveFramePosition = nil
end

APSPrint = function(msg)
    print("|cff5da8ffKeystoneLens Bridge|r " .. msg)
end

-- Screenshot lifecycle/CVar ownership is isolated from the payload builder.
-- This keeps the asynchronous capture state serialised and inspectable.
entryCreationKeyState.screenshotController =
    KL.NewScreenshotController(entryCreationKeyState, APSPrint)

-- ───────────────────────────────────────────────────────────
-- Session lifecycle: tied to the player's own LFG listing.
--   StartSession: invariant transition false→true. Resets snapshot dedup
--                 state for fresh full snapshot.
--   EndSession:   invariant transition true→false. Force-emits final empty
--                 snapshot (clears companion overlay state).
--   sessionGen:   monotonic counter — verified by EndSession's deferred
--                 terminal-clear capture and Hide callbacks so a fast
--                 Start→End→Start sequence doesn't let the prior End mutate
--                 a fresh session.

StartSession = function()
    if isSessionActive then return end
    isSessionActive = true
    sessionGen = sessionGen + 1
    entryCreationKeyState.ClearPendingForcedScreenshot()

    -- QR transport state reset: force fresh full snapshot at session start.
    -- BuildPayload emits VERSION on every shot so companion-launched-mid-session
    -- still receives region/realm info from the freshest backlog snapshot.
    lastSnapshotHash = nil
    lastShotTime = 0
    entryCreationKeyState.lastEmittedApplicantCount = 0
    entryCreationKeyState.lastDeliverySnapshotHash = nil
    entryCreationKeyState.lastDeliverySnapshotSendCount = 0
    entryCreationKeyState.ClearQROverflowTransport("session-start")
    entryCreationKeyState.qrOverflowLastFailure = nil
    entryCreationKeyState.ClearScreenshotFailureState()
    entryCreationKeyState.terminalClearDispatchCount = 0
    entryCreationKeyState.terminalClearSessionGen = nil
    entryCreationKeyState.terminalClearRetryScheduled = false
    pendingShotDirty = false
    lastQREncodeMode = "never"
    lastQREncodeBytes = 0
    lastQREncodeError = nil
    if entryCreationKeyState.screenshotController:IsWaitingResult() then
        -- SCREENSHOT_* has no request identity. Keep the old handler armed so
        -- its eventual event/timeout can be consumed without resolving a new
        -- session capture.
        entryCreationKeyState.screenshotController:SupersedeWaitingResult()
    else
        entryCreationKeyState.qrPaintJobGen = (entryCreationKeyState.qrPaintJobGen or 0) + 1
        entryCreationKeyState.ClearQRTransportJob()
    end
    qrForceVisibleShotGen = (qrForceVisibleShotGen or 0) + 1
    qrForceVisibleForShot = false
    if qrFrame then qrFrame:SetFrameStrata("DIALOG") end
    entryCreationKeyState.rioMPlusSummaryCache = {}
    entryCreationKeyState.lastQuietFullPartySignature = nil
    entryCreationKeyState.lastPayloadQuietFullPartySignature = nil
    entryCreationKeyState.MarkRosterCompositionChanged()
    entryCreationKeyState.ClearRosterInspectBatchState()
    entryCreationKeyState.ClearRosterInspectFailureState()
    entryCreationKeyState.ResetRosterInspectDataCache()
    entryCreationKeyState.ReconcileRosterInspectMembership()
    entryCreationKeyState.RequestLeaderKeystone(true)

    -- QR is no longer shown for the entire session. The first changed snapshot
    -- will paint the QR, take a short visibility lease, wait QR_RENDER_SETTLE_S,
    -- capture, and hide it again. Manual debug/move modes still flow through
    -- the same visibility coordinator.
    suppressShotsUntil = 0
    _RefreshQRVisibility()
end

EndSession = function(emitTerminalClear)
    if not isSessionActive then return end
    if emitTerminalClear == nil then emitTerminalClear = true end
    isSessionActive = false  -- claim the transition; further scans early-return

    scanDirty = false
    -- Force-shot path bypasses suppressShotsUntil via force=true, but clear
    -- the gate explicitly so a fresh StartSession that happens before the
    -- old gate would have expired starts with a clean render-settle window.
    suppressShotsUntil = 0

    -- Final force-shot: terminalClear makes BuildPayload emit has_listing=0,
    -- 0 applicants, and roster_count=0. Companion treats no-listing + roster
    -- as valid Party state, so teardown must explicitly omit roster rows.
    -- Bypasses dedup + throttle (force=true). Completion schedules one serialized
    -- resend so an async first job cannot be cancelled by an absolute retry timer.
    entryCreationKeyState.ClearRosterInspectBatchState()
    entryCreationKeyState.ClearRosterInspectFailureState()
    entryCreationKeyState.ClearRosterLoadRetryState()
    entryCreationKeyState.ClearRosterCompositionChanged()
    if entryCreationKeyState.screenshotController:IsWaitingResult() then
        -- Do not orphan an identity-free SCREENSHOT_* result. The terminal
        -- request below is queued behind this physical capture.
        entryCreationKeyState.screenshotController:SupersedeWaitingResult()
    else
        entryCreationKeyState.qrPaintJobGen = (entryCreationKeyState.qrPaintJobGen or 0) + 1
        entryCreationKeyState.ClearQRTransportJob()
    end
    qrForceVisibleShotGen = (qrForceVisibleShotGen or 0) + 1
    qrForceVisibleForShot = false
    if qrFrame then
        qrFrame:SetFrameStrata("DIALOG")
        _RefreshQRVisibility()
    end
    entryCreationKeyState.terminalClearDispatchCount = 0
    entryCreationKeyState.terminalClearSessionGen = emitTerminalClear and sessionGen or nil
    entryCreationKeyState.terminalClearRetryScheduled = false
    -- A normal listing close sends one final clear frame so the Companion can
    -- clear stale applicants. Auto-pausing because the party is full or the
    -- dungeon has started is intentionally silent: no new Screenshot() call is
    -- allowed after that lifecycle boundary.
    entryCreationKeyState.ClearQROverflowTransport(
        emitTerminalClear and "terminal-clear" or "capture-auto-pause"
    )
    if emitTerminalClear then
        MaybeTriggerScreenshot(true, nil, true)
    end
    entryCreationKeyState.lastQuietFullPartySignature = nil
    entryCreationKeyState.lastPayloadQuietFullPartySignature = nil
    -- Defensive: force-shot path resets pendingShotDirty on success, but if it
    -- early-returned (qrFrame missing, QR encode failure) the flag could persist
    -- across sessions and trigger empty drains in the scan ticker. Clear here.
    pendingShotDirty = false
    entryCreationKeyState.lastEmittedApplicantCount = 0
    entryCreationKeyState.lastDeliverySnapshotHash = nil
    entryCreationKeyState.lastDeliverySnapshotSendCount = 0
    entryCreationKeyState.entryCreationKeyLevelCache = nil
    entryCreationKeyState.rioMPlusSummaryCache = {}

    -- Schedule deferred Hide AFTER the final clear-shot has had a chance to
    -- fire. The screenshot path inside MaybeTriggerScreenshot waits the render
    -- settle window before capture after every successful QR repaint. Hiding
    -- synchronously here would make the screenshot capture an empty screen (no QR),
    -- companion never sees the clear signal, overlay stuck showing pre-end
    -- applicants.
    -- All gating (qrAlwaysVisible, new-session-started) re-checked at fire
    -- time so the deferred Hide respects the latest toggle state — important
    -- for /kl off which resets qrAlwaysVisible right after EndSession.
    if qrFrame then
        local genAtSchedule = sessionGen
        C_Timer.After(QR_RENDER_SETTLE_S, function()
            -- Re-enter the visibility coordinator only if we're still in the
            -- same gen AND the session has actually ended. _RefreshQRVisibility
            -- handles qrAlwaysVisible (debug override stays visible across
            -- session boundaries). Without the gen check a fast Start→End→Start
            -- sequence would apply this old End's "hide" decision atop a fresh
            -- session's StartSession-driven Show.
            if sessionGen == genAtSchedule and not isSessionActive then
                _RefreshQRVisibility()
            end
        end)
    end
end

local function _HasGroupRosterForTransport()
    return math.floor(SafeNumber(GetNumGroupMembers and GetNumGroupMembers(), 0)) > 0
end

CheckSessionTransition = function(lfgReadsAllowed)
    if lfgReadsAllowed == nil then lfgReadsAllowed = true end
    local hasRoster = _HasGroupRosterForTransport()
    local entry = nil
    local hosting = false
    if lfgReadsAllowed then
        local hasEntry = C_LFGList.HasActiveEntryInfo()
        if hasEntry then
            entry = SafeTable(C_LFGList.GetActiveEntryInfo())
        end
        hosting = entry ~= nil

        local confirmedNewListing = hosting and (
            not wasHostingListing or entryCreationKeyState.listingCreatePending == true
        )
        if confirmedNewListing then
            listingGeneration = (listingGeneration % 255) + 1
            entryCreationKeyState.listingCreatePending = false
            wasHostingListing = true
            -- A re-queue is a new applicant domain even when every visible
            -- listing field is identical. CreateListing intent closes the race
            -- where delist -> relist happens entirely between two 0.25s ticks.
            -- Retire old fragments/hash and force a fresh current-queue capture.
            lastSnapshotHash = nil
            entryCreationKeyState.ClearQROverflowTransport("listing-start")
            pendingShotDirty = true
        elseif not hosting and wasHostingListing then
            wasHostingListing = false
            lastSnapshotHash = nil
            entryCreationKeyState.ClearQROverflowTransport("listing-ended")
            pendingShotDirty = true
        end

        local listingContext = entryCreationKeyState.EntryListingCacheContext(entry)
        entryCreationKeyState.ReconcileEntryCreationKeyCache(listingContext)
    end
    local transportActive = CapturePolicy.TransportActive(
        hosting, hasRoster, lfgReadsAllowed, isSessionActive
    )

    if transportActive and not isSessionActive then
        StartSession()
    elseif not transportActive and isSessionActive then
        if lfgReadsAllowed or not entryCreationKeyState.activeListingCacheContext then
            EndSession()
        end
    end
    -- Returns the active LFG entry (or nil) so the scan-tick caller can pass
    -- it straight to MaybeTriggerScreenshot — saves a second
    -- C_LFGList.GetActiveEntryInfo() call per scan.
    return entry
end

-- ───────────────────────────────────────────────────────────
-- event dispatch (raw frame; rationale at top)

-- Single transition logger: clean→dirty fires the debug print once per
-- scan cycle (avoids spam during applicant bursts where 30+ events fire <1s
-- apart). All events funnel here; behavior decisions live in ScanAndEmit /
-- CheckSessionTransition — DRY-locked.
MarkDirty = function(reason)
    local wasClean = not scanDirty
    scanDirty = true
    entryCreationKeyState.transportDirtyGeneration =
        (entryCreationKeyState.transportDirtyGeneration or 0) + 1
    if wasClean and KeystoneLensBridgeDB and KeystoneLensBridgeDB.debug then
        print("|cff999999[APS-debug]|r DIRTY reason=" .. tostring(reason))
    end
end

-- ───────────────────────────────────────────────────────────
-- QR frame setup
--
-- One containing frame, sized to whatever QR version we just generated
-- (adaptive). White background covers the entire frame; row-RLE pool of
-- black-rectangle textures draws the QR data.
local function _IsFinitePositionNumber(v)
    local POSITION_LIMIT = 100000
    return type(v) == "number" and v == v
           and v > -POSITION_LIMIT and v < POSITION_LIMIT
end

local function _NormalizeQRPosition(pos)
    if type(pos) ~= "table" then return 0, 0, false end
    local x, y = pos.x, pos.y
    if not (_IsFinitePositionNumber(x) and _IsFinitePositionNumber(y)) then
        return 0, 0, false
    end
    return x, y, true
end

local function _ClampQRPosition(x, y, frameSize)
    frameSize = _IsFinitePositionNumber(frameSize) and frameSize or 64
    local parentW = UIParent and UIParent:GetWidth() or 0
    local parentH = UIParent and UIParent:GetHeight() or 0
    if not _IsFinitePositionNumber(parentW) or parentW <= 0 then parentW = frameSize end
    if not _IsFinitePositionNumber(parentH) or parentH <= 0 then parentH = frameSize end

    local maxX = parentW - frameSize
    local minY = frameSize - parentH
    if maxX < 0 then maxX = 0 end
    if minY > 0 then minY = 0 end

    if x < 0 then x = 0 elseif x > maxX then x = maxX end
    if y > 0 then y = 0 elseif y < minY then y = minY end
    return x, y
end

local function _GetQRFrameSize()
    if qrFrame then
        local w = qrFrame:GetWidth()
        if _IsFinitePositionNumber(w) and w > 0 then return w end
    end
    return qrCurrentSize > 0 and qrCurrentSize or 64
end

local function _ApplyQRFramePosition()
    if not qrFrame then return end
    -- Normal transport is deliberately pinned to the extreme top-left because
    -- the Companion decodes a small top-left crop and this is the least
    -- intrusive location. A saved position is only honored in explicit move
    -- mode for support/debugging.
    local x, y = 0, 0
    if qrMoveMode then
        x, y = _NormalizeQRPosition(
            KeystoneLensBridgeDB and KeystoneLensBridgeDB.qrFramePosition
        )
    end
    x, y = _ClampQRPosition(x, y, _GetQRFrameSize())
    qrFrame:ClearAllPoints()
    qrFrame:SetPoint("TOPLEFT", UIParent, "TOPLEFT", x, y)
end

local function _SaveQRFramePositionFromFrame()
    if not (qrFrame and KeystoneLensBridgeDB) then return false end
    local frameLeft, frameTop = qrFrame:GetLeft(), qrFrame:GetTop()
    local parentLeft = UIParent and UIParent:GetLeft() or 0
    local parentTop = UIParent and UIParent:GetTop() or (UIParent and UIParent:GetHeight() or 0)
    if not (_IsFinitePositionNumber(frameLeft) and _IsFinitePositionNumber(frameTop)
            and _IsFinitePositionNumber(parentLeft) and _IsFinitePositionNumber(parentTop)) then
        return false
    end
    local x = frameLeft - parentLeft
    local y = frameTop - parentTop
    x, y = _ClampQRPosition(x, y, _GetQRFrameSize())
    if x == 0 and y == 0 then
        KeystoneLensBridgeDB.qrFramePosition = nil
    else
        KeystoneLensBridgeDB.qrFramePosition = { x = x, y = y }
    end
    _ApplyQRFramePosition()
    return true
end

local function _ResetQRFramePosition()
    if KeystoneLensBridgeDB then KeystoneLensBridgeDB.qrFramePosition = nil end
    _ApplyQRFramePosition()
end

local function _CurrentQRPositionText()
    if not qrFrame then return "(frame missing)" end
    local x, y, valid = _NormalizeQRPosition(KeystoneLensBridgeDB and KeystoneLensBridgeDB.qrFramePosition)
    x, y = _ClampQRPosition(x, y, _GetQRFrameSize())
    local saved = valid and "saved" or "default"
    return string.format("%s @ (%.0f, %.0f)", saved, x, y)
end

local function _OnQRFrameDragStart(self)
    if not qrMoveMode or not IsAltKeyDown() then return end
    local ok = pcall(self.StartMoving, self)
    if ok then self.apsMoving = true end
end

local function _OnQRFrameDragStop(self)
    if not self.apsMoving then return end
    pcall(self.StopMovingOrSizing, self)
    self.apsMoving = false
    if _SaveQRFramePositionFromFrame() then
        APSPrint("QR position saved: " .. _CurrentQRPositionText())
    else
        APSPrint("QR position not saved — frame anchor unavailable")
    end
end

local function CreateQRFrame()
    if qrFrameCreated then return end
    qrFrame = CreateFrame("Frame", "KeystoneLensBridgeQRFrame", UIParent)
    qrFrame:SetIgnoreParentScale(true)
    -- DIALOG strata: above gameplay HUD but below modal popups (StaticPopup,
    -- ColorPicker, dropdowns). Avoids FULLSCREEN_DIALOG which has been
    -- empirically observed to interfere with input chain on heavy renders.
    qrFrame:SetFrameStrata("DIALOG")
    qrFrame:SetSize(64, 64)  -- placeholder; PaintQR resizes per-snapshot
    qrFrame:SetMovable(true)
    qrFrame:SetClampedToScreen(true)
    qrFrame:RegisterForDrag("LeftButton")
    qrFrame:SetScript("OnDragStart", _OnQRFrameDragStart)
    qrFrame:SetScript("OnDragStop", _OnQRFrameDragStop)
    _ApplyQRFramePosition()

    -- White background — single texture covering the whole frame, BACKGROUND
    -- layer. Black module textures (BORDER layer above) overlay it. ZXing's
    -- QR detector relies on black-on-white contrast — this gives it the
    -- canonical look.
    local qrBackground = qrFrame:CreateTexture(nil, "BACKGROUND")
    qrBackground:SetColorTexture(1, 1, 1, 1)
    qrBackground:SetAllPoints(qrFrame)

    qrFrameCreated = true
    -- Hidden by default unless the current-session support override is enabled.
    -- Screenshot dispatch otherwise takes a temporary visibility lease only
    -- after a changed payload has been painted.
    if _RefreshQRMouse then _RefreshQRMouse() end
    qrFrame:Hide()
    if _RefreshQRVisibility then _RefreshQRVisibility() end
end

-- /klbridge qrvisible state — forces frame to stay visible regardless of session
-- state (debug aid for visual inspection). Forward-declared at top so EndSession
-- can respect the toggle when hiding the frame.
qrAlwaysVisible = false
qrMoveMode = false

-- Support-only visibility is session-local. Persisting this state made a
-- diagnostic command leak into the next play session and left the QR visible,
-- which is the opposite of the normal transport contract.
entryCreationKeyState.SetQRAlwaysVisible = function(flag)
    local enabled = flag == true
    qrAlwaysVisible = enabled
    if KeystoneLensBridgeDB then KeystoneLensBridgeDB.qrAlwaysVisible = false end
    return enabled
end

-- ───────────────────────────────────────────────────────────
-- QR auto-fade on Blizzard interaction frames
--
-- WHY: dense applicant snapshots can produce a QR wide enough to obscure
-- Blizzard panels (vendor, gossip, quest text, mail, bank, taxi, etc.).
-- Hiding the QR while ANY tracked
-- interaction frame is open lets the user actually read those windows.
-- Companion misses the screenshots during the fade window — acceptable
-- because the user isn't actively monitoring applicants while they're at a
-- vendor. _RefreshQRVisibility re-arms suppressShotsUntil on each
-- hidden→shown transition so the next Screenshot() doesn't capture an
-- unpainted post-Hide frame.
--
-- WHY hybrid event + polling: vendor-class frames have dedicated
-- events (MERCHANT_SHOW etc) that fire even when third-party addons replace
-- the Blizzard frame entirely (BetterMerchant, custom gossip overlays).
-- Info panels (CharacterFrame, WorldMapFrame, EncounterJournalFrame, etc.)
-- have no dedicated events, so the scan ticker samples their shown state.
-- Avoid hooking their OnShow/OnHide stacks; some Blizzard panels read secret
-- fields while showing/sorting, and addon callbacks there can make unrelated
-- protected comparisons inherit addon taint.
--
-- WHY ADDON_LOADED-driven re-scan: many info panels live in load-on-demand
-- addons (Blizzard_AchievementUI, Blizzard_EncounterJournal, etc.) and don't
-- exist at PLAYER_LOGIN. Re-scan on every ADDON_LOADED catches them as their
-- addons load. _trackedInfoPanels keeps scans idempotent.

-- Each value is { slot kind, desired active state }. Keeping both fields in
-- one map prevents registration and state transitions from drifting apart.
local INTERACTION_EVENTS = {
    MERCHANT_SHOW          = { "vendor", true },
    MERCHANT_CLOSED        = { "vendor", false },
    GOSSIP_SHOW            = { "gossip", true },
    GOSSIP_CLOSED          = { "gossip", false },
    QUEST_DETAIL           = { "quest", true },
    QUEST_GREETING         = { "quest", true },
    QUEST_PROGRESS         = { "quest", true },
    QUEST_COMPLETE         = { "quest", true },
    QUEST_FINISHED         = { "quest", false },
    MAIL_SHOW              = { "mail", true },
    MAIL_CLOSED            = { "mail", false },
    BANKFRAME_OPENED       = { "bank", true },
    BANKFRAME_CLOSED       = { "bank", false },
    GUILDBANKFRAME_OPENED  = { "guildbank", true },
    GUILDBANKFRAME_CLOSED  = { "guildbank", false },
    -- VOID_STORAGE_* removed in Midnight 12.x — `Frame:RegisterEvent` warns
    -- "Attempt to register unknown event" 3x. Void storage UI no longer fires
    -- those events; the frame uses different mechanics. No replacement event
    -- is needed (companion's QR fade-on-interaction list isn't user-facing).
    TAXIMAP_OPENED         = { "taxi", true },
    TAXIMAP_CLOSED         = { "taxi", false },
    BARBER_SHOP_OPEN       = { "barber", true },
    BARBER_SHOP_CLOSE      = { "barber", false },
    TRADE_SHOW             = { "trade", true },
    TRADE_CLOSED           = { "trade", false },
    AUCTION_HOUSE_SHOW     = { "auctionhouse", true },
    AUCTION_HOUSE_CLOSED   = { "auctionhouse", false },
    TRADE_SKILL_SHOW       = { "professions", true },
    TRADE_SKILL_CLOSE      = { "professions", false },
}

-- Frames without dedicated events. Track them when the frame becomes available;
-- _TryHookInfoPanels re-runs on ADDON_LOADED/ticker to catch LoD panels.
local INFO_PANEL_FRAMES = {
    "WorldMapFrame", "EncounterJournalFrame", "SpellBookFrame",
    "PlayerSpellsFrame", "CharacterFrame", "CollectionsJournal",
    "AchievementFrame", "CommunitiesFrame", "FriendsFrame",
    "ProfessionsFrame", "FlightMapFrame", "SettingsPanel",
}

local _interactionSlots = {}  -- kind → bool (only set when active; nil = inactive)
local _trackedInfoPanels = {} -- frame name → true once available for polling

-- Current Retail exposes one authoritative interaction manager for NPC-backed
-- panels. Keep its enum mapping on the existing state table (rather than adding
-- more file-scope locals in this Lua 5.1-sized file) and use it to repair both
-- missed close events and missed show events during the normal poll.
entryCreationKeyState.RefreshInteractionTypeMappings = function()
    local playerInteractionType = _G.Enum and _G.Enum.PlayerInteractionType
    if type(playerInteractionType) ~= "table" then return false end

    local typeKinds = {}
    local kindTypes = {}
    local function Add(kind, enumName)
        local interactionType = playerInteractionType[enumName]
        if type(interactionType) ~= "number" or IsSecretValue(interactionType) then
            return
        end
        typeKinds[interactionType] = kind
        local types = kindTypes[kind]
        if not types then
            types = {}
            kindTypes[kind] = types
        end
        types[#types + 1] = interactionType
    end

    Add("vendor", "Merchant")
    Add("vendor", "Vendor")
    Add("gossip", "Gossip")
    Add("quest", "QuestGiver")
    Add("mail", "MailInfo")
    Add("bank", "Banker")
    Add("bank", "CharacterBanker")
    Add("bank", "AccountBanker")
    Add("guildbank", "GuildBanker")
    Add("taxi", "TaxiNode")
    Add("barber", "BarbersChoice")
    Add("trade", "TradePartner")
    Add("auctionhouse", "Auctioneer")
    Add("professions", "Professions")
    Add("professions", "ProfessionsCraftingOrder")
    Add("professions", "ProfessionsCustomerOrder")
    Add("professions", "ProfessionsCustomerOrders")

    entryCreationKeyState.interactionTypeKinds = typeKinds
    entryCreationKeyState.interactionKindTypes = kindTypes
    return true
end

-- A loading-screen/world transition cannot preserve an event-owned merchant,
-- bank, trade, auction, taxi, or quest interaction. If Blizzard omits a paired
-- *_CLOSED event during that transition, retaining the slot would suppress
-- every later non-force transport until /reload. Polled info panels are not
-- cleared; the recompute below still observes their actual IsVisible state.
entryCreationKeyState.ResetInteractionSlotsForWorldTransition = function()
    for kind in pairs(_interactionSlots) do
        _interactionSlots[kind] = nil
    end
    _RecomputeInteractionSuppression()
end

-- Single visibility decision. Three axes:
--   qrForceVisibleForShot       — auto: changed snapshot is being captured
--   qrAlwaysVisible             — manual: /klbridge qrvisible debug override
--   qrMoveMode                  — manual: /klbridge qrmove drag/debug mode
-- Debug override/move mode wins over normal hidden state (user explicitly said
-- "show me"). Interaction suppression gates non-force dispatch before a lease
-- is acquired.
_RefreshQRMouse = function()
    if not qrFrame then return end
    qrFrame:EnableMouse(qrMoveMode and true or false)
end

_RefreshQRVisibility = function()
    if not qrFrame then return end
    local wasShown = qrFrame:IsShown()
    local shouldShow = qrAlwaysVisible
                       or qrMoveMode
                       or qrForceVisibleForShot
    if shouldShow and not wasShown then
        qrFrame:SetAlpha(1)
        qrFrame:Show()
        -- WHY QR_RENDER_SETTLE_S grace on every hidden→shown transition (not just session
        -- start): the GPU framebuffer needs paint time after Show, same race
        -- as session-start. Without this, a vendor-close → fast Screenshot
        -- captures the post-Hide unpainted frame → companion logs "no APS1".
        -- Reuses the existing suppression mechanism — no parallel state.
        suppressShotsUntil = GetTime() + QR_RENDER_SETTLE_S
        pendingShotDirty = true  -- scan-tick drain retries post-grace
    elseif not shouldShow and wasShown then
        qrFrame:Hide()
    end
end

-- Aggregator: walks events table + tracked info panels to determine if any
-- interaction frame is currently open. Calls _RefreshQRVisibility only when
-- the suppression boolean actually flips — avoids redundant Show/Hide calls
-- on every event burst.
_RecomputeInteractionSuppression = function(skipManagerReconcile)
    local managerStates = nil
    local interactionManager = _G.C_PlayerInteractionManager
    local isInteracting = interactionManager
        and interactionManager.IsInteractingWithNpcOfType
    if not skipManagerReconcile and type(isInteracting) == "function" then
        if type(entryCreationKeyState.interactionTypeKinds) ~= "table" then
            entryCreationKeyState.RefreshInteractionTypeMappings()
        end
        managerStates = {}
        for interactionType in pairs(entryCreationKeyState.interactionTypeKinds or {}) do
            local active = entryCreationKeyState.CleanUnitAPIBoolean(
                isInteracting,
                interactionType
            )
            managerStates[interactionType] = active
            if active == true then
                _interactionSlots[interactionType] = true
            elseif active == false then
                _interactionSlots[interactionType] = nil
            end
        end

        -- Legacy events remain useful for third-party replacement panels, but
        -- a missing *_CLOSED must not become a permanent latch. Clear a legacy
        -- kind only when every mapped manager query returned a clean false.
        for kind in pairs(entryCreationKeyState.interactionKindTypes or {}) do
            if _interactionSlots[kind] then
                local mappedTypes = entryCreationKeyState.interactionKindTypes
                    and entryCreationKeyState.interactionKindTypes[kind]
                local allKnownInactive = mappedTypes and #mappedTypes > 0
                for _, interactionType in ipairs(mappedTypes or {}) do
                    if managerStates[interactionType] ~= false then
                        allKnownInactive = false
                        break
                    end
                end
                if allKnownInactive then
                    _interactionSlots[kind] = nil
                end
            end
        end
    end

    local anyActive = false
    for _, active in pairs(_interactionSlots) do
        if active then anyActive = true; break end
    end
    if not anyActive then
        for name in pairs(_trackedInfoPanels) do
            local frame = _G[name]
            if frame
               and entryCreationKeyState.CleanUnitAPIBoolean(frame.IsVisible, frame) == true then
                anyActive = true; break
            end
        end
    end
    if anyActive ~= (_qrSuppressedByInteraction or false) then
        _qrSuppressedByInteraction = anyActive
        _RefreshQRVisibility()
    end
end

-- Event-driven slot updater. Idempotent: repeated set-true for the same kind
-- writes the same slot. desired=nil events filtered upstream by EVENT_HANDLERS
-- registration (only events present in INTERACTION_EVENTS are bound).
_OnInteractionEvent = function(event)
    local config = INTERACTION_EVENTS[event]
    if not config then return end
    local kind, desired = config[1], config[2]
    -- Sparse storage: false → nil to keep the table minimal; aggregator's
    -- pairs() loop only walks active slots.
    _interactionSlots[kind] = desired or nil
    -- The legacy SHOW event can precede the manager's state flip in the same
    -- frame. Trust this event immediately; the next poll performs repair.
    _RecomputeInteractionSuppression(desired == true)
end

entryCreationKeyState.OnPlayerInteractionManagerEvent = function(event, interactionType)
    if type(interactionType) ~= "number" or IsSecretValue(interactionType) then return end
    if event == "PLAYER_INTERACTION_MANAGER_FRAME_SHOW" then
        _interactionSlots[interactionType] = true
    elseif event == "PLAYER_INTERACTION_MANAGER_FRAME_HIDE" then
        _interactionSlots[interactionType] = nil
    else
        return
    end
    _RecomputeInteractionSuppression(event == "PLAYER_INTERACTION_MANAGER_FRAME_SHOW")
end

-- Lazy tracker. Called at PLAYER_LOGIN, ADDON_LOADED, and the scan ticker.
-- Idempotent via _trackedInfoPanels — once a frame is seen, later calls skip it.
-- Frames not yet existing (LoD that hasn't loaded) are silently skipped;
-- next ADDON_LOADED/ticker pass triggers another scan.
_TryHookInfoPanels = function()
    local newlyTrackedVisible = false
    for _, name in ipairs(INFO_PANEL_FRAMES) do
        if not _trackedInfoPanels[name] then
            local frame = _G[name]
            if frame and type(frame.IsVisible) == "function" then
                _trackedInfoPanels[name] = true
                if entryCreationKeyState.CleanUnitAPIBoolean(frame.IsVisible, frame) == true then
                    newlyTrackedVisible = true
                end
            end
        end
    end
    if newlyTrackedVisible then
        _RecomputeInteractionSuppression()
    end
end

-- Lease screenshot format only for the short KeystoneLens capture.
-- Use lossless PNG for KeystoneLens-owned captures and keep that lease until
-- Blizzard reports the screenshot result. SetCVar persists in Config.wtf, so
-- every completed/failed capture restores the user's prior format afterwards.
-- screenshotQuality is intentionally left untouched; the legacy quality stash
-- is only restored below for interrupted older leases.
entryCreationKeyState.RestoreScreenshotCVarsWhenSafe = function(delay, requiredSessionGen)
    local function restoreIfStillDisabled()
        if not KeystoneLensBridgeDB or KeystoneLensBridgeDB.enabled then return end
        if isSessionActive then return end
        if requiredSessionGen and sessionGen ~= requiredSessionGen then return end
        entryCreationKeyState.screenshotController:RestoreScreenshotCVars(false)
    end

    if delay and delay > 0 and C_Timer and C_Timer.After then
        C_Timer.After(delay, restoreIfStillDisabled)
    else
        restoreIfStillDisabled()
    end
end

-- ───────────────────────────────────────────────────────────
-- Payload encoder + QR painter
--
-- Wire format (binary, big-endian; unchanged from prior pixel transport — QR
-- is purely a transport upgrade, the same bytes flow end-to-end):
--   Header:    "APS1" magic + version byte + uint16 length + flags +
--              listing-generation byte (0 = legacy/unknown)
--   Listing:   has_listing byte; if 1: uint32 activityID + uint16 categoryID +
--              uint16 difficultyID + key_level byte +
--              len-prefixed dungeonName/listingName/comment (uint8 len + utf8)
--   Version:   has_version byte; if 1: len-prefixed addonVer/gameVer +
--              region_id byte + len-prefixed playerName
--   LeaderKey: has_leader_key byte; if 1: uint8 keyLevel +
--              uint16 challengeMapID + len-prefixed leaderName
--   Apps:      uint16 count; per applicant: uint32 id + uint8 member_idx +
--              uint8 classID + uint16 specID + uint16 ilvl + uint16 rioScore +
--              uint16 mainScore + uint8 rioProfile + uint8 rioBestKey +
--              uint8 rioBestDungeonKey + uint8 rioTimedAtTarget +
--              uint8 rioTimedAtMinus1 + uint8 rioTimedAtMinus2 +
--              uint8 rioCompletedAtMinus1 + uint8 rioDungeonCount +
--              uint8 role + uint8 nameLen + utf8 name (CLAMPED to 255 bytes)
--   Roster:    uint16 count; per current party/raid member: uint8 unitIndex +
--              uint8 flags + uint8 subgroup + same class/spec/score/RIO/role
--              tail as applicant rows, then nameLen + utf8 name.
--   Trailer:   uint32 CRC32 (IEEE 802.3) over [magic..last roster byte]
--
-- WHY keep the magic + CRC even though QR has its own ECC: the magic gives the
-- companion a quick "is this really our payload" check that catches
-- false-positive QR hits (e.g. user runs the companion against a folder with
-- random QR codes from another addon). CRC catches the rare corner where QR's
-- ECC reports success but a few bits flipped — empirically rare but
-- belt-and-suspenders.
--
-- Applicants sorted by ID before serialization → identical state produces
-- identical bytes → snapshot-hash dedup works reliably.

-- WoW classID 1-13 (retail Midnight). Inverse of LOCALIZED_CLASS_NAMES_MALE.
local CLASS_NAME_TO_ID = {
    WARRIOR=1, PALADIN=2, HUNTER=3, ROGUE=4, PRIEST=5, DEATHKNIGHT=6,
    SHAMAN=7, MAGE=8, WARLOCK=9, MONK=10, DRUID=11, DEMONHUNTER=12, EVOKER=13,
}
local ROLE_NAME_TO_BYTE = { TANK=0, HEALER=1, DAMAGER=2 }

-- LFG status values that mean "applicant gone" (won't appear in companion).
-- Whitelist-by-exclusion: enum names shifted across patches; safer than positive
-- match.
local APP_DEAD_STATUSES = {
    cancelled=true, declined=true, failed=true, timedout=true,
    invitedeclined=true, inviteaccepted=true,
    declined_full=true, declined_delisted=true,
}

local function _GetApplicantApplicationStatus(info)
    -- Current C_LFGList.GetApplicantInfo uses applicationStatus. Keep the older
    -- applicantStatus spelling as a compatibility fallback for stubs/build drift.
    local status = SafeEnumKey(info and info.applicationStatus, nil)
    if status == nil or status == "" then
        status = SafeEnumKey(info and info.applicantStatus, "")
    end
    return status
end

entryCreationKeyState.GetApplicantInfoForTransport = function(rawID)
    if not (C_LFGList and type(C_LFGList.GetApplicantInfo) == "function") then
        return nil, nil, nil
    end
    -- WHY: in Midnight applicant IDs can be secret/opaque tokens. Passing the
    -- token back to Blizzard APIs is safe, but arithmetic/comparison on it is
    -- not. Read the info table first, then use its clean applicantID for our
    -- own wire identity.
    local ok, info = pcall(C_LFGList.GetApplicantInfo, rawID)
    if not ok then return nil, nil, nil end
    info = SafeTable(info)
    if not info then return nil, nil, nil end

    local cleanID = math.floor(SafeNumber(info.applicantID, 0))
    local apiID = info.applicantID
    if cleanID <= 0 then
        cleanID = math.floor(SafeNumber(rawID, 0))
        apiID = rawID
    end
    if cleanID <= 0 then return nil, nil, nil end
    return cleanID, info, apiID
end

entryCreationKeyState.GetApplicantMemberInfoForTransport = function(apiID, memberIndex)
    if not (C_LFGList and type(C_LFGList.GetApplicantMemberInfo) == "function") then
        return false
    end
    -- Retail 12.x returns:
    -- name, class, localizedClass, level, itemLevel, honorLevel,
    -- tank, healer, damage, assignedRole, relationship, dungeonScore,
    -- pvpItemLevel, factionGroup, raceID, specID, isLeaver.
    -- Keep the original opaque applicant token for Blizzard's member API.
    local ok, name, class, _, _, ilvl, _, tank, healer, damage, assignedRole,
          _, dungeonScore, _, _, _, specID =
        pcall(C_LFGList.GetApplicantMemberInfo, apiID, memberIndex)
    if not ok then return false end

    local role = SafeEnumKey(assignedRole, "")
    if role ~= "TANK" and role ~= "HEALER" and role ~= "DAMAGER" then
        local tankOK = not IsSecretValue(tank) and tank == true
        local healerOK = not IsSecretValue(healer) and healer == true
        local damageOK = not IsSecretValue(damage) and damage == true
        if tankOK then
            role = "TANK"
        elseif healerOK then
            role = "HEALER"
        elseif damageOK then
            role = "DAMAGER"
        else
            role = "DAMAGER"
        end
    end
    return true, name, class, ilvl, role, dungeonScore, specID
end

-- Big-endian uint packing
local function _Uint32BE(n)
    n = math.floor(SafeNumber(n, 0)) % 4294967296
    return string.char(
        math.floor(n / 16777216) % 256,
        math.floor(n / 65536) % 256,
        math.floor(n / 256) % 256,
        n % 256
    )
end
local function _Uint16BE(n)
    n = math.floor(SafeNumber(n, 0)) % 65536
    return string.char(math.floor(n / 256), n % 256)
end

local function _ClampUInt16(n)
    n = math.floor(SafeNumber(n, 0))
    if n < 0 then return 0 end
    if n > 65535 then return 65535 end
    return n
end

local function _ClampUInt8(n)
    n = math.floor(SafeNumber(n, 0))
    if n < 0 then return 0 end
    if n > 255 then return 255 end
    return n
end

-- Append one already-SafeStr-cleaned value. CLAMPS to 255 bytes (safety).
local function _PackCleanLenStr(out, str)
    if #str > 255 then
        str = entryCreationKeyState.TruncateUTF8Bytes(str, 255)
    end
    table.insert(out, string.char(#str))
    table.insert(out, str)
end

local function _NormalizeKeystoneLevel(value)
    local n = math.floor(SafeNumber(value, 0))
    if n >= 2 and n <= 50 then return n end
    return 0
end

entryCreationKeyState.GetApplicantDungeonContextForTransport = function(apiID, memberIndex, activityID)
    local bestForDungeon, bestOverall = 0, 0
    activityID = math.floor(SafeNumber(activityID, 0))
    if activityID > 0 and C_LFGList
       and type(C_LFGList.GetApplicantDungeonScoreForListing) == "function" then
        local ok, info = pcall(C_LFGList.GetApplicantDungeonScoreForListing, apiID, memberIndex, activityID)
        if ok then
            info = SafeTable(info)
            if info then bestForDungeon = _NormalizeKeystoneLevel(info.bestRunLevel) end
        end
    end
    if C_LFGList and type(C_LFGList.GetApplicantBestDungeonScore) == "function" then
        local ok, info = pcall(C_LFGList.GetApplicantBestDungeonScore, apiID, memberIndex)
        if ok then
            info = SafeTable(info)
            if info then bestOverall = _NormalizeKeystoneLevel(info.bestRunLevel) end
        end
    end
    return bestForDungeon, bestOverall
end

local function _ExtractKeystoneLevelFromText(value)
    local s = SafeStr(value, "")
    if s == "" then return 0 end
    local m = s:match("%+(%d+)")
    return _NormalizeKeystoneLevel(m)
end

local function _ExtractKeystoneLevelFromShortKeyText(value)
    local keyLevel = _ExtractKeystoneLevelFromText(value)
    if keyLevel > 0 then return keyLevel end

    local s = SafeStr(value, "")
    if s == "" then return 0 end
    s = s:gsub("^%s+", ""):gsub("%s+$", "")
    -- Localized UI text can use width or symbol variants of the plus sign.
    -- Accept those only as a leading key marker; stripping arbitrary text down
    -- to digits turns titles such as "weekly in 15 minutes" into false keys.
    if #s > 40 then return 0 end
    local digits = s:match("^＋%s*(%d%d?)%f[%D]")
        or s:match("^﹢%s*(%d%d?)%f[%D]")
        or s:match("^➕%s*(%d%d?)%f[%D]")
    if not digits then return 0 end
    return _NormalizeKeystoneLevel(digits)
end

local function _ReadCleanWidgetText(widget)
    if not (widget and type(widget.GetText) == "function") then return "" end
    local ok, text = pcall(widget.GetText, widget)
    if not ok or IsSecretValue(text) then return "" end
    return SafeStr(text, "")
end

entryCreationKeyState.EntryListingCacheContext = function(entry)
    entry = SafeTable(entry)
    if not entry then return nil end
    local activityIDs = SafeTable(entry.activityIDs)
    local activityID = math.floor(SafeNumber(activityIDs and activityIDs[1], 0))
    if activityID <= 0 then
        activityID = math.floor(SafeNumber(entry.activityID, 0))
    end
    if activityID < 0 then activityID = 0 end
    local questID = math.floor(SafeNumber(entry.questID, 0))
    if questID < 0 then questID = 0 end
    return { activityID = activityID, questID = questID }
end

local function _EntryCreationCacheFresh(cache)
    local ENTRY_CREATION_KEY_CACHE_TTL = 3600
    cache = SafeTable(cache)
    if not cache then return false end
    if GetTime and (GetTime() - SafeNumber(cache.at, 0)) > ENTRY_CREATION_KEY_CACHE_TTL then
        return false
    end
    return true
end

local function _EntryCreationCacheMatchesListing(cache, listingContext)
    if not _EntryCreationCacheFresh(cache) then return false end
    listingContext = SafeTable(listingContext)
    if not listingContext then return false end

    local activityID = math.floor(SafeNumber(listingContext.activityID, 0))
    if activityID <= 0 then return false end

    local cacheActivityID = math.floor(SafeNumber(cache.activityID, 0))
    if cacheActivityID <= 0 or cacheActivityID ~= activityID then
        return false
    end

    local questID = math.floor(SafeNumber(listingContext.questID, 0))
    local cacheQuestID = math.floor(SafeNumber(cache.questID, 0))
    if cacheQuestID > 0 and questID > 0 and cacheQuestID ~= questID then
        return false
    end
    return true
end

local function _SameEntryListingCacheContext(a, b)
    a = SafeTable(a)
    b = SafeTable(b)
    if not a or not b then return false end
    return math.floor(SafeNumber(a.activityID, 0)) == math.floor(SafeNumber(b.activityID, 0))
       and math.floor(SafeNumber(a.questID, 0)) == math.floor(SafeNumber(b.questID, 0))
end

local function _ClearEntryCreationKeyLevelCache(reason)
    entryCreationKeyState.entryCreationKeyLevelCache = nil
    entryCreationKeyState.pendingEntryCreationKeyLevelCache = nil
    entryCreationKeyState.entryCreationKeyLevelCacheDecision = reason or "cleared"
end

local function _PublishPendingEntryCreationKeyLevelCache(listingContext)
    if GetTime
       and entryCreationKeyState.pendingEntryCreationKeyLevelCache
       and (GetTime() - SafeNumber(entryCreationKeyState.pendingEntryCreationKeyLevelCache.at, 0))
           > entryCreationKeyState.pendingTtl then
        entryCreationKeyState.pendingEntryCreationKeyLevelCache = nil
        entryCreationKeyState.entryCreationKeyLevelCacheDecision = "ignored: pending submit expired"
        return false
    end
    if not _EntryCreationCacheMatchesListing(entryCreationKeyState.pendingEntryCreationKeyLevelCache, listingContext) then
        entryCreationKeyState.pendingEntryCreationKeyLevelCache = nil
        return false
    end
    entryCreationKeyState.entryCreationKeyLevelCache = entryCreationKeyState.pendingEntryCreationKeyLevelCache
    entryCreationKeyState.pendingEntryCreationKeyLevelCache = nil
    entryCreationKeyState.entryCreationKeyLevelCacheDecision = "promoted pending submit"
    return true
end

entryCreationKeyState.ResolveCachedEntryCreationKeystoneLevel = function(activityID, questID)
    activityID = math.floor(SafeNumber(activityID, 0))
    if activityID <= 0 then
        return 0, "ignored: active activity unknown", false
    end
    local cache = entryCreationKeyState.entryCreationKeyLevelCache
    if not cache then return 0, nil, false end
    if not _EntryCreationCacheFresh(cache) then
        return 0, "ignored: expired", true
    end

    questID = math.floor(SafeNumber(questID, 0))
    if cache.activityID <= 0 or cache.activityID ~= activityID then
        return 0, "ignored: activity mismatch", false
    end
    if cache.questID > 0 and questID > 0 and cache.questID ~= questID then
        return 0, "ignored: quest mismatch", false
    end
    return _NormalizeKeystoneLevel(cache.keyLevel), "used", false
end

entryCreationKeyState.PeekCachedEntryCreationKeystoneLevel = function(activityID, questID)
    local level = entryCreationKeyState.ResolveCachedEntryCreationKeystoneLevel(activityID, questID)
    return level
end

local function _GetCachedEntryCreationKeystoneLevel(activityID, questID)
    local level, decision, clearExpired =
        entryCreationKeyState.ResolveCachedEntryCreationKeystoneLevel(activityID, questID)
    if clearExpired then
        entryCreationKeyState.entryCreationKeyLevelCache = nil
    end
    if decision then
        entryCreationKeyState.entryCreationKeyLevelCacheDecision = decision
    end
    return level
end

local function _ClearEntryCreationKeystoneLevelCache(activityID, questID)
    activityID = math.floor(SafeNumber(activityID, 0))
    questID = math.floor(SafeNumber(questID, 0))
    local listingContext = { activityID = activityID, questID = questID }
    if _EntryCreationCacheMatchesListing(entryCreationKeyState.pendingEntryCreationKeyLevelCache, listingContext) then
        entryCreationKeyState.pendingEntryCreationKeyLevelCache = nil
    end
    if _EntryCreationCacheMatchesListing(entryCreationKeyState.entryCreationKeyLevelCache, listingContext) then
        entryCreationKeyState.entryCreationKeyLevelCache = nil
        entryCreationKeyState.entryCreationKeyLevelCacheDecision = "cleared: form key unreadable"
    end
end

entryCreationKeyState.PrintDiagnostics = function()
    print("  entry creation hooks: " .. tostring(lfgEntryCreationHookState.hooksSetup)
          .. (lfgEntryCreationHookState.hookError
              and (" (error: " .. lfgEntryCreationHookState.hookError .. ")")
              or ""))
    local pendingCache = SafeTable(entryCreationKeyState.pendingEntryCreationKeyLevelCache)
    local publishedCache = SafeTable(entryCreationKeyState.entryCreationKeyLevelCache)
    print("  pendingEntryCreationCache.keyLevel: "
          .. tostring(pendingCache and pendingCache.keyLevel or 0))
    print("  pendingEntryCreationCache.activityID: "
          .. tostring(pendingCache and pendingCache.activityID or 0))
    print("  pendingEntryCreationCache.questID: "
          .. tostring(pendingCache and pendingCache.questID or 0))
    print("  publishedEntryCreationCache.keyLevel: "
          .. tostring(publishedCache and publishedCache.keyLevel or 0))
    print("  publishedEntryCreationCache.activityID: "
          .. tostring(publishedCache and publishedCache.activityID or 0))
    print("  publishedEntryCreationCache.questID: "
          .. tostring(publishedCache and publishedCache.questID or 0))
    print("  activeListingCache.generation: "
          .. tostring(entryCreationKeyState.activeListingGeneration))
    print("  activeListingCache.activityID: "
          .. tostring(entryCreationKeyState.activeListingCacheContext
                     and entryCreationKeyState.activeListingCacheContext.activityID or 0))
    print("  activeListingCache.questID: "
          .. tostring(entryCreationKeyState.activeListingCacheContext
                     and entryCreationKeyState.activeListingCacheContext.questID or 0))
    print("  listing cache decision: "
          .. tostring(entryCreationKeyState.entryCreationKeyLevelCacheDecision))
end

entryCreationKeyState.ReconcileEntryCreationKeyCache = function(listingContext)
    listingContext = SafeTable(listingContext)
    if not listingContext then
        if entryCreationKeyState.activeListingCacheContext then
            entryCreationKeyState.activeListingGeneration = entryCreationKeyState.activeListingGeneration + 1
            _ClearEntryCreationKeyLevelCache("listing-ended")
        else
            entryCreationKeyState.entryCreationKeyLevelCache = nil
            entryCreationKeyState.entryCreationKeyLevelCacheDecision = "idle"
        end
        entryCreationKeyState.activeListingCacheContext = nil
        entryCreationKeyState.activeListingMaybeChanged = false
        return
    end

    if math.floor(SafeNumber(listingContext.activityID, 0)) <= 0 then
        entryCreationKeyState.activeListingCacheContext = listingContext
        entryCreationKeyState.activeListingGeneration = entryCreationKeyState.activeListingGeneration + 1
        entryCreationKeyState.activeListingMaybeChanged = false
        _ClearEntryCreationKeyLevelCache("ignored: active activity unknown")
        return
    end

    local listingChanged = entryCreationKeyState.activeListingMaybeChanged
       or not _SameEntryListingCacheContext(entryCreationKeyState.activeListingCacheContext, listingContext)
    if listingChanged then
        entryCreationKeyState.activeListingGeneration = entryCreationKeyState.activeListingGeneration + 1
        entryCreationKeyState.activeListingCacheContext = listingContext
        if not _PublishPendingEntryCreationKeyLevelCache(listingContext) then
            _ClearEntryCreationKeyLevelCache("stale-after-entry-update")
        end
        entryCreationKeyState.activeListingMaybeChanged = false
        return
    end

    entryCreationKeyState.activeListingCacheContext = listingContext
    if entryCreationKeyState.pendingEntryCreationKeyLevelCache then
        _PublishPendingEntryCreationKeyLevelCache(listingContext)
    end
    entryCreationKeyState.activeListingMaybeChanged = false
end

local function _RememberEntryCreationKeystoneLevel(panel, reason)
    if not panel then return false end

    local activityID = panel.selectedActivity
    if IsSecretValue(activityID) then return false end
    activityID = math.floor(SafeNumber(activityID, 0))
    if activityID <= 0 then return false end

    local activityInfo = nil
    if C_LFGList and C_LFGList.GetActivityInfoTable then
        activityInfo = SafeTable(C_LFGList.GetActivityInfoTable(activityID))
    end
    if not activityInfo then return false end
    local isMythicPlusActivity = activityInfo.isMythicPlusActivity
    if IsSecretValue(isMythicPlusActivity)
       or IsSecretValue(activityInfo.categoryID) then
        return false
    end
    if isMythicPlusActivity ~= true
       and math.floor(SafeNumber(activityInfo.categoryID, 0)) ~= 2 then
        return false
    end

    local nameText = _ReadCleanWidgetText(panel.Name)
    local commentText = _ReadCleanWidgetText(panel.Description)
    local keyLevel = _ExtractKeystoneLevelFromShortKeyText(nameText)
    if keyLevel == 0 then
        keyLevel = _ExtractKeystoneLevelFromText(commentText)
    end
    local questID = math.floor(SafeNumber(panel.questID, 0))
    if keyLevel == 0 then
        _ClearEntryCreationKeystoneLevelCache(activityID, questID)
        return false
    end

    entryCreationKeyState.pendingEntryCreationKeyLevelCache = {
        activityID = activityID,
        questID = questID,
        keyLevel = keyLevel,
        at = GetTime and GetTime() or 0,
    }
    if KeystoneLensBridgeDB and KeystoneLensBridgeDB.debug then
        print("|cff999999[APS-debug]|r LFG posted key cached: +"
              .. tostring(keyLevel)
              .. (reason and (" (" .. reason .. ")") or ""))
    end
    return true
end

local function _HookEntryCreationKeyCapture(panel)
    if not panel or lfgEntryCreationKeyCaptureHooked[panel] then return end
    lfgEntryCreationKeyCaptureHooked[panel] = true

    local button = panel.ListGroupButton
    if button and type(button.HookScript) == "function" then
        button:HookScript("OnClick", function()
            _RememberEntryCreationKeystoneLevel(panel, "button")
        end)
    end

    local nameBox = panel.Name
    if nameBox and type(nameBox.HookScript) == "function" then
        nameBox:HookScript("OnEnterPressed", function()
            _RememberEntryCreationKeystoneLevel(panel, "enter")
        end)
    end
end

local function _ApplicationViewerTextCandidates(viewer)
    return {
        { label = "EntryName", fontString = viewer.EntryName },
        {
            label = "DescriptionFrame.Text",
            fontString = viewer.DescriptionFrame and viewer.DescriptionFrame.Text,
        },
    }
end

local function _GetVisibleApplicationViewerKeystoneLevel()
    local lfgFrame = _G.LFGListFrame
    local viewer = lfgFrame and lfgFrame.ApplicationViewer
    if not viewer then return 0 end
    if type(viewer.IsShown) == "function" and not viewer:IsShown() then return 0 end

    for _, candidate in ipairs(_ApplicationViewerTextCandidates(viewer)) do
        local fontString = candidate.fontString
        if fontString and type(fontString.GetText) == "function" then
            local ok, text = pcall(fontString.GetText, fontString)
            if ok and not IsSecretValue(text) then
                local keyLevel = _ExtractKeystoneLevelFromShortKeyText(text)
                if keyLevel > 0 then
                    return keyLevel
                end
            end
        end
    end
    return 0
end

local function _GetVisibleApplicationViewerKeystoneDiagnostics()
    local lines = {}
    local lfgFrame = _G.LFGListFrame
    local viewer = lfgFrame and lfgFrame.ApplicationViewer
    lines[#lines + 1] = "  visibleFrame.viewer: " .. tostring(viewer ~= nil)
    if not viewer then return lines end

    local shown = "n/a"
    if type(viewer.IsShown) == "function" then
        local ok, result = pcall(viewer.IsShown, viewer)
        shown = ok and tostring(result) or "<error>"
    end
    lines[#lines + 1] = "  visibleFrame.viewerShown: " .. shown

    for _, candidate in ipairs(_ApplicationViewerTextCandidates(viewer)) do
        local label = candidate.label
        local fontString = candidate.fontString
        if fontString and type(fontString.GetText) == "function" then
            local ok, text = pcall(fontString.GetText, fontString)
            if ok then
                local isSecret = IsSecretValue(text)
                local keyLevel = isSecret and 0 or _ExtractKeystoneLevelFromShortKeyText(text)
                lines[#lines + 1] = "  visibleFrame." .. label
                    .. ": " .. SafeDiag(text)
                    .. " secret=" .. tostring(isSecret)
                    .. " key=" .. tostring(keyLevel)
            else
                lines[#lines + 1] = "  visibleFrame." .. label .. ": <error>"
            end
        else
            lines[#lines + 1] = "  visibleFrame." .. label .. ": nil"
        end
    end
    return lines
end

local function _GetActivityInfoForListing(activityID, questID)
    if not (C_LFGList and C_LFGList.GetActivityInfoTable) then return nil end
    activityID = math.floor(SafeNumber(activityID, 0))
    if activityID <= 0 then return nil end
    questID = math.floor(SafeNumber(questID, 0))
    if questID > 0 then
        local info = SafeTable(C_LFGList.GetActivityInfoTable(activityID, questID))
        if info then return info end
    end
    return SafeTable(C_LFGList.GetActivityInfoTable(activityID))
end

local function _ActivityInfoListingName(activityInfo)
    activityInfo = SafeTable(activityInfo)
    if not activityInfo then return "?" end
    local shortName = SafeStr(activityInfo.shortName, "?")
    if shortName ~= "" and shortName ~= "?" then
        return shortName
    end
    local fullName = SafeStr(activityInfo.fullName, "?")
    return (fullName ~= "" and fullName) or "?"
end

local function _GetOwnedKeystoneListingInfo()
    if not (C_LFGList and C_LFGList.GetOwnedKeystoneActivityAndGroupAndLevel) then
        return 0, 0, 0, nil
    end
    local ok, ownedActivityID, ownedGroupID, ownedLevel = pcall(
        C_LFGList.GetOwnedKeystoneActivityAndGroupAndLevel
    )
    if not ok then return 0, 0, 0, nil end
    ownedActivityID = math.floor(SafeNumber(ownedActivityID, 0))
    ownedGroupID = math.floor(SafeNumber(ownedGroupID, 0))
    ownedLevel = _NormalizeKeystoneLevel(ownedLevel)
    local ownedInfo = nil
    if ownedActivityID > 0 then
        ownedInfo = _GetActivityInfoForListing(ownedActivityID, 0)
    end
    return ownedActivityID, ownedGroupID, ownedLevel, ownedInfo
end

entryCreationKeyState.CanUseOwnedKeystoneForListingFallback = function()
    if not (IsInGroup and IsInGroup()) then return true end
    if entryCreationKeyState.CleanUnitIsGroupLeader("player") == true then return true end
    return false
end

local function _GetListingKeystoneLevel(activityID, questID, listingName, listingComment, activityInfo)
    -- WARNING: C_LFGList.GetKeystoneForActivity can report the host's owned
    -- key for this dungeon instead of the active posted listing level.
    local keyLevel = _ExtractKeystoneLevelFromShortKeyText(listingName)
    if keyLevel == 0 then
        keyLevel = _ExtractKeystoneLevelFromText(listingComment)
    end
    if keyLevel == 0 then
        keyLevel = _GetVisibleApplicationViewerKeystoneLevel()
    end
    if keyLevel == 0 then
        keyLevel = _GetCachedEntryCreationKeystoneLevel(activityID, questID)
    end
    activityInfo = SafeTable(activityInfo)
    if keyLevel == 0 and activityInfo then
        local activityShortName = SafeStr(activityInfo.shortName, "")
        keyLevel = _ExtractKeystoneLevelFromText(activityShortName)
    end
    if keyLevel == 0 and activityInfo then
        local activityFullName = SafeStr(activityInfo.fullName, "")
        keyLevel = _ExtractKeystoneLevelFromText(activityFullName)
    end
    return keyLevel
end

local function _RaiderIODungeonMatchesActivity(dungeon, listingActivityID)
    dungeon = SafeTable(dungeon)
    listingActivityID = math.floor(SafeNumber(listingActivityID, 0))
    if not dungeon or listingActivityID <= 0 then return false end

    local lfdActivityIDs = SafeTable(dungeon.lfd_activity_ids)
    if lfdActivityIDs then
        for _, rawActivityID in ipairs(lfdActivityIDs) do
            if math.floor(SafeNumber(rawActivityID, 0)) == listingActivityID then
                return true
            end
        end
    end

    return math.floor(SafeNumber(dungeon.keystone_instance, 0)) == listingActivityID
end

local function _EmptyRaiderIOMPlusSummary(currentScore, mainScore)
    return {
        currentScore = _ClampUInt16(currentScore),
        mainScore = _ClampUInt16(mainScore),
        hasProfile = false,
        bestKey = 0,
        bestDungeonKey = 0,
        timedAtOrAbove = 0,
        timedAtOrAboveMinus1 = 0,
        timedAtOrAboveMinus2 = 0,
        completedAtOrAboveMinus1 = 0,
        dungeonCount = 0,
    }
end

local function _RaiderIOProfileLookupNameFromCleanName(memberName, playerRealm)
    if memberName == "" or memberName == "?" or memberName:find("-", 1, true) then
        return memberName
    end
    if playerRealm == nil then
        local _playerName, resolvedRealm = UnitFullName("player")
        playerRealm = SafeStr(resolvedRealm, "")
    end
    if playerRealm == "" then return memberName end
    -- WHY: LFG may emit same-realm applicants as bare "Name"; RaiderIO profile
    -- lookups need the realm-qualified key to expose per-dungeon history.
    return memberName .. "-" .. playerRealm
end

local function _GetRaiderIOMPlusSummaryForCleanName(memberName, listingActivityID, targetKey)
    -- RaiderIO is optional. Callers pass only a SafeStr-cleaned applicant name:
    -- the raw LFG name can be secret-tagged, and RaiderIO's public API performs
    -- string parsing internally.
    if memberName == "" or memberName == "?" then
        return entryCreationKeyState.emptyRaiderIOMPlusSummary
    end
    local rio = SafeTable(_G.RaiderIO)
    if not rio or type(rio.GetProfile) ~= "function" then
        return entryCreationKeyState.emptyRaiderIOMPlusSummary
    end

    listingActivityID = math.floor(SafeNumber(listingActivityID, 0))
    targetKey = _NormalizeKeystoneLevel(targetKey)
    local rioSummaryCache = entryCreationKeyState.rioMPlusSummaryCache
    if not rioSummaryCache then
        rioSummaryCache = {}
        entryCreationKeyState.rioMPlusSummaryCache = rioSummaryCache
    end
    local cacheKey = memberName .. "\031" .. tostring(listingActivityID)
        .. "\031" .. tostring(targetKey)
    local cachedSummary = rioSummaryCache[cacheKey]
    if cachedSummary then return cachedSummary end

    local profileName, profileRealm = memberName:match("^([^-]+)%-(.+)$")
    local ok, profile
    if profileName and profileRealm and profileRealm ~= "" then
        ok, profile = pcall(rio.GetProfile, profileName, profileRealm)
    else
        ok, profile = pcall(rio.GetProfile, memberName)
    end
    if not ok or IsSecretValue(profile) then
        return entryCreationKeyState.emptyRaiderIOMPlusSummary
    end
    profile = SafeTable(profile)
    if not profile then return entryCreationKeyState.emptyRaiderIOMPlusSummary end
    local function StoreRaiderIOSummary(summary)
        rioSummaryCache[cacheKey] = summary
        return summary
    end

    local keystoneProfile = SafeTable(profile.mythicKeystoneProfile)
    if not keystoneProfile then
        return StoreRaiderIOSummary(entryCreationKeyState.emptyRaiderIOMPlusSummary)
    end
    -- Raider.IO documents hasRenderableData=false as stale data that must be ignored.
    if keystoneProfile.hasRenderableData == false then
        return StoreRaiderIOSummary(entryCreationKeyState.emptyRaiderIOMPlusSummary)
    end
    if IsSecretValue(keystoneProfile.blocked) or keystoneProfile.blocked then
        return StoreRaiderIOSummary(entryCreationKeyState.emptyRaiderIOMPlusSummary)
    end

    local current = SafeTable(keystoneProfile.mplusCurrent)
    local currentScore = keystoneProfile.currentScore
    if current then
        currentScore = current.score
    end
    local mainCurrent = SafeTable(keystoneProfile.mplusMainCurrent)
    local mainScore = keystoneProfile.mainCurrentScore
    if mainCurrent then
        mainScore = mainCurrent.score
    end
    local summary = _EmptyRaiderIOMPlusSummary(currentScore, mainScore)

    local sortedDungeons = SafeTable(keystoneProfile.sortedDungeons)
    if not sortedDungeons then return StoreRaiderIOSummary(summary) end

    local targetMinus1 = targetKey > 0 and math.max(2, targetKey - 1) or 0
    local targetMinus2 = targetKey > 0 and math.max(2, targetKey - 2) or 0
    summary.hasProfile = true

    for _, sortedDungeon in ipairs(sortedDungeons) do
        local entry = SafeTable(sortedDungeon)
        if entry then
            local keyLevel = _NormalizeKeystoneLevel(entry.level)
            if keyLevel > 0 then
                local chests = math.floor(SafeNumber(entry.chests, 0))
                local timed = chests > 0
                local dungeon = SafeTable(entry.dungeon)
                summary.dungeonCount = summary.dungeonCount + 1
                if timed and keyLevel > summary.bestKey then
                    summary.bestKey = keyLevel
                end
                if timed
                   and _RaiderIODungeonMatchesActivity(dungeon, listingActivityID)
                   and keyLevel > summary.bestDungeonKey then
                    summary.bestDungeonKey = keyLevel
                end
                if targetKey > 0 and timed and keyLevel >= targetKey then
                    summary.timedAtOrAbove = summary.timedAtOrAbove + 1
                end
                if targetMinus1 > 0 then
                    if timed and keyLevel >= targetMinus1 then
                        summary.timedAtOrAboveMinus1 =
                            summary.timedAtOrAboveMinus1 + 1
                    end
                    if keyLevel >= targetMinus1 then
                        summary.completedAtOrAboveMinus1 =
                            summary.completedAtOrAboveMinus1 + 1
                    end
                end
                if targetMinus2 > 0 and timed and keyLevel >= targetMinus2 then
                    summary.timedAtOrAboveMinus2 =
                        summary.timedAtOrAboveMinus2 + 1
                end
            end
        end
    end

    summary.bestKey = _ClampUInt8(summary.bestKey)
    summary.bestDungeonKey = _ClampUInt8(summary.bestDungeonKey)
    summary.timedAtOrAbove = _ClampUInt8(summary.timedAtOrAbove)
    summary.timedAtOrAboveMinus1 = _ClampUInt8(summary.timedAtOrAboveMinus1)
    summary.timedAtOrAboveMinus2 = _ClampUInt8(summary.timedAtOrAboveMinus2)
    summary.completedAtOrAboveMinus1 =
        _ClampUInt8(summary.completedAtOrAboveMinus1)
    summary.dungeonCount = _ClampUInt8(summary.dungeonCount)
    return StoreRaiderIOSummary(summary)
end

entryCreationKeyState.AppendRaiderIOMPlusSummary = function(out, summary)
    table.insert(out, _Uint16BE(summary.mainScore))
    table.insert(out, string.char(summary.hasProfile and 1 or 0))
    table.insert(out, string.char(summary.bestKey))
    table.insert(out, string.char(summary.bestDungeonKey))
    table.insert(out, string.char(summary.timedAtOrAbove))
    table.insert(out, string.char(summary.timedAtOrAboveMinus1))
    table.insert(out, string.char(summary.timedAtOrAboveMinus2))
    table.insert(out, string.char(summary.completedAtOrAboveMinus1))
    table.insert(out, string.char(summary.dungeonCount))
end

local function _IsPlaceholderCleanUnitName(name)
    local sep = name:find("-", 1, true)
    local base = sep and name:sub(1, sep - 1) or name
    if base == "" or base == "?" then return true end
    local unknownObject = entryCreationKeyState.cleanUnknownObjectLabel
    if unknownObject == nil and type(_G.UNKNOWNOBJECT) == "string" then
        unknownObject = SafeStr(_G.UNKNOWNOBJECT, "")
        entryCreationKeyState.cleanUnknownObjectLabel = unknownObject
    end
    if unknownObject ~= "" and base == unknownObject then return true end
    local unknown = entryCreationKeyState.cleanUnknownLabel
    if unknown == nil and type(_G.UNKNOWN) == "string" then
        unknown = SafeStr(_G.UNKNOWN, "")
        entryCreationKeyState.cleanUnknownLabel = unknown
    end
    if unknown ~= "" and base == unknown then return true end
    return base == "Unknown" or base == "UNKNOWN" or base == "UNKNOWNOBJECT"
end

local function _UnitFullNameForTransport(unit)
    local name, realm = "", ""
    if UnitFullName then
        local ok, unitName, unitRealm = pcall(UnitFullName, unit)
        if ok then
            name = SafeStr(unitName, "")
            realm = SafeStr(unitRealm, "")
        end
    end
    if name == "" and GetUnitName then
        local ok, unitName = pcall(GetUnitName, unit, true)
        if ok then name = SafeStr(unitName, "") end
    end
    if _IsPlaceholderCleanUnitName(name) then return "" end
    if name:find("-", 1, true) then return name end
    if realm == "" and UnitFullName then
        local okPlayer, _playerName, playerRealm = pcall(UnitFullName, "player")
        if okPlayer then realm = SafeStr(playerRealm, "") end
    end
    if realm ~= "" then return name .. "-" .. realm end
    return name
end

local function _UnitClassIDForRoster(unit)
    if not UnitClass then return 0 end
    local ok, _localized, classToken, classID = pcall(UnitClass, unit)
    if not ok then return 0 end
    classID = math.floor(SafeNumber(classID, 0))
    if classID > 0 then return classID end
    classToken = SafeEnumKey(classToken, "")
    return CLASS_NAME_TO_ID[classToken] or 0
end

local rosterInspectSpecByGUID = {}
local rosterInspectPendingGUID = nil
local rosterInspectLastRequestTime = 0
local ROSTER_INSPECT_THROTTLE_S = 1.0
local ROSTER_INSPECT_TIMEOUT_S = 4.0

local function _UnitExistsForRoster(unit)
    if unit == "player" then return true end
    local exists = entryCreationKeyState.CleanUnitAPIBoolean(UnitExists, unit)
    if exists == nil then
        entryCreationKeyState.NoteRosterIdentityReadUnknown("unit-exists-unknown")
    end
    return exists == true
end

local function _UnitIsSelfForRoster(unit)
    if unit == "player" then return true end
    return entryCreationKeyState.CleanUnitAPIBoolean(UnitIsUnit, unit, "player") == true
end

local function _ForEachRosterUnit(callback)
    if type(callback) ~= "function" then return end
    local groupCount = math.floor(SafeNumber(GetNumGroupMembers and GetNumGroupMembers(), 0))
    if groupCount <= 0 then return end

    if IsInRaid and IsInRaid() then
        if groupCount > 40 then groupCount = 40 end
        for i = 1, groupCount do
            if callback("raid" .. i) then return end
        end
        return
    end

    if callback("player") then return end
    for i = 1, 4 do
        local unit = "party" .. i
        if _UnitExistsForRoster(unit) and callback(unit) then return end
    end
end

local function _FindRosterUnitByGUID(guid)
    guid = SafeStr(guid, "")
    if guid == "" then return nil end
    local found = nil
    _ForEachRosterUnit(function(unit)
        if entryCreationKeyState.UnitGUIDForRoster(unit) == guid then
            found = unit
            return true
        end
        return false
    end)
    return found
end

entryCreationKeyState.ReleaseOwnedRosterInspect = function()
    if not rosterInspectPendingGUID then return false end
    rosterInspectPendingGUID = nil
    if ClearInspectPlayer then pcall(ClearInspectPlayer) end
    return true
end

entryCreationKeyState.ClearRosterInspectDataForGUID = function(guid)
    guid = SafeStr(guid, "")
    if guid == "" then return end
    rosterInspectSpecByGUID[guid] = nil
    entryCreationKeyState.rosterInspectIlvlByGUID[guid] = nil
    if rosterInspectPendingGUID == guid then
        entryCreationKeyState.ReleaseOwnedRosterInspect()
    end
    entryCreationKeyState.ClearRosterInspectFailureForGUID(guid)
end

entryCreationKeyState.ResetRosterInspectDataCache = function()
    rosterInspectSpecByGUID = {}
    entryCreationKeyState.rosterInspectIlvlByGUID = {}
    entryCreationKeyState.rosterInspectKnownGUIDs = {}
    entryCreationKeyState.ReleaseOwnedRosterInspect()
end

entryCreationKeyState.ReconcileRosterInspectMembership = function()
    local currentGUIDs = {}
    local expectedCount = math.floor(SafeNumber(
        GetNumGroupMembers and GetNumGroupMembers(),
        0
    ))
    local visitedCount = 0
    local complete = true
    _ForEachRosterUnit(function(unit)
        visitedCount = visitedCount + 1
        local guid = entryCreationKeyState.UnitGUIDForRoster(unit)
        if guid == "" then
            complete = false
        else
            currentGUIDs[guid] = true
        end
        return false
    end)
    if visitedCount ~= expectedCount then complete = false end

    if not complete then
        -- A secret/unavailable unit identity makes selective reconciliation
        -- unsafe. Prefer fresh inspection work over emitting stale member data.
        entryCreationKeyState.ResetRosterInspectDataCache()
        entryCreationKeyState.ClearRosterInspectFailureState()
    else
        for guid in pairs(entryCreationKeyState.rosterInspectKnownGUIDs) do
            if not currentGUIDs[guid] then
                entryCreationKeyState.ClearRosterInspectDataForGUID(guid)
            end
        end
    end
    entryCreationKeyState.rosterInspectKnownGUIDs = currentGUIDs
    return complete
end

local function _InvalidateRosterSpecCacheForUnit(unit)
    local guid = entryCreationKeyState.UnitGUIDForRoster(unit)
    if guid ~= "" then
        entryCreationKeyState.ClearRosterInspectDataForGUID(guid)
        return
    end
    entryCreationKeyState.ResetRosterInspectDataCache()
    entryCreationKeyState.ClearRosterInspectFailureState()
end

local function _MaybeRequestRosterInspect(unit, guid, isSelf)
    if not (NotifyInspect and CanInspect) then return false, "api" end
    if isSelf == nil then isSelf = _UnitIsSelfForRoster(unit) end
    if isSelf then return false, "self" end
    guid = SafeStr(guid, "")
    if guid == "" then return false, "guid" end
    if entryCreationKeyState.RosterUnitHasResolvedInspectData(unit, guid, isSelf) then
        return false, "cached"
    end

    local now = GetTime and GetTime() or 0
    if entryCreationKeyState.RosterInspectRetryBlocked(guid, now) then
        return false, "retry-budget"
    end
    if rosterInspectPendingGUID == guid
       and (now - rosterInspectLastRequestTime) < ROSTER_INSPECT_TIMEOUT_S then
        return false, "pending"
    end
    if rosterInspectPendingGUID
       and rosterInspectPendingGUID ~= guid
       and (now - rosterInspectLastRequestTime) < ROSTER_INSPECT_TIMEOUT_S then
        return false, "pending"
    end
    if (now - rosterInspectLastRequestTime) < ROSTER_INSPECT_THROTTLE_S then
        return false, "throttle"
    end
    if InCombatLockdown and InCombatLockdown() then return false, "combat" end

    if entryCreationKeyState.CleanUnitAPIBoolean(CanInspect, unit) ~= true then
        return false, "uninspectable"
    end
    local ok = pcall(NotifyInspect, unit)
    if ok then
        rosterInspectPendingGUID = guid
        rosterInspectLastRequestTime = now
        return true, "requested"
    end
    return false, "notify"
end

-- WARNING: keep these as entryCreationKeyState fields instead of new top-level
-- locals; this large Lua 5.1 file is already at local/upvalue limits.
entryCreationKeyState.rosterInspectBatchDirtyPending = false
entryCreationKeyState.rosterInspectBatchSkippedGUIDs = nil
-- WHY: batch state is cleared after each partial snapshot, so unresolved GUID
-- budgets must live for the whole listing session or every poll retries forever.
entryCreationKeyState.rosterInspectFailuresByGUID = {}
entryCreationKeyState.rosterInspectRetryAfterByGUID = {}
entryCreationKeyState.rosterInspectExhaustedGUIDs = {}
entryCreationKeyState.rosterInspectBatchRetryToken = 0
entryCreationKeyState.rosterInspectBatchRetryDeadline = nil
entryCreationKeyState.rosterInspectBatchRetrySessionGen = nil
entryCreationKeyState.rosterInspectBatchCombatDeferred = false
entryCreationKeyState.rosterInspectBatchLastBlockReason = nil
entryCreationKeyState.CachedRosterInspectItemLevel = function(guid)
    guid = SafeStr(guid, "")
    if guid == "" then return 0 end
    return _ClampUInt16(SafeRoundedNumber(entryCreationKeyState.rosterInspectIlvlByGUID[guid], 0))
end
entryCreationKeyState.ReadRosterInspectItemLevel = function(unit)
    if not (C_PaperDollInfo and type(C_PaperDollInfo.GetInspectItemLevel) == "function") then
        return 0
    end
    local ok, ilvl = pcall(C_PaperDollInfo.GetInspectItemLevel, unit)
    if not ok or IsSecretValue(ilvl) then return 0 end
    return _ClampUInt16(SafeRoundedNumber(ilvl, 0))
end
entryCreationKeyState.RosterUnitHasResolvedInspectData = function(unit, guid, isSelf)
    if isSelf == nil then isSelf = _UnitIsSelfForRoster(unit) end
    if isSelf then return true end
    guid = SafeStr(guid, "")
    if guid == "" then return false end

    local hasSpec = false
    local cachedSpecID = _ClampUInt16(SafeNumber(rosterInspectSpecByGUID[guid], 0))
    if cachedSpecID > 0 then
        hasSpec = true
    elseif GetInspectSpecialization then
        local ok, specID = pcall(GetInspectSpecialization, unit)
        specID = ok and _ClampUInt16(SafeNumber(specID, 0)) or 0
        if specID > 0 then
            rosterInspectSpecByGUID[guid] = specID
            hasSpec = true
        end
    end

    local hasIlvl = true
    if C_PaperDollInfo and type(C_PaperDollInfo.GetInspectItemLevel) == "function" then
        hasIlvl = entryCreationKeyState.CachedRosterInspectItemLevel(guid) > 0
        if not hasIlvl then
            local ilvl = entryCreationKeyState.ReadRosterInspectItemLevel(unit)
            if ilvl > 0 then
                entryCreationKeyState.rosterInspectIlvlByGUID[guid] = ilvl
                hasIlvl = true
            end
        end
    end

    local resolved = hasSpec and hasIlvl
    if resolved then
        entryCreationKeyState.ClearRosterInspectFailureForGUID(guid)
    end
    return resolved
end
entryCreationKeyState.ClearRosterInspectFailureForGUID = function(guid)
    guid = SafeStr(guid, "")
    if guid == "" then return end
    entryCreationKeyState.rosterInspectFailuresByGUID[guid] = nil
    entryCreationKeyState.rosterInspectRetryAfterByGUID[guid] = nil
    entryCreationKeyState.rosterInspectExhaustedGUIDs[guid] = nil
end
entryCreationKeyState.ClearRosterInspectFailureState = function()
    entryCreationKeyState.rosterInspectFailuresByGUID = {}
    entryCreationKeyState.rosterInspectRetryAfterByGUID = {}
    entryCreationKeyState.rosterInspectExhaustedGUIDs = {}
end
entryCreationKeyState.MarkRosterInspectAttemptFailed = function(guid, now)
    guid = SafeStr(guid, "")
    if guid == "" then return 0 end
    now = SafeNumber(now, 0)
    local failureCount = math.floor(SafeNumber(
        entryCreationKeyState.rosterInspectFailuresByGUID[guid],
        0
    )) + 1
    entryCreationKeyState.rosterInspectFailuresByGUID[guid] = failureCount
    if failureCount >= entryCreationKeyState.ROSTER_INSPECT_MAX_TIMEOUTS_PER_SESSION then
        entryCreationKeyState.rosterInspectRetryAfterByGUID[guid] = nil
        entryCreationKeyState.rosterInspectExhaustedGUIDs[guid] = true
    else
        entryCreationKeyState.rosterInspectRetryAfterByGUID[guid] =
            now + entryCreationKeyState.ROSTER_INSPECT_RETRY_COOLDOWN_S
    end
    return failureCount
end
entryCreationKeyState.RosterInspectRetryBlocked = function(guid, now)
    guid = SafeStr(guid, "")
    if guid == "" then return true end
    if entryCreationKeyState.rosterInspectExhaustedGUIDs[guid] then return true end
    local retryAfter = SafeNumber(
        entryCreationKeyState.rosterInspectRetryAfterByGUID[guid],
        0
    )
    if retryAfter <= 0 then return false end
    now = SafeNumber(now, 0)
    if now < retryAfter then return true end
    entryCreationKeyState.rosterInspectRetryAfterByGUID[guid] = nil
    return false
end
entryCreationKeyState.ClearRosterInspectBatchState = function()
    entryCreationKeyState.rosterInspectBatchDirtyPending = false
    entryCreationKeyState.rosterInspectBatchSkippedGUIDs = nil
    entryCreationKeyState.rosterInspectBatchCombatDeferred = false
    entryCreationKeyState.rosterInspectBatchLastBlockReason = nil
    entryCreationKeyState.rosterInspectBatchRetryDeadline = nil
    entryCreationKeyState.rosterInspectBatchRetrySessionGen = nil
    entryCreationKeyState.rosterInspectBatchRetryToken =
        (entryCreationKeyState.rosterInspectBatchRetryToken or 0) + 1
    entryCreationKeyState.ReleaseOwnedRosterInspect()
end
entryCreationKeyState.ClearRosterLoadRetryState = function()
    entryCreationKeyState.rosterLoadRetryDeadline = nil
    entryCreationKeyState.rosterLoadRetrySessionGen = nil
    entryCreationKeyState.rosterLoadRetryAttempt = 0
    entryCreationKeyState.rosterLoadRetryReady = true
    entryCreationKeyState.rosterLoadRetryExhausted = false
    entryCreationKeyState.rosterLoadRetryToken =
        (entryCreationKeyState.rosterLoadRetryToken or 0) + 1
end
entryCreationKeyState.ShouldAttemptRosterLoad = function()
    return entryCreationKeyState.rosterLoadRetryReady == true
        and not entryCreationKeyState.rosterLoadRetryExhausted
end
entryCreationKeyState.ClearRosterCompositionChanged = function()
    entryCreationKeyState.rosterChangedSinceLastPayload = false
    entryCreationKeyState.rosterChangePreflightDeadline = nil
    entryCreationKeyState.rosterChangePreflightToken =
        (entryCreationKeyState.rosterChangePreflightToken or 0) + 1
end
entryCreationKeyState.MarkRosterCompositionChanged = function()
    -- A real roster event is new evidence. Cancel any stale timer/exhaustion so
    -- the next clean transport tick gets one fresh bounded attempt immediately.
    entryCreationKeyState.ClearRosterLoadRetryState()
    entryCreationKeyState.rosterChangedSinceLastPayload = true
    entryCreationKeyState.transportDirtyGeneration =
        (entryCreationKeyState.transportDirtyGeneration or 0) + 1
    local now = GetTime and GetTime() or 0
    local delay = entryCreationKeyState.ROSTER_CHANGE_PREFLIGHT_DEADLINE_S
    entryCreationKeyState.rosterChangePreflightDeadline = now + delay
    entryCreationKeyState.rosterChangePreflightToken =
        (entryCreationKeyState.rosterChangePreflightToken or 0) + 1
    local retryToken = entryCreationKeyState.rosterChangePreflightToken
    local retrySessionGen = sessionGen
    if C_Timer and C_Timer.After then
        C_Timer.After(delay, function()
            if retryToken ~= entryCreationKeyState.rosterChangePreflightToken then
                return
            end
            if retrySessionGen ~= sessionGen then return end
            if not entryCreationKeyState.rosterChangedSinceLastPayload then return end
            if not (KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled) then return end
            if not isSessionActive then return end
            pendingShotDirty = true
            MarkDirty("rosterdeadline")
        end)
    end
end
entryCreationKeyState.ShouldDeferRosterChangeForPreflight = function()
    if not entryCreationKeyState.rosterChangedSinceLastPayload then return true end
    local deadline = entryCreationKeyState.rosterChangePreflightDeadline
    if not deadline then return false end
    local now = GetTime and GetTime() or 0
    return now < deadline
end
entryCreationKeyState.PrintRosterInspectBatchDiagnostics = function()
    local skippedInspectCount = 0
    local inspectCooldownCount = 0
    local exhaustedInspectCount = 0
    if entryCreationKeyState.rosterInspectBatchSkippedGUIDs then
        for _ in pairs(entryCreationKeyState.rosterInspectBatchSkippedGUIDs) do
            skippedInspectCount = skippedInspectCount + 1
        end
    end
    for _, retryAfter in pairs(entryCreationKeyState.rosterInspectRetryAfterByGUID) do
        if SafeNumber(retryAfter, 0) > GetTime() then
            inspectCooldownCount = inspectCooldownCount + 1
        end
    end
    for _ in pairs(entryCreationKeyState.rosterInspectExhaustedGUIDs) do
        exhaustedInspectCount = exhaustedInspectCount + 1
    end
    local pendingInspectAge = "n/a"
    if rosterInspectPendingGUID and rosterInspectLastRequestTime > 0 then
        pendingInspectAge = string.format("%.1fs", GetTime() - rosterInspectLastRequestTime)
    end
    local retryText = "no"
    if entryCreationKeyState.rosterInspectBatchRetryDeadline then
        retryText = string.format(
            "yes (%.2fs)",
            math.max(0, entryCreationKeyState.rosterInspectBatchRetryDeadline - GetTime())
        )
    end
    local loadRetryText = "no"
    if entryCreationKeyState.rosterLoadRetryDeadline then
        loadRetryText = string.format(
            "yes (%.2fs)",
            math.max(0, entryCreationKeyState.rosterLoadRetryDeadline - GetTime())
        )
    end
    print("  roster inspect batch:")
    print("    batch pending: "
          .. tostring(entryCreationKeyState.rosterInspectBatchDirtyPending))
    print("    pending inspect: " .. tostring(rosterInspectPendingGUID ~= nil)
          .. " (age: " .. pendingInspectAge .. ")")
    print("    retry scheduled: " .. retryText)
    print("    combat deferred: "
          .. tostring(entryCreationKeyState.rosterInspectBatchCombatDeferred))
    print("    last block reason: "
          .. tostring(entryCreationKeyState.rosterInspectBatchLastBlockReason or "none"))
    print("    skipped count: " .. tostring(skippedInspectCount))
    print("    retry cooldown count: " .. tostring(inspectCooldownCount))
    print("    exhausted count: " .. tostring(exhaustedInspectCount))
    print("    quiet full-party suppression: cached="
          .. tostring(entryCreationKeyState.lastQuietFullPartySignature ~= nil)
          .. ", payload="
          .. tostring(entryCreationKeyState.lastPayloadQuietFullPartySignature ~= nil))
    print("  roster load retry: " .. loadRetryText
          .. ", attempt: "
          .. tostring(entryCreationKeyState.rosterLoadRetryAttempt or 0)
          .. ", exhausted: "
          .. tostring(entryCreationKeyState.rosterLoadRetryExhausted == true)
          .. ", incomplete payload: "
          .. tostring(entryCreationKeyState.lastPayloadRosterIncomplete))
end
entryCreationKeyState.ScheduleRosterInspectBatchRetry = function(delay)
    if not (C_Timer and C_Timer.After) then return false end
    local now = GetTime and GetTime() or 0
    delay = SafeNumber(delay, 0)
    if delay < 0 then delay = 0 end
    local due = now + delay
    local existingDeadline = entryCreationKeyState.rosterInspectBatchRetryDeadline
    if existingDeadline
       and entryCreationKeyState.rosterInspectBatchRetrySessionGen == sessionGen
       and existingDeadline <= due then
        return true
    end
    entryCreationKeyState.rosterInspectBatchRetryToken =
        (entryCreationKeyState.rosterInspectBatchRetryToken or 0) + 1
    local retryToken = entryCreationKeyState.rosterInspectBatchRetryToken
    local retrySessionGen = sessionGen
    entryCreationKeyState.rosterInspectBatchRetryDeadline = due
    entryCreationKeyState.rosterInspectBatchRetrySessionGen = retrySessionGen
    C_Timer.After(delay, function()
        if retryToken ~= entryCreationKeyState.rosterInspectBatchRetryToken then
            return
        end
        if retrySessionGen ~= sessionGen then return end
        entryCreationKeyState.rosterInspectBatchRetryDeadline = nil
        entryCreationKeyState.rosterInspectBatchRetrySessionGen = nil
        if not (KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled) then return end
        if not isSessionActive then return end
        if entryCreationKeyState.rosterInspectBatchDirtyPending
           and not entryCreationKeyState.FlushOrContinueRosterInspectBatch() then
            MarkDirty("inspect")
        end
    end)
    return true
end
entryCreationKeyState.ScheduleRosterLoadRetry = function()
    local now = GetTime and GetTime() or 0
    local existingDeadline = entryCreationKeyState.rosterLoadRetryDeadline
    if existingDeadline
       and entryCreationKeyState.rosterLoadRetrySessionGen == sessionGen then
        return true
    end
    if entryCreationKeyState.rosterLoadRetryExhausted then return true end

    local attempt = math.floor(SafeNumber(
        entryCreationKeyState.rosterLoadRetryAttempt,
        0
    )) + 1
    local delay = SafeNumber(
        entryCreationKeyState.ROSTER_LOAD_RETRY_DELAYS_S[attempt],
        0
    )
    if delay <= 0 or not (C_Timer and C_Timer.After) then
        entryCreationKeyState.rosterLoadRetryDeadline = nil
        entryCreationKeyState.rosterLoadRetrySessionGen = nil
        entryCreationKeyState.rosterLoadRetryReady = false
        entryCreationKeyState.rosterLoadRetryExhausted = true
        return true
    end

    local due = now + delay
    entryCreationKeyState.rosterLoadRetryAttempt = attempt
    entryCreationKeyState.rosterLoadRetryReady = false
    entryCreationKeyState.rosterLoadRetryToken =
        (entryCreationKeyState.rosterLoadRetryToken or 0) + 1
    local retryToken = entryCreationKeyState.rosterLoadRetryToken
    local retrySessionGen = sessionGen
    entryCreationKeyState.rosterLoadRetryDeadline = due
    entryCreationKeyState.rosterLoadRetrySessionGen = retrySessionGen
    C_Timer.After(delay, function()
        if retryToken ~= entryCreationKeyState.rosterLoadRetryToken then
            return
        end
        if retrySessionGen ~= sessionGen then return end
        entryCreationKeyState.rosterLoadRetryDeadline = nil
        entryCreationKeyState.rosterLoadRetrySessionGen = nil
        entryCreationKeyState.rosterLoadRetryReady = true
        if not (KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled) then return end
        if not isSessionActive then return end
        pendingShotDirty = true
        MarkDirty("rosterload")
    end)
    return true
end

entryCreationKeyState.FlushOrContinueRosterInspectBatch = function()
    if not entryCreationKeyState.rosterInspectBatchDirtyPending then return true end

    local now = GetTime and GetTime() or 0
    if rosterInspectPendingGUID then
        if not _FindRosterUnitByGUID(rosterInspectPendingGUID) then
            local missingGUID = rosterInspectPendingGUID
            entryCreationKeyState.ReleaseOwnedRosterInspect()
            entryCreationKeyState.rosterInspectBatchSkippedGUIDs =
                entryCreationKeyState.rosterInspectBatchSkippedGUIDs or {}
            entryCreationKeyState.rosterInspectBatchSkippedGUIDs[missingGUID] = true
        end
    end
    if rosterInspectPendingGUID then
        local timeoutLeft = ROSTER_INSPECT_TIMEOUT_S - (now - rosterInspectLastRequestTime)
        if timeoutLeft > 0 then
            return entryCreationKeyState.ScheduleRosterInspectBatchRetry(timeoutLeft)
        end
        local timedOutGUID = rosterInspectPendingGUID
        entryCreationKeyState.ReleaseOwnedRosterInspect()
        entryCreationKeyState.rosterInspectBatchSkippedGUIDs =
            entryCreationKeyState.rosterInspectBatchSkippedGUIDs or {}
        entryCreationKeyState.rosterInspectBatchSkippedGUIDs[timedOutGUID] = true
        entryCreationKeyState.MarkRosterInspectAttemptFailed(timedOutGUID, now)
    end

    local throttleLeft = ROSTER_INSPECT_THROTTLE_S - (now - rosterInspectLastRequestTime)

    local requested = false
    local requestReason = nil
    _ForEachRosterUnit(function(unit)
        if not _UnitExistsForRoster(unit) then return false end
        local guid = entryCreationKeyState.UnitGUIDForRoster(unit)
        if guid == ""
           or (entryCreationKeyState.rosterInspectBatchSkippedGUIDs
               and entryCreationKeyState.rosterInspectBatchSkippedGUIDs[guid])
           or entryCreationKeyState.RosterUnitHasResolvedInspectData(unit, guid)
           or entryCreationKeyState.RosterInspectRetryBlocked(guid, now) then
            return false
        end
        local didRequest, reason = _MaybeRequestRosterInspect(unit, guid)
        if didRequest then
            requested = true
            requestReason = reason
            return true
        end
        if reason == "combat" then
            requestReason = reason
            return true
        end
        if reason == "throttle" then
            requestReason = requestReason or reason
        elseif reason == "uninspectable"
            or reason == "notify"
            or reason == "api" then
            -- These failures never create INSPECT_READY or a timeout-owned
            -- pending GUID. Charge the same per-session budget here so a
            -- permanently unavailable unit cannot be retried every poll.
            entryCreationKeyState.rosterInspectBatchSkippedGUIDs =
                entryCreationKeyState.rosterInspectBatchSkippedGUIDs or {}
            entryCreationKeyState.rosterInspectBatchSkippedGUIDs[guid] = true
            entryCreationKeyState.MarkRosterInspectAttemptFailed(guid, now)
        end
        return false
    end)
    if requestReason == "throttle"
       and throttleLeft > 0
       and rosterInspectLastRequestTime > 0
       and entryCreationKeyState.ScheduleRosterInspectBatchRetry(throttleLeft) then
        return true
    end
    if requestReason == "combat" then
        entryCreationKeyState.rosterInspectBatchDirtyPending = true
        entryCreationKeyState.rosterInspectBatchCombatDeferred = true
        entryCreationKeyState.rosterInspectBatchLastBlockReason = "combat"
        return true
    end
    if requested then
        entryCreationKeyState.rosterInspectBatchCombatDeferred = false
        entryCreationKeyState.rosterInspectBatchLastBlockReason = nil
        entryCreationKeyState.ScheduleRosterInspectBatchRetry(ROSTER_INSPECT_TIMEOUT_S)
        return true
    end

    entryCreationKeyState.ClearRosterInspectBatchState()
    return false
end

entryCreationKeyState.EnsureRosterInspectBatchBeforeSnapshot = function()
    local groupCount = math.floor(SafeNumber(GetNumGroupMembers and GetNumGroupMembers(), 0))
    if groupCount <= 0 or groupCount > 5 then return false end
    if IsInRaid and IsInRaid() then return false end
    if not entryCreationKeyState.rosterInspectBatchDirtyPending then
        local seeded = false
        local now = GetTime and GetTime() or 0
        _ForEachRosterUnit(function(unit)
            if not _UnitExistsForRoster(unit) then return false end
            local guid = entryCreationKeyState.UnitGUIDForRoster(unit)
            if guid ~= ""
               and not entryCreationKeyState.RosterUnitHasResolvedInspectData(unit, guid)
               and not entryCreationKeyState.RosterInspectRetryBlocked(guid, now) then
                entryCreationKeyState.rosterInspectBatchDirtyPending = true
                entryCreationKeyState.rosterInspectBatchSkippedGUIDs = nil
                entryCreationKeyState.rosterInspectBatchLastBlockReason = "preflight"
                seeded = true
                return true
            end
            return false
        end)
        if not seeded then return false end
    end
    return entryCreationKeyState.FlushOrContinueRosterInspectBatch()
end

local function _OnRosterInspectReady(guid)
    local ownedGUID = entryCreationKeyState.CleanRosterGUIDValue(
        rosterInspectPendingGUID
    )
    if ownedGUID == "" then return false end
    guid = entryCreationKeyState.CleanRosterGUIDValue(guid)
    if guid == "" then return false end
    if guid ~= ownedGUID then return false end

    if not (KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled) then
        entryCreationKeyState.ClearRosterInspectBatchState()
        return false
    end

    local unit = _FindRosterUnitByGUID(guid)
    if not unit then
        entryCreationKeyState.ReleaseOwnedRosterInspect()
        if entryCreationKeyState.rosterInspectBatchDirtyPending then
            if entryCreationKeyState.FlushOrContinueRosterInspectBatch() then
                return false
            end
            MarkDirty("inspect")
        end
        return false
    end
    if not GetInspectSpecialization then return false end
    local wasPendingInspect = rosterInspectPendingGUID == guid
    local ok, specID = pcall(GetInspectSpecialization, unit)
    specID = ok and _ClampUInt16(SafeNumber(specID, 0)) or 0
    local ilvl = entryCreationKeyState.ReadRosterInspectItemLevel(unit)
    local resolved = false
    if specID > 0 then
        rosterInspectSpecByGUID[guid] = specID
        resolved = true
    end
    if ilvl > 0 then
        entryCreationKeyState.rosterInspectIlvlByGUID[guid] = ilvl
        resolved = true
    end
    if resolved
       and wasPendingInspect
       and not entryCreationKeyState.RosterUnitHasResolvedInspectData(unit, guid) then
        entryCreationKeyState.MarkRosterInspectAttemptFailed(guid, GetTime())
    end
    if resolved then
        entryCreationKeyState.ReleaseOwnedRosterInspect()
        -- WHY: a freshly assembled group can resolve one inspected spec per
        -- callback. Batch follow-up inspect requests so the user sees one final
        -- QR refresh instead of a visible flash for every party member.
        entryCreationKeyState.rosterInspectBatchDirtyPending = true
        entryCreationKeyState.rosterInspectBatchSkippedGUIDs = nil
        if entryCreationKeyState.FlushOrContinueRosterInspectBatch() then
            return true
        end
        MarkDirty("inspect")
    end
    return resolved
end

local function _UnitSpecIDForRoster(unit, guid, isSelf)
    if guid ~= "" then
        local cachedSpecID = _ClampUInt16(SafeNumber(rosterInspectSpecByGUID[guid], 0))
        if cachedSpecID > 0 then return cachedSpecID end
    end

    if isSelf then
        if GetSpecialization and GetSpecializationInfo then
            local okSpec, specIndex = pcall(GetSpecialization)
            specIndex = okSpec and math.floor(SafeNumber(specIndex, 0)) or 0
            if specIndex > 0 then
                local okInfo, specID = pcall(GetSpecializationInfo, specIndex)
                if okInfo then return _ClampUInt16(SafeNumber(specID, 0)) end
            end
        end
    end
    if GetInspectSpecialization then
        local ok, specID = pcall(GetInspectSpecialization, unit)
        specID = ok and _ClampUInt16(SafeNumber(specID, 0)) or 0
        if specID > 0 then
            if guid ~= "" then rosterInspectSpecByGUID[guid] = specID end
            return specID
        end
    end
    _MaybeRequestRosterInspect(unit, guid, isSelf)
    return 0
end

local function _UnitItemLevelForRoster(unit, guid, isSelf)
    if not isSelf then
        if guid ~= "" then
            local cachedIlvl = entryCreationKeyState.CachedRosterInspectItemLevel(guid)
            if cachedIlvl > 0 then return cachedIlvl end

            local ilvl = entryCreationKeyState.ReadRosterInspectItemLevel(unit)
            if ilvl > 0 then
                entryCreationKeyState.rosterInspectIlvlByGUID[guid] = ilvl
                return ilvl
            end
            _MaybeRequestRosterInspect(unit, guid, isSelf)
        end
        return 0
    end
    if not GetAverageItemLevel then return 0 end
    local ok, overall, equipped = pcall(GetAverageItemLevel)
    if not ok then return 0 end
    local ilvl = SafeNumber(equipped, 0)
    if ilvl <= 0 then ilvl = SafeNumber(overall, 0) end
    return _ClampUInt16(SafeRoundedNumber(ilvl, 0))
end

local function _UnitRoleTokenForRoster(unit, specID)
    local roleToken = ""
    if UnitGroupRolesAssigned then
        local ok, assigned = pcall(UnitGroupRolesAssigned, unit)
        if ok then roleToken = SafeEnumKey(assigned, "") end
    end
    if (roleToken == "" or roleToken == "NONE")
       and specID > 0 and GetSpecializationRoleByID then
        local ok, specRole = pcall(GetSpecializationRoleByID, specID)
        if ok then roleToken = SafeEnumKey(specRole, "") end
    end
    if roleToken == "TANK" or roleToken == "HEALER" or roleToken == "DAMAGER" then
        return roleToken
    end
    return "DAMAGER"
end

local function _BuildRosterRow(unit, unitIndex, subgroup, isRaid)
    if not _UnitExistsForRoster(unit) then return nil end
    local name = _UnitFullNameForTransport(unit)
    if name == "" then return nil end
    local guid = entryCreationKeyState.UnitGUIDForRoster(unit)
    local isSelf = _UnitIsSelfForRoster(unit)
    local specID = _UnitSpecIDForRoster(unit, guid, isSelf)
    local roleToken = _UnitRoleTokenForRoster(unit, specID)
    local flags = 0
    if isSelf then flags = flags + 1 end
    if isRaid then flags = flags + 2 end
    return {
        unitIndex = unitIndex,
        flags = flags,
        subgroup = subgroup,
        classID = _UnitClassIDForRoster(unit),
        specID = specID,
        ilvl = _UnitItemLevelForRoster(unit, guid, isSelf),
        role = ROLE_NAME_TO_BYTE[roleToken] or 2,
        name = name,
    }
end

entryCreationKeyState.GetLibKeystone = function()
    local libStub = _G and _G.LibStub
    if type(libStub) == "function" then
        local ok, lib = pcall(libStub, "LibKeystone", true)
        if ok
           and type(lib) == "table"
           and type(lib.Register) == "function"
           and type(lib.Request) == "function" then
            return lib
        end
    end
    return entryCreationKeyState.GetLibKeystoneShim()
end

entryCreationKeyState.IsLibKeystoneShimResponderOwner = function()
    local provider = entryCreationKeyState.leaderKeystoneLib
        or entryCreationKeyState.GetLibKeystone()
    return provider ~= nil and provider == entryCreationKeyState.libKeystoneShim
end

entryCreationKeyState.RegisterLibKeystonePrefix = function()
    if entryCreationKeyState.libKeystonePrefixRegistered then return true end
    if not (C_ChatInfo and type(C_ChatInfo.RegisterAddonMessagePrefix) == "function") then
        return false
    end
    local ok, result = pcall(function()
        return C_ChatInfo.RegisterAddonMessagePrefix("LibKS")
    end)
    if not ok then return false end
    if type(result) == "number" and result > 1 then return false end
    entryCreationKeyState.libKeystonePrefixRegistered = true
    return true
end

entryCreationKeyState.IsLibKeystoneSendRetryable = function(reason)
    return reason == "lockdown"
        or reason == "send-failed"
        or reason == "request-error"
        or reason == "request-failed"
end

entryCreationKeyState.IsLibKeystoneTransportEnabled = function()
    return KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled
end

entryCreationKeyState.SendLibKeystoneAddonMessage = function(payload, channel)
    if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then
        return false, "disabled"
    end
    if channel ~= "PARTY" then return false, "bad-channel" end
    if not (IsInGroup and IsInGroup()) then return false, "not-grouped" end
    if IsChatMessagingLockdown() then return false, "lockdown" end
    if not entryCreationKeyState.RegisterLibKeystonePrefix() then
        return false, "prefix-unavailable"
    end
    if not (C_ChatInfo and type(C_ChatInfo.SendAddonMessage) == "function") then
        return false, "missing-chat-api"
    end
    local ok, result = pcall(function()
        return C_ChatInfo.SendAddonMessage("LibKS", payload, channel)
    end)
    if not ok then return false, "send-failed" end
    if result ~= nil and result ~= 0 then return false, "send-failed" end
    return true
end

entryCreationKeyState.ReadOwnLibKeystoneInfo = function()
    local keyLevel, challengeMapID, playerRating = 0, 0, 0
    local keyLevelAvailable, challengeMapIDAvailable = false, false
    if C_MythicPlus then
        if type(C_MythicPlus.GetOwnedKeystoneLevel) == "function" then
            local ok, value = pcall(C_MythicPlus.GetOwnedKeystoneLevel)
            if ok and not IsSecretValue(value) and type(value) == "number" then
                keyLevel = math.floor(SafeNumber(value, 0))
                keyLevelAvailable = true
            end
        end
        if type(C_MythicPlus.GetOwnedKeystoneChallengeMapID) == "function" then
            local ok, value = pcall(C_MythicPlus.GetOwnedKeystoneChallengeMapID)
            if ok and not IsSecretValue(value) and type(value) == "number" then
                challengeMapID = math.floor(SafeNumber(value, 0))
                challengeMapIDAvailable = true
            end
        end
    end
    if C_PlayerInfo and type(C_PlayerInfo.GetPlayerMythicPlusRatingSummary) == "function" then
        local ok, summary = pcall(C_PlayerInfo.GetPlayerMythicPlusRatingSummary, "player")
        summary = ok and SafeTable(summary) or nil
        playerRating = math.floor(SafeNumber(summary and summary.currentSeasonScore, 0))
    end
    return keyLevel, challengeMapID, playerRating,
        keyLevelAvailable and challengeMapIDAvailable
end

entryCreationKeyState.NotifyLibKeystoneShimCallbacks = function(keyLevel, challengeMapID, playerRating, playerName, channel)
    for _, callback in pairs(entryCreationKeyState.libKeystoneShimCallbacks) do
        if type(callback) == "function" then
            pcall(callback, keyLevel, challengeMapID, playerRating, playerName, channel)
        end
    end
end

entryCreationKeyState.SendLibKeystoneShimInfo = function(channel)
    local keyLevel, challengeMapID, playerRating = entryCreationKeyState.ReadOwnLibKeystoneInfo()
    local payload = string.format("%d,%d,%d", keyLevel, challengeMapID, playerRating)
    local ok, reason = entryCreationKeyState.SendLibKeystoneAddonMessage(payload, channel)
    entryCreationKeyState.libKeystoneLastSendStatus =
        ok and "response sent" or ("response failed: " .. tostring(reason or "unknown"))
    return ok, reason
end

entryCreationKeyState.ScheduleLibKeystoneResponseRetry = function(channel, reason, attempt)
    if not entryCreationKeyState.IsLibKeystoneSendRetryable(reason) then
        return false
    end
    if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then
        return false
    end
    if not entryCreationKeyState.IsLibKeystoneShimResponderOwner() then
        return false
    end
    attempt = math.floor(SafeNumber(attempt, 1))
    if attempt >= entryCreationKeyState.LIB_KEYSTONE_RESPONSE_MAX_RETRIES then
        entryCreationKeyState.libKeystoneLastSendStatus =
            "response exhausted: " .. tostring(reason or "unknown")
        return false
    end
    if not (C_Timer and C_Timer.After) then return false end
    if not (IsInGroup and IsInGroup()) then return false end

    local now = GetTime and GetTime() or 0
    local delay = entryCreationKeyState.LIB_KEYSTONE_RESPONSE_RETRY_DELAY_S
    local due = now + delay
    local retryGroupGen = entryCreationKeyState.groupTransportGen
    local existingDeadline = entryCreationKeyState.libKeystoneResponseRetryDeadline
    if existingDeadline
       and entryCreationKeyState.libKeystoneResponseRetryGeneration == retryGroupGen
       and existingDeadline <= due then
        return true
    end

    entryCreationKeyState.libKeystoneResponseRetryToken =
        (entryCreationKeyState.libKeystoneResponseRetryToken or 0) + 1
    local retryToken = entryCreationKeyState.libKeystoneResponseRetryToken
    entryCreationKeyState.libKeystoneResponseRetryDeadline = due
    entryCreationKeyState.libKeystoneResponseRetryGeneration = retryGroupGen
    C_Timer.After(delay, function()
        if retryToken ~= entryCreationKeyState.libKeystoneResponseRetryToken then
            return
        end
        entryCreationKeyState.libKeystoneResponseRetryDeadline = nil
        entryCreationKeyState.libKeystoneResponseRetryGeneration = nil
        if retryGroupGen ~= entryCreationKeyState.groupTransportGen then return end
        if not (IsInGroup and IsInGroup()) then return end
        if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then return end
        if not entryCreationKeyState.IsLibKeystoneShimResponderOwner() then return end
        local ok, retryReason = entryCreationKeyState.SendLibKeystoneShimInfo(channel)
        if not ok then
            entryCreationKeyState.ScheduleLibKeystoneResponseRetry(
                channel,
                retryReason,
                attempt + 1
            )
        end
    end)
    return true
end

entryCreationKeyState.CancelLibKeystoneResponseRetry = function()
    entryCreationKeyState.libKeystoneResponseRetryDeadline = nil
    entryCreationKeyState.libKeystoneResponseRetryGeneration = nil
    entryCreationKeyState.libKeystoneResponseRetryToken =
        (entryCreationKeyState.libKeystoneResponseRetryToken or 0) + 1
end

entryCreationKeyState.CancelLeaderKeystoneRefresh = function()
    entryCreationKeyState.leaderKeystoneRefreshDeadline = nil
    entryCreationKeyState.leaderKeystoneRefreshGeneration = nil
    entryCreationKeyState.leaderKeystoneRefreshToken =
        (entryCreationKeyState.leaderKeystoneRefreshToken or 0) + 1
end

entryCreationKeyState.ScheduleLeaderKeystoneRefresh = function()
    if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then return false end
    if not (C_Timer and C_Timer.After) then return false end
    if not (IsInGroup and IsInGroup()) then return false end

    local refreshGroupGen = entryCreationKeyState.groupTransportGen
    if entryCreationKeyState.leaderKeystoneRefreshDeadline ~= nil
       and entryCreationKeyState.leaderKeystoneRefreshGeneration == refreshGroupGen then
        return true
    end

    local now = GetTime and GetTime() or 0
    entryCreationKeyState.leaderKeystoneRefreshToken =
        (entryCreationKeyState.leaderKeystoneRefreshToken or 0) + 1
    local refreshToken = entryCreationKeyState.leaderKeystoneRefreshToken
    entryCreationKeyState.leaderKeystoneRefreshDeadline = now
    entryCreationKeyState.leaderKeystoneRefreshGeneration = refreshGroupGen
    C_Timer.After(0, function()
        if refreshToken ~= entryCreationKeyState.leaderKeystoneRefreshToken then return end
        entryCreationKeyState.leaderKeystoneRefreshDeadline = nil
        entryCreationKeyState.leaderKeystoneRefreshGeneration = nil
        if refreshGroupGen ~= entryCreationKeyState.groupTransportGen then return end
        if not (IsInGroup and IsInGroup()) then return end
        if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then return end
        entryCreationKeyState.RequestLeaderKeystone(false)
    end)
    return true
end

entryCreationKeyState.AdvanceGroupTransportGeneration = function()
    entryCreationKeyState.groupTransportGen =
        (entryCreationKeyState.groupTransportGen or 0) + 1
    entryCreationKeyState.CancelLibKeystoneResponseRetry()
    entryCreationKeyState.CancelLeaderKeystoneRefresh()
end

entryCreationKeyState.GetLibKeystoneShim = function()
    if entryCreationKeyState.libKeystoneShim then return entryCreationKeyState.libKeystoneShim end
    if not entryCreationKeyState.RegisterLibKeystonePrefix() then return nil end
    entryCreationKeyState.libKeystoneShim = {
        Register = function(owner, callback)
            if type(owner) ~= "table" or type(callback) ~= "function" then return end
            entryCreationKeyState.libKeystoneShimCallbacks[owner] = callback
        end,
    }
    return entryCreationKeyState.libKeystoneShim
end

entryCreationKeyState.LibKeystoneShimHandleAddonMessage = function(prefix, msg, channel, sender)
    if prefix ~= "LibKS" or channel ~= "PARTY" then return end
    if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then return end
    if IsSecretValue(msg) or type(msg) ~= "string" then return end
    if msg == "R" then
        if not entryCreationKeyState.IsLibKeystoneShimResponderOwner() then return end
        local ok, reason = entryCreationKeyState.SendLibKeystoneShimInfo(channel)
        if not ok then
            entryCreationKeyState.ScheduleLibKeystoneResponseRetry(channel, reason)
        end
        return
    end
    local keyLevelStr, challengeMapIDStr, playerRatingStr =
        msg:match("^(%d+),(%d+),(%d+)$")
    if not keyLevelStr then return end
    local playerName = SafeStr(Ambiguate and Ambiguate(sender, "none") or sender, "")
    entryCreationKeyState.NotifyLibKeystoneShimCallbacks(
        math.floor(SafeNumber(keyLevelStr, 0)),
        math.floor(SafeNumber(challengeMapIDStr, 0)),
        math.floor(SafeNumber(playerRatingStr, 0)),
        playerName,
        channel
    )
end

entryCreationKeyState.CanonicalPlayerName = function(name)
    name = SafeStr(name, "")
    if name == "" then return "", "" end
    local full = name
    local short = name:gsub("%-.+$", "")
    return full, short
end

entryCreationKeyState.PlayerNamesMatch = function(leftName, rightName)
    local leftFull, leftShort = entryCreationKeyState.CanonicalPlayerName(leftName)
    local rightFull, rightShort = entryCreationKeyState.CanonicalPlayerName(rightName)
    if leftFull == "" or rightFull == "" then return false end
    if leftFull == rightFull then return true end
    if not leftFull:find("-", 1, true) or not rightFull:find("-", 1, true) then
        return leftShort ~= "" and leftShort == rightShort
    end
    return false
end

entryCreationKeyState.CurrentPartyLeaderName = function()
    local grouped = entryCreationKeyState.CleanUnitAPIBoolean(IsInGroup)
    if grouped == false then return "" end
    if grouped ~= true then
        if entryCreationKeyState.CleanUnitAPIBoolean(InCombatLockdown) == true then
            entryCreationKeyState.leaderKeystoneContextCombatDeferred = true
        end
        return nil
    end
    local sawUnknown = false

    local playerLeader = entryCreationKeyState.CleanUnitIsGroupLeader("player")
    if playerLeader == true then
        local playerName = _UnitFullNameForTransport("player")
        if playerName ~= "" then return playerName end
        sawUnknown = true
    elseif playerLeader == nil then
        sawUnknown = true
    end
    for i = 1, 4 do
        local unit = "party" .. i
        local exists = entryCreationKeyState.CleanUnitAPIBoolean(UnitExists, unit)
        if exists == true then
            local isLeader = entryCreationKeyState.CleanUnitIsGroupLeader(unit)
            if isLeader == true then
                local partyName = _UnitFullNameForTransport(unit)
                if partyName ~= "" then return partyName end
                sawUnknown = true
            elseif isLeader == nil then
                sawUnknown = true
            end
        elseif exists == nil then
            sawUnknown = true
        end
    end
    if sawUnknown then
        if entryCreationKeyState.CleanUnitAPIBoolean(InCombatLockdown) == true then
            entryCreationKeyState.leaderKeystoneContextCombatDeferred = true
        end
        return nil
    end
    return ""
end

entryCreationKeyState.CancelLeaderKeystoneRequestRetry = function()
    entryCreationKeyState.leaderKeystoneRequestRetryDeadline = nil
    entryCreationKeyState.leaderKeystoneRequestRetryGeneration = nil
    entryCreationKeyState.leaderKeystoneRequestRetryToken =
        (entryCreationKeyState.leaderKeystoneRequestRetryToken or 0) + 1
end

entryCreationKeyState.ClearLeaderKeystone = function()
    entryCreationKeyState.leaderKeystone = nil
    entryCreationKeyState.leaderKeystoneContextCombatDeferred = false
    entryCreationKeyState.CancelLeaderKeystoneRefresh()
    entryCreationKeyState.CancelLeaderKeystoneRequestRetry()
end

entryCreationKeyState.OnLeaderKeystoneData = function(keyLevel, challengeMapID, _rating, playerName, channel)
    if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then return end
    if channel ~= "PARTY" then return end
    if not (IsInGroup and IsInGroup()) then return end
    local leaderName = entryCreationKeyState.CurrentPartyLeaderName()
    if not leaderName or leaderName == "" then return end
    if not entryCreationKeyState.PlayerNamesMatch(playerName, leaderName) then return end
    local rawKeyLevel = SafeNumber(keyLevel, -1)
    local rawChallengeMapID = SafeNumber(challengeMapID, -1)
    if rawKeyLevel == 0 and rawChallengeMapID == 0 then
        entryCreationKeyState.ClearLeaderKeystone()
        MarkDirty("leaderkey")
        return
    end
    keyLevel = _NormalizeKeystoneLevel(rawKeyLevel)
    if rawKeyLevel ~= math.floor(rawKeyLevel)
       or keyLevel <= 0
       or rawChallengeMapID ~= math.floor(rawChallengeMapID)
       or rawChallengeMapID <= 0
       or rawChallengeMapID > 65535 then
        return
    end
    challengeMapID = rawChallengeMapID
    entryCreationKeyState.CancelLeaderKeystoneRefresh()
    entryCreationKeyState.CancelLeaderKeystoneRequestRetry()
    entryCreationKeyState.leaderKeystone = {
        level = keyLevel,
        challengeMapID = challengeMapID,
        playerName = leaderName,
        at = GetTime and GetTime() or 0,
    }
    entryCreationKeyState.leaderKeystoneContextCombatDeferred = false
    MarkDirty("leaderkey")
end

entryCreationKeyState.RegisterLeaderKeystoneCallback = function()
    local lib = entryCreationKeyState.GetLibKeystone()
    if not lib then return nil end
    -- WHY: an optional external provider can load after the built-in shim was
    -- selected. Re-register only when the currently resolved provider changes.
    if entryCreationKeyState.leaderKeystoneCallbackRegistered
       and entryCreationKeyState.leaderKeystoneLib == lib then
        return lib
    end
    local ok = pcall(function()
        lib.Register(
            entryCreationKeyState.leaderKeystoneCallbackOwner,
            entryCreationKeyState.OnLeaderKeystoneData
        )
    end)
    if not ok then return nil end
    if lib ~= entryCreationKeyState.libKeystoneShim then
        entryCreationKeyState.libKeystoneShimCallbacks[
            entryCreationKeyState.leaderKeystoneCallbackOwner
        ] = nil
        entryCreationKeyState.CancelLibKeystoneResponseRetry()
    end
    entryCreationKeyState.leaderKeystoneCallbackRegistered = true
    entryCreationKeyState.leaderKeystoneLib = lib
    return lib
end

entryCreationKeyState.ScheduleLeaderKeystoneRequestRetry = function(attempt, reason)
    if not entryCreationKeyState.IsLibKeystoneSendRetryable(reason) then
        return false
    end
    if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then
        return false
    end
    attempt = math.floor(SafeNumber(attempt, 1))
    if attempt >= entryCreationKeyState.LEADER_KEY_REQUEST_MAX_RETRIES then
        entryCreationKeyState.leaderKeystoneLastRequestStatus =
            "request exhausted: " .. tostring(reason or "unknown")
        entryCreationKeyState.CancelLeaderKeystoneRequestRetry()
        return false
    end
    if not (C_Timer and C_Timer.After) then return false end
    if not (IsInGroup and IsInGroup()) then return false end

    local now = GetTime and GetTime() or 0
    local delay = entryCreationKeyState.LEADER_KEY_REQUEST_RETRY_DELAY_S
    local due = now + delay
    local retryGroupGen = entryCreationKeyState.groupTransportGen
    local existingDeadline = entryCreationKeyState.leaderKeystoneRequestRetryDeadline
    if existingDeadline
       and entryCreationKeyState.leaderKeystoneRequestRetryGeneration == retryGroupGen
       and existingDeadline <= due then
        return true
    end

    entryCreationKeyState.leaderKeystoneRequestRetryToken =
        (entryCreationKeyState.leaderKeystoneRequestRetryToken or 0) + 1
    local retryToken = entryCreationKeyState.leaderKeystoneRequestRetryToken
    entryCreationKeyState.leaderKeystoneRequestRetryDeadline = due
    entryCreationKeyState.leaderKeystoneRequestRetryGeneration = retryGroupGen
    entryCreationKeyState.leaderKeystoneLastRequestStatus =
        "request retry scheduled: " .. tostring(reason or "unknown")
    C_Timer.After(delay, function()
        if retryToken ~= entryCreationKeyState.leaderKeystoneRequestRetryToken then
            return
        end
        entryCreationKeyState.leaderKeystoneRequestRetryDeadline = nil
        entryCreationKeyState.leaderKeystoneRequestRetryGeneration = nil
        if retryGroupGen ~= entryCreationKeyState.groupTransportGen then return end
        if not (IsInGroup and IsInGroup()) then return end
        if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then return end
        entryCreationKeyState.RequestLeaderKeystone(true, attempt + 1)
    end)
    return true
end

entryCreationKeyState.RequestLeaderKeystone = function(force, attempt)
    if not entryCreationKeyState.IsLibKeystoneTransportEnabled() then
        return
    end
    if not entryCreationKeyState.RegisterLeaderKeystoneCallback()
       or not (IsInGroup and IsInGroup()) then
        return
    end
    local now = GetTime and GetTime() or 0
    attempt = math.floor(SafeNumber(attempt, 1))
    if attempt < 1 then attempt = 1 end
    if not force
       and (now - SafeNumber(entryCreationKeyState.leaderKeystoneLastRequestAt, 0))
           < entryCreationKeyState.LEADER_KEY_REQUEST_THROTTLE_S then
        return
    end
    -- LibKeystone.Request reports the caller's own key before broadcasting.
    -- Preserve that local leader context while retaining checked wire delivery.
    if entryCreationKeyState.CleanUnitIsGroupLeader("player") == true then
        local keyLevel, challengeMapID, playerRating, ownInfoAvailable =
            entryCreationKeyState.ReadOwnLibKeystoneInfo()
        if ownInfoAvailable then
            entryCreationKeyState.OnLeaderKeystoneData(
                keyLevel,
                challengeMapID,
                playerRating,
                _UnitFullNameForTransport("player"),
                "PARTY"
            )
        end
    end
    -- WHY: external LibKeystone.Request() does not expose addon-message
    -- delivery status, so route the wire request through our checked sender.
    local ok, reason = entryCreationKeyState.SendLibKeystoneAddonMessage("R", "PARTY")
    if ok then
        entryCreationKeyState.leaderKeystoneLastRequestAt = now
        entryCreationKeyState.leaderKeystoneLastRequestStatus = "request sent"
        entryCreationKeyState.CancelLeaderKeystoneRequestRetry()
        return true
    end
    reason = reason or "request-failed"
    entryCreationKeyState.leaderKeystoneLastRequestStatus =
        "request failed: " .. tostring(reason or "unknown")
    entryCreationKeyState.ScheduleLeaderKeystoneRequestRetry(attempt, reason)
    return false
end

entryCreationKeyState.ResolveLeaderKeystoneContext = function()
    local leaderKeystone = entryCreationKeyState.leaderKeystone
    if type(leaderKeystone) ~= "table" then return nil end
    local leaderName = entryCreationKeyState.CurrentPartyLeaderName()
    if leaderName ~= nil
       and (leaderName == ""
            or not entryCreationKeyState.PlayerNamesMatch(leaderKeystone.playerName, leaderName)) then
        entryCreationKeyState.ClearLeaderKeystone()
        return nil
    end
    local now = GetTime and GetTime() or 0
    local expired = now > 0
        and (now - SafeNumber(leaderKeystone.at, 0)) > entryCreationKeyState.LEADER_KEY_TTL_S
    if leaderName == nil then
        if expired then return nil end
        return leaderKeystone
    end
    entryCreationKeyState.leaderKeystoneContextCombatDeferred = false
    if expired then
        entryCreationKeyState.ClearLeaderKeystone()
        entryCreationKeyState.ScheduleLeaderKeystoneRefresh()
        return nil
    end
    return leaderKeystone
end

local function _RaidSubgroupForRoster(index)
    if not GetRaidRosterInfo then return 1 end
    local ok, _name, _rank, subgroup = pcall(GetRaidRosterInfo, index)
    if not ok then return 1 end
    return _ClampUInt8(SafeNumber(subgroup, 1))
end

local function BuildRosterPayloadRows(listingActivityIDForRio, listingKeyLevelForRio, includeSoloPlayer)
    local rosterOut = {}
    local emittedCount = 0
    local rows = {}
    local rosterQuietHasUnknownSpec = false
    local groupCount = math.floor(SafeNumber(GetNumGroupMembers and GetNumGroupMembers(), 0))
    local inRaid = IsInRaid and IsInRaid() or false
    local expectedRosterCount = 0
    if groupCount <= 0 then
        if includeSoloPlayer then
            local playerRow = _BuildRosterRow("player", 1, 1, false)
            if playerRow then table.insert(rows, playerRow) end
            expectedRosterCount = 1
            groupCount = 1
        else
            return "", emittedCount, "", false, inRaid, false
        end
    end

    if inRaid then
        if groupCount > 40 then groupCount = 40 end
        expectedRosterCount = groupCount
        for i = 1, groupCount do
            local row = _BuildRosterRow(
                "raid" .. i,
                i,
                _RaidSubgroupForRoster(i),
                true
            )
            if row then table.insert(rows, row) end
        end
    else
        expectedRosterCount = groupCount
        if expectedRosterCount > 5 then expectedRosterCount = 5 end
        if #rows == 0 then
            local playerRow = _BuildRosterRow("player", 1, 1, false)
            if playerRow then table.insert(rows, playerRow) end
        end
        for i = 1, 4 do
            local unit = "party" .. i
            local row = _BuildRosterRow(unit, i + 1, 1, false)
            if row then table.insert(rows, row) end
        end
    end

    table.sort(rows, function(a, b)
        if a.subgroup ~= b.subgroup then return a.subgroup < b.subgroup end
        return a.unitIndex < b.unitIndex
    end)

    for _, row in ipairs(rows) do
        local rioSummary = _GetRaiderIOMPlusSummaryForCleanName(
            _RaiderIOProfileLookupNameFromCleanName(row.name),
            listingActivityIDForRio,
            listingKeyLevelForRio
        )
        local currentScoreBytes = _Uint16BE(rioSummary.currentScore)
        table.insert(rosterOut, string.char(_ClampUInt8(row.unitIndex)))
        table.insert(rosterOut, string.char(_ClampUInt8(row.flags)))
        table.insert(rosterOut, string.char(_ClampUInt8(row.subgroup)))
        table.insert(rosterOut, string.char(_ClampUInt8(row.classID)))
        table.insert(rosterOut, _Uint16BE(row.specID))
        table.insert(rosterOut, _Uint16BE(row.ilvl))
        table.insert(rosterOut, currentScoreBytes)
        entryCreationKeyState.AppendRaiderIOMPlusSummary(rosterOut, rioSummary)
        table.insert(rosterOut, string.char(_ClampUInt8(row.role)))
        _PackCleanLenStr(rosterOut, row.name)
        emittedCount = emittedCount + 1
        if row.specID <= 0 then rosterQuietHasUnknownSpec = true end
    end

    local rosterIncomplete = emittedCount < expectedRosterCount
        or (not inRaid and rosterQuietHasUnknownSpec)
    -- SYNC: the quiet signature intentionally covers the exact companion-visible
    -- roster block. Reuse the serialized bytes so the 0.5s transport poll does
    -- not rebuild or copy every field a second time.
    local rosterPayload = table.concat(rosterOut)
    return rosterPayload, emittedCount, rosterPayload,
           rosterQuietHasUnknownSpec, inRaid, rosterIncomplete
end

-- CRC32 IEEE-802.3, table-based. Built once at file load (~5KB memory).
local CRC32_TABLE = {}
do
    for i = 0, 255 do
        local c = i
        for _ = 1, 8 do
            if c % 2 == 1 then
                c = bit.bxor(bit.rshift(c, 1), 0xEDB88320)
            else
                c = bit.rshift(c, 1)
            end
        end
        CRC32_TABLE[i] = c
    end
end
local function _CRC32AndSnapshotHash(chunks)
    local crc = 0xFFFFFFFF
    local snapshotHash = 5381
    for chunkIndex = 1, #chunks do
        local chunk = chunks[chunkIndex]
        for i = 1, #chunk do
            local byte = string.byte(chunk, i)
            crc = bit.bxor(bit.rshift(crc, 8),
                            CRC32_TABLE[bit.band(bit.bxor(crc, byte), 0xFF)])
            snapshotHash = ((snapshotHash * 33) + byte) % 4294967296
        end
    end
    return bit.bxor(crc, 0xFFFFFFFF) % 4294967296, snapshotHash
end

-- Builds binary payload from current LFG state. entry may be nil (no listing).
-- applicantIDs is array from C_LFGList.GetApplicants(). Returns payload bytes
-- and their exact djb2 snapshot hash; one-result Lua callers receive the bytes.
local function BuildPayload(entry, applicantIDs, terminalClear, lfgUnavailable, rosterUnavailable)
    local out = {}
    entryCreationKeyState.lastPayloadBuildError = nil
    entryCreationKeyState.lastPayloadTotalBytes = 0
    entryCreationKeyState.lastPayloadQuietFullPartySignature = nil
    entryCreationKeyState.lastPayloadApplicantCount = 0
    entryCreationKeyState.lastPayloadRosterCount = 0
    entryCreationKeyState.lastPayloadRosterIncomplete = false
    if terminalClear then
        lfgUnavailable = false
    end
    local applicantsUnavailable = not terminalClear and applicantIDs == nil
    rosterUnavailable = (not terminalClear) and rosterUnavailable == true
    local headerFlags = 0
    if terminalClear then
        headerFlags = headerFlags + 0x01
    end
    if lfgUnavailable then
        headerFlags = headerFlags + 0x02
    end

    -- Header (length patched after we know body size)
    table.insert(out, "APS1")
    local wireVersionChunkIndex = #out + 1
    table.insert(out, "\0")                 -- v12 normally; v13 only for applicant partials
    local lengthChunkIndex = #out + 1
    table.insert(out, "\0\0")                -- length placeholder (uint16 BE)
    local headerFlagsChunkIndex = #out + 1
    table.insert(out, "\0")                  -- flags patched after completeness checks
    -- Formerly reserved. New Companions use this non-zero marker to separate
    -- consecutive LFG listings; old Companions simply ignore the byte.
    table.insert(out, string.char(_ClampUInt8(listingGeneration)))

    -- Listing block
    local cleanEntry = SafeTable(entry)
    local leaderKeystone = entryCreationKeyState.ResolveLeaderKeystoneContext()
    if terminalClear then
        cleanEntry = nil
        applicantIDs = nil
        leaderKeystone = nil
    end
    local listingActivityIDForRio = 0
    local listingKeyLevelForRio = 0
    local listingQuietSignature = nil
    if cleanEntry then
        -- Midnight 12.0 returns activityIDs (table) on the primary listing —
        -- legacy entry.activityID is nil. Fall back to legacy field for
        -- forward-compat with future API renames.
        local activityIDs = SafeTable(cleanEntry.activityIDs)
        local activityID = SafeNumber(activityIDs and activityIDs[1], 0)
        if activityID <= 0 then
            activityID = SafeNumber(cleanEntry.activityID, 0)
        end
        activityID = math.floor(activityID)
        if activityID < 0 then activityID = 0 end

        local questID = math.floor(SafeNumber(cleanEntry.questID, 0))
        if questID < 0 then questID = 0 end

        local activityInfo = _GetActivityInfoForListing(activityID, questID)

        local dungeonName = "?"
        local categoryID = 0
        local difficultyID = 0
        if activityInfo then
            dungeonName = _ActivityInfoListingName(activityInfo)
            categoryID = math.floor(SafeNumber(activityInfo.categoryID, 0))
            difficultyID = math.floor(SafeNumber(activityInfo.difficultyID, 0))
        end
        local isMythicPlus = (categoryID == 2)

        -- Strip player-link |Kxxx|k from listing name after SafeStr has
        -- handled secret-tagged strings and regular WoW escape sequences.
        local listingName = SafeStr(cleanEntry.name, "?")
        local listingComment = SafeStr(cleanEntry.comment, "?")

        local keyLevel = 0
        if isMythicPlus then
            keyLevel = _GetListingKeystoneLevel(
                activityID,
                questID,
                listingName,
                listingComment,
                activityInfo
            )
            local ownedActivityID, _ownedGroupID, ownedLevel, ownedInfo =
                _GetOwnedKeystoneListingInfo()
            local shouldUseOwnedKeystone = ownedLevel > 0
                and ownedActivityID > 0
                and ownedInfo
                and entryCreationKeyState.CanUseOwnedKeystoneForListingFallback()
                and (ownedActivityID == activityID
                    or dungeonName == "Mythic+"
                    or dungeonName == "?")
            if keyLevel == 0 and shouldUseOwnedKeystone then
                keyLevel = ownedLevel
            end
            if shouldUseOwnedKeystone then
                activityID = ownedActivityID
                ---@cast ownedInfo table
                activityInfo = ownedInfo
                dungeonName = _ActivityInfoListingName(activityInfo)
                categoryID = math.floor(SafeNumber(activityInfo.categoryID, categoryID))
                difficultyID = math.floor(SafeNumber(activityInfo.difficultyID, difficultyID))
            end
            if leaderKeystone and leaderKeystone.level > 0 then
                keyLevel = leaderKeystone.level
            end
        end
        listingActivityIDForRio = activityID
        listingKeyLevelForRio = keyLevel
        local listingQuietOut = {}
        table.insert(listingQuietOut, _Uint32BE(activityID))
        table.insert(listingQuietOut, _Uint32BE(questID))
        table.insert(listingQuietOut, _Uint16BE(categoryID))
        table.insert(listingQuietOut, _Uint16BE(difficultyID))
        table.insert(listingQuietOut, string.char(math.min(keyLevel, 255)))
        _PackCleanLenStr(listingQuietOut, dungeonName)
        _PackCleanLenStr(listingQuietOut, listingName)
        _PackCleanLenStr(listingQuietOut, listingComment)
        listingQuietSignature = table.concat(listingQuietOut)

        table.insert(out, string.char(1))
        table.insert(out, _Uint32BE(activityID))
        table.insert(out, _Uint16BE(categoryID))
        table.insert(out, _Uint16BE(difficultyID))
        table.insert(out, string.char(math.min(keyLevel, 255)))
        _PackCleanLenStr(out, dungeonName)
        _PackCleanLenStr(out, listingName)
        _PackCleanLenStr(out, listingComment)
    else
        table.insert(out, string.char(0))
    end

    -- Version block — emitted in EVERY snapshot. Companion mid-session launch
    -- (user opens companion AFTER hosting LFG) misses session start; without
    -- VERSION in every shot, companion never learns realm/region and all
    -- same-realm applicants get empty realm → derive_server_slug("") → WCL
    -- "Server not found" silently for the rest of the session. Cost is
    -- ~30-60 bytes per shot (addon+game version strings + region byte + 12-char
    -- realm-qualified name) — negligible vs. QR Version 25-30 capacity.
    table.insert(out, string.char(1))
    _PackCleanLenStr(out, SafeStr(ADDON_VERSION, "?"))
    local gameVer = SafeStr((GetBuildInfo and select(1, GetBuildInfo())) or "?", "?")
    _PackCleanLenStr(out, gameVer)
    local regionID = math.floor(SafeNumber(GetCurrentRegion and GetCurrentRegion(), 0))
    if regionID < 0 then regionID = 0 elseif regionID > 255 then regionID = 0 end
    table.insert(out, string.char(regionID))
    local pname, prealm = UnitFullName("player")
    local playerName = SafeStr(pname, "?")
    if playerName == "" then playerName = "?" end
    local playerRealm = SafeStr(prealm, "")
    local fullName = playerName .. ((playerRealm ~= "") and ("-" .. playerRealm) or "")
    _PackCleanLenStr(out, fullName)

    local leaderQuietOut = {}
    if leaderKeystone and leaderKeystone.level > 0 then
        table.insert(leaderQuietOut, string.char(_ClampUInt8(leaderKeystone.level)))
        table.insert(leaderQuietOut, _Uint16BE(leaderKeystone.challengeMapID))
        _PackCleanLenStr(leaderQuietOut, leaderKeystone.playerName)
        if listingKeyLevelForRio <= 0 then
            listingKeyLevelForRio = leaderKeystone.level
        end
        table.insert(out, string.char(1))
        table.insert(out, string.char(_ClampUInt8(leaderKeystone.level)))
        table.insert(out, _Uint16BE(leaderKeystone.challengeMapID))
        _PackCleanLenStr(out, leaderKeystone.playerName)
    else
        table.insert(out, string.char(0))
    end
    local leaderQuietSignature = table.concat(leaderQuietOut)

    -- Applicants — filter out DEAD_STATUSES + sort by ID for hash stability
    local validAppIDs, validAppAPITokens = {}, {}
    local validAppMemberCounts, validAppOrder = {}, {}
    local applicantsIncomplete = applicantsUnavailable
        or entryCreationKeyState.applicantListReadIncomplete == true
    local expectedApplicantMemberCount = 0
    local cleanApplicantIDs = SafeTable(applicantIDs) or {}
    for _, rawID in ipairs(cleanApplicantIDs) do
        local id, info, apiID = entryCreationKeyState.GetApplicantInfoForTransport(rawID)
        if id and info then
            local status = _GetApplicantApplicationStatus(info)
            if not APP_DEAD_STATUSES[status] then
                local rawMemberCount = math.floor(SafeNumber(info.numMembers, 0))
                if rawMemberCount < 1 or rawMemberCount > 5 then
                    applicantsIncomplete = true
                end
                local memberCount = rawMemberCount
                if memberCount > 5 then memberCount = 5 end
                if memberCount > 0 then
                    local appIndex = #validAppIDs + 1
                    validAppIDs[appIndex] = id
                    validAppAPITokens[appIndex] = apiID or id
                    validAppMemberCounts[appIndex] = memberCount
                    validAppOrder[appIndex] = appIndex
                    expectedApplicantMemberCount =
                        expectedApplicantMemberCount + memberCount
                end
            end
        else
            applicantsIncomplete = true
        end
    end
    table.sort(validAppOrder, function(a, b)
        return validAppIDs[a] < validAppIDs[b]
    end)

    -- Wire format v2: emit one block per group member (was: only the leader).
    -- Single-pass shadow-table approach — count is derived from successfully-
    -- emitted blocks, not from numMembers sum, so:
    --   (a) no count/emit race possible (header count cannot disagree with
    --       what was actually appended);
    --   (b) detects GetApplicantMemberInfo returning nil for transient
    --       member-load lag (rare; members 2+ may lag by ≤1 frame on first
    --       list-update). One missing member makes the whole applicant domain
    --       non-authoritative until a later complete snapshot replaces it.
    -- Per-block byte layout (v12):
    --   uint32 applicant_id, u8 member_idx (1-based), u8 class_id,
    --   u16 spec_id, u16 ilvl, u16 rio_score, u16 main_score,
    --   u8 rio_profile, u8 rio_best_key, u8 rio_best_dungeon_key,
    --   u8 rio_timed_at_or_above, u8 rio_timed_at_or_above_minus1,
    --   u8 rio_timed_at_or_above_minus2, u8 rio_completed_at_or_above_minus1,
    --   u8 rio_dungeon_count, u8 role, len-prefixed name,
    --   u8 application_member_count, u16 blizzard_mplus_score,
    --   u8 blizzard_best_dungeon_key, u8 blizzard_best_key.
    local memberOut = {}
    local emittedCount = 0
    for _, appIndex in ipairs(validAppOrder) do
        local appID = validAppIDs[appIndex]
        local apiToken = validAppAPITokens[appIndex]
        for m = 1, validAppMemberCounts[appIndex] do
            local memberOK, rawMemberName, memberClass, memberILvl,
                  memberRole, memberScore, memberSpecID =
                entryCreationKeyState.GetApplicantMemberInfoForTransport(apiToken, m)
            local memberName = SafeStr(rawMemberName, "")
            if memberOK and not _IsPlaceholderCleanUnitName(memberName) then
                local classToken = SafeEnumKey(memberClass, "")
                local roleToken = SafeEnumKey(memberRole, "DAMAGER")
                table.insert(memberOut, _Uint32BE(appID))
                table.insert(memberOut, string.char(m))
                table.insert(memberOut, string.char(CLASS_NAME_TO_ID[classToken] or 0))
                table.insert(memberOut, _Uint16BE(SafeNumber(memberSpecID, 0)))
                table.insert(memberOut, _Uint16BE(SafeRoundedNumber(memberILvl, 0)))
                local rioSummary = _GetRaiderIOMPlusSummaryForCleanName(
                    _RaiderIOProfileLookupNameFromCleanName(memberName, playerRealm),
                    listingActivityIDForRio,
                    listingKeyLevelForRio
                )
                -- v12 fixes the old semantic mismatch: this wire slot is now the
                -- actual Raider.IO current-character score. Blizzard's Group
                -- Finder score is carried separately below as fallback/context.
                table.insert(memberOut, _Uint16BE(rioSummary.currentScore))
                entryCreationKeyState.AppendRaiderIOMPlusSummary(memberOut, rioSummary)
                table.insert(memberOut, string.char(ROLE_NAME_TO_BYTE[roleToken] or 2))
                _PackCleanLenStr(memberOut, memberName)
                local blizzardBestDungeonKey, blizzardBestKey =
                    entryCreationKeyState.GetApplicantDungeonContextForTransport(
                        apiToken, m, listingActivityIDForRio
                    )
                table.insert(memberOut, string.char(_ClampUInt8(validAppMemberCounts[appIndex])))
                table.insert(memberOut, _Uint16BE(_ClampUInt16(SafeRoundedNumber(memberScore, 0))))
                table.insert(memberOut, string.char(_ClampUInt8(blizzardBestDungeonKey)))
                table.insert(memberOut, string.char(_ClampUInt8(blizzardBestKey)))
                emittedCount = emittedCount + 1
            end
        end
    end

    -- The member block is already fully ordered. Append its serialized bytes as
    -- one chunk instead of copying every field chunk into the outer payload on
    -- each transport poll.
    local memberPayload = table.concat(memberOut)
    if emittedCount < expectedApplicantMemberCount then
        applicantsIncomplete = true
    end
    -- IMPORTANT: an incomplete Blizzard read is non-authoritative, but the rows
    -- that were readable are still useful. v13 carries those partial rows with
    -- FLAG_APPLICANTS_UNAVAILABLE set. The Companion merges them into the last
    -- authoritative snapshot and never deletes absent rows until a complete v12
    -- snapshot arrives. This prevents one transient applicant/member from
    -- freezing every newer applicant out of the overlay.
    table.insert(out, _Uint16BE(emittedCount))
    table.insert(out, memberPayload)
    entryCreationKeyState.lastPayloadApplicantCount = emittedCount
    entryCreationKeyState.lastPayloadApplicantsIncomplete = applicantsIncomplete

    local rosterPayload, rosterCount = "", 0
    local rosterIncomplete = false
    local rosterQuietSignature, rosterQuietHasUnknownSpec, rosterQuietInRaid =
        nil, false, false
    if not terminalClear and not rosterUnavailable then
        rosterPayload, rosterCount, rosterQuietSignature,
        rosterQuietHasUnknownSpec, rosterQuietInRaid, rosterIncomplete =
            BuildRosterPayloadRows(
                listingActivityIDForRio,
                listingKeyLevelForRio,
                cleanEntry ~= nil
            )
    end
    entryCreationKeyState.lastPayloadRosterIncomplete = rosterIncomplete
    if rosterIncomplete then
        rosterPayload = ""
        rosterCount = 0
        rosterQuietSignature = nil
        rosterQuietHasUnknownSpec = false
        rosterQuietInRaid = false
    end
    entryCreationKeyState.lastPayloadRosterCount = rosterCount
    rosterUnavailable = rosterUnavailable or rosterIncomplete
    if rosterUnavailable then
        headerFlags = headerFlags + 0x04
    end
    if applicantsIncomplete then
        headerFlags = headerFlags + 0x08
    end
    -- v12 carries explicit Raider.IO vs Blizzard score semantics plus atomic
    -- application metadata. v13 is the same layout with applicant-authority
    -- unavailable; paired older companions fail closed instead of clearing rows.
    out[wireVersionChunkIndex] = string.char(applicantsIncomplete and 0x0D or 0x0C)
    out[headerFlagsChunkIndex] = string.char(headerFlags)
    if cleanEntry and not applicantsIncomplete and not rosterUnavailable
       and #validAppOrder == 0
       and rosterCount == 5
       and rosterQuietSignature
       and not rosterQuietInRaid
       and not rosterQuietHasUnknownSpec then
        local quietOut = {}
        local listingSig = listingQuietSignature or ""
        table.insert(quietOut, _Uint16BE(#listingSig))
        table.insert(quietOut, listingSig)
        table.insert(quietOut, _Uint16BE(#leaderQuietSignature))
        table.insert(quietOut, leaderQuietSignature)
        table.insert(quietOut, _Uint16BE(#rosterQuietSignature))
        table.insert(quietOut, rosterQuietSignature)
        entryCreationKeyState.lastPayloadQuietFullPartySignature = table.concat(quietOut)
    end
    table.insert(out, _Uint16BE(rosterCount))
    table.insert(out, rosterPayload)

    -- Patch the dedicated length chunk before concat so finalization does not
    -- copy almost the entire body through substring slicing. CRC32 and the
    -- runtime dedup hash then share one body scan; only the four CRC trailer
    -- bytes need to be folded into the hash afterward.
    local bodyLength = 0
    for i = 1, #out do bodyLength = bodyLength + #out[i] end
    local totalLength = bodyLength + 4
    entryCreationKeyState.lastPayloadTotalBytes = totalLength
    if totalLength > 65535 then
        entryCreationKeyState.lastPayloadBuildError =
            "complete snapshot exceeds APS1 uint16 length limit (" ..
            tostring(totalLength) .. " bytes)"
        return nil, nil
    end
    out[lengthChunkIndex] = _Uint16BE(totalLength)
    local crc, snapshotHash = _CRC32AndSnapshotHash(out)
    local crcBytes = _Uint32BE(crc)
    for i = 1, #crcBytes do
        snapshotHash = ((snapshotHash * 33) + string.byte(crcBytes, i)) % 4294967296
    end
    out[#out + 1] = crcBytes
    return table.concat(out), snapshotHash
end

entryCreationKeyState.ClearQROverflowTransport = function(reason)
    local state = entryCreationKeyState.qrOverflowState
    if state and reason == "superseded" then
        entryCreationKeyState.qrOverflowSupersededCount =
            (entryCreationKeyState.qrOverflowSupersededCount or 0) + 1
    end
    entryCreationKeyState.qrOverflowState = nil
end

entryCreationKeyState.EnsureQROverflowStreamID = function()
    if entryCreationKeyState.qrOverflowStreamID then
        return entryCreationKeyState.qrOverflowStreamID
    end
    -- A new addon load is a new producer stream. GetServerTime supplies a
    -- wall-clock epoch while GetTime's millisecond component distinguishes a
    -- rapid /reload inside the same second. The companion uses screenshot
    -- source ordering when streams change; this value is identity, not trust.
    local serverSeconds = math.floor(SafeNumber(
        GetServerTime and GetServerTime(), 0
    ))
    local clientMillis = math.floor(SafeNumber(
        GetTime and GetTime(), 0
    ) * 1000)
    local streamID = (serverSeconds * 1009 + clientMillis * 9176 + 1) % 4294967296
    if streamID == 0 then streamID = 1 end
    entryCreationKeyState.qrOverflowStreamID = streamID
    return streamID
end

entryCreationKeyState.ReadUint32BE = function(value, offset)
    offset = offset or 1
    return string.byte(value, offset) * 16777216
        + string.byte(value, offset + 1) * 65536
        + string.byte(value, offset + 2) * 256
        + string.byte(value, offset + 3)
end

entryCreationKeyState.StartQROverflowTransport = function(
    logicalPayload,
    logicalHash,
    dirtyGeneration,
    applicantCount,
    rosterIncomplete,
    quietSignature
)
    if type(logicalPayload) ~= "string" or #logicalPayload < 13 then
        return nil, "complete APS1 payload is unavailable"
    end
    if #logicalPayload > 65535 then
        return nil, "complete APS1 payload exceeds 65535 bytes"
    end
    local chunkBytes = entryCreationKeyState.QR_OVERFLOW_FRAGMENT_BYTES
    local chunkCount = math.ceil(#logicalPayload / chunkBytes)
    if chunkCount < 2 then
        return nil, "overflow payload unexpectedly fits one fragment"
    end
    if chunkCount > entryCreationKeyState.QR_OVERFLOW_MAX_FRAGMENTS then
        return nil, "overflow requires " .. tostring(chunkCount) ..
            " fragments (max " ..
            tostring(entryCreationKeyState.QR_OVERFLOW_MAX_FRAGMENTS) .. ")"
    end
    local generation =
        ((entryCreationKeyState.qrOverflowGenerationCounter or 0) + 1)
        % 4294967296
    if generation == 0 then generation = 1 end
    entryCreationKeyState.qrOverflowGenerationCounter = generation
    local state = {
        streamID = entryCreationKeyState.EnsureQROverflowStreamID(),
        generation = generation,
        logicalPayload = logicalPayload,
        logicalHash = logicalHash,
        logicalCRC = entryCreationKeyState.ReadUint32BE(
            logicalPayload,
            #logicalPayload - 3
        ),
        logicalBytes = #logicalPayload,
        chunkCount = chunkCount,
        chunkIndex = 0,
        pass = 1,
        queuedNewer = false,
        dirtyGeneration = dirtyGeneration or 0,
        applicantCount = applicantCount or 0,
        rosterIncomplete = rosterIncomplete == true,
        quietSignature = quietSignature,
        failure = nil,
    }
    entryCreationKeyState.qrOverflowState = state
    entryCreationKeyState.qrOverflowLastFailure = nil
    return state, nil
end

entryCreationKeyState.BuildQROverflowFragment = function(state)
    if type(state) ~= "table" or type(state.logicalPayload) ~= "string" then
        return nil, "overflow state is unavailable"
    end
    local index = math.floor(SafeNumber(state.chunkIndex, 0))
    local count = math.floor(SafeNumber(state.chunkCount, 0))
    if index < 0 or index >= count then
        return nil, "overflow fragment index is out of range"
    end
    local chunkBytes = entryCreationKeyState.QR_OVERFLOW_FRAGMENT_BYTES
    local first = index * chunkBytes + 1
    local chunk = string.sub(state.logicalPayload, first, first + chunkBytes - 1)
    local out = {
        "APS1",
        string.char(entryCreationKeyState.QR_OVERFLOW_WIRE_VERSION),
        "\0\0",
        "\0",
        "\0",
        _Uint32BE(state.streamID),
        _Uint32BE(state.generation),
        _Uint16BE(index),
        _Uint16BE(count),
        _Uint16BE(state.logicalBytes),
        _Uint32BE(state.logicalCRC),
        chunk,
    }
    local totalLength = 31 + #chunk
    out[3] = _Uint16BE(totalLength)
    local crc = _CRC32AndSnapshotHash(out)
    out[#out + 1] = _Uint32BE(crc)
    return table.concat(out), nil
end

entryCreationKeyState.AdvanceQROverflowTransport = function(state)
    if state ~= entryCreationKeyState.qrOverflowState then
        return false, false
    end
    state.chunkIndex = state.chunkIndex + 1
    if state.chunkIndex < state.chunkCount then
        return false, false
    end
    state.chunkIndex = 0
    local completedPass = state.pass
    if state.queuedNewer then
        entryCreationKeyState.ClearQROverflowTransport("superseded")
        return true, false
    end
    state.pass = state.pass + 1
    if state.pass > entryCreationKeyState.QR_OVERFLOW_MIN_SENDS then
        entryCreationKeyState.ClearQROverflowTransport("complete")
        return true, true
    end
    return completedPass > 0, false
end

local _addonNS = select(2, ...)

-- Resolve QR encoder reference (set by libs/qrencode.lua via addon namespace).
-- Nil-safe so BuildQRMatrix can show its missing-library diagnostic instead of
-- crashing at file load if the embedded QR library failed to populate ns.QR.
local _qrencode = _addonNS.QR and _addonNS.QR.qrcode

-- Acquire (or reuse from pool) a black-rectangle texture and position+size it.
-- Returns the texture or nil if pool exhausted (caller logs warning).
-- Pool grows as needed; never shrinks. Excess textures from prior larger QRs
-- are hidden, not destroyed (cheap reuse on next render).
entryCreationKeyState.QR_TEXTURE_RENDER_BUDGET = 6000  -- total pooled textures; per-frame work is chunked below
entryCreationKeyState.QR_TEXTURE_PAINT_CHUNK = 450     -- max texture ops per frame while painting one QR
entryCreationKeyState.QR_RUN_SCAN_ROWS_PER_FRAME = 12 -- bound matrix analysis work per frame
entryCreationKeyState.QR_RUN_STRIDE = 4               -- flat x, y, width, height values per run
entryCreationKeyState.QR_FAILURE_NOTICE_COOLDOWN_S = 30 -- keep persistent failures out of chat spam
entryCreationKeyState.QR_PIXEL_UI_REFERENCE_HEIGHT = 768 -- WoW's physical-pixel conversion baseline
entryCreationKeyState.QR_LARGE_PAYLOAD_BYTES = 320 -- compact encoding for applicant bursts
-- Keep normal applicant bursts in one screenshot. At 1400 APS1 bytes the hex/L
-- QR still has comfortable Version-40 headroom, while 8-20 player queues avoid
-- the multi-screenshot fragment delay that previously made the overlay lag.
entryCreationKeyState.QR_STEALTH_FRAGMENT_THRESHOLD_BYTES = 1400
entryCreationKeyState.GetQRModuleUISize = function()
    local pixelUtil = SafeTable(_G.PixelUtil)
    local convert = pixelUtil and pixelUtil.ConvertPixelsToUIForRegion
    if type(convert) == "function" and qrFrame then
        local ok, converted = pcall(convert, QR_MODULE_PX, qrFrame)
        converted = ok and SafeNumber(converted, nil) or nil
        if converted and converted > 0 then return converted end
    end
    -- Mirror PixelUtil's conversion when the helper is absent or rejects the
    -- region. Raw UI units would reintroduce fractional physical module widths.
    local getPhysicalScreenSize = _G.GetPhysicalScreenSize
    local getEffectiveScale = qrFrame and qrFrame.GetEffectiveScale
    if type(getPhysicalScreenSize) == "function"
       and type(getEffectiveScale) == "function" then
        local screenOK, _, physicalHeight = pcall(getPhysicalScreenSize)
        local scaleOK, effectiveScale = pcall(getEffectiveScale, qrFrame)
        physicalHeight = screenOK and SafeNumber(physicalHeight, nil) or nil
        effectiveScale = scaleOK and SafeNumber(effectiveScale, nil) or nil
        if physicalHeight and physicalHeight > 0
           and effectiveScale and effectiveScale > 0 then
            local uiUnitFactor =
                entryCreationKeyState.QR_PIXEL_UI_REFERENCE_HEIGHT / physicalHeight
            return QR_MODULE_PX * uiUnitFactor / effectiveScale
        end
    end
    -- Last-resort compatibility for clients without either conversion API.
    return QR_MODULE_PX
end

local function _AcquireQRTexture(x, y, w, h)
    if qrTextureUsed >= entryCreationKeyState.QR_TEXTURE_RENDER_BUDGET then
        return nil
    end
    qrTextureUsed = qrTextureUsed + 1
    local t = qrTexturePool[qrTextureUsed]
    if not t then
        t = qrFrame:CreateTexture(nil, "BORDER")
        t:SetColorTexture(0, 0, 0, 1)
        qrTexturePool[qrTextureUsed] = t
    end
    t:ClearAllPoints()
    t:SetSize(w, h)
    t:SetPoint("TOPLEFT", qrFrame, "TOPLEFT", x, -y)
    t:Show()
    entryCreationKeyState.qrTextureVisibleHighWater = math.max(
        entryCreationKeyState.qrTextureVisibleHighWater or 0,
        qrTextureUsed
    )
    return t
end

local function _BuildQRBlackRunsAsync(
    matrix,
    quiet_offset,
    module_ui_size,
    limit,
    jobGen,
    onComplete
)
    local runs = {}
    local runCount = 0
    local nextRow = 1

    local function AddRun(x_start, y, run_len)
        runCount = runCount + 1
        if limit and runCount > limit then
            onComplete(nil, runCount)
            return false
        end
        local baseIndex = #runs
        runs[baseIndex + 1] = quiet_offset + (x_start - 1) * module_ui_size
        runs[baseIndex + 2] = quiet_offset + (y - 1) * module_ui_size
        runs[baseIndex + 3] = run_len * module_ui_size
        runs[baseIndex + 4] = module_ui_size
        return true
    end

    local function ContinueBuild()
        if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
        local chunkEnd = math.min(
            #matrix,
            nextRow + entryCreationKeyState.QR_RUN_SCAN_ROWS_PER_FRAME - 1
        )
        for y = nextRow, chunkEnd do
            local row = matrix[y]
            local x_start = nil
            for x = 1, #row do
                local is_black = (row[x] or 0) > 0
                if is_black then
                    if x_start == nil then x_start = x end
                elseif x_start ~= nil then
                    local run_len = x - x_start
                    if not AddRun(x_start, y, run_len) then return end
                    x_start = nil
                end
            end
            if x_start ~= nil then
                local run_len = #row - x_start + 1
                if not AddRun(x_start, y, run_len) then return end
            end
        end
        nextRow = chunkEnd + 1
        if nextRow <= #matrix then
            C_Timer.After(0, ContinueBuild)
        else
            onComplete(runs, runCount)
        end
    end

    -- Always yield after QR encoding. Large Version 40 matrices have already
    -- consumed most of the current script watchdog budget before this scan.
    C_Timer.After(0, ContinueBuild)
end


-- Paint pre-built row runs into the frame. Matrix analysis and encode-mode
-- fallback complete asynchronously before this function starts.
local function PaintQR(matrix, runs, runCount, module_ui_size, jobGen, onComplete)
    local rows = #matrix
    local total_modules = rows + 2 * QR_QUIET_ZONE   -- assume square QR
    local frame_ui = total_modules * module_ui_size

    qrFrame:SetSize(frame_ui, frame_ui)
    qrCurrentSize = frame_ui
    _ApplyQRFramePosition()

    qrTextureUsed = 0
    local runIndex = 1

    local function CompletePaint(success)
        if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
        entryCreationKeyState.screenshotController:FinishPaint(jobGen, success)
        if not success and APSPrint then
            APSPrint("WARN: QR render exceeded pooled texture budget " ..
                     entryCreationKeyState.QR_TEXTURE_RENDER_BUDGET .. " — rendered QR is INCOMPLETE; companion will fail to decode")
        end
        if onComplete then onComplete(success) end
    end

    local function FinishPaint(success)
        if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
        -- Hide leftovers in the same bounded chunks as painting. Keep the
        -- visible high-water mark until cleanup completes: if a timer callback
        -- is aborted, the watchdog can retry and the next job still knows how
        -- far the stale black textures extend.
        local cleanupIndex = qrTextureUsed + 1
        local cleanupTarget = entryCreationKeyState.qrTextureVisibleHighWater or 0

        local function ContinueCleanup()
            if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
            local chunkEnd = math.min(
                cleanupTarget,
                cleanupIndex + entryCreationKeyState.QR_TEXTURE_PAINT_CHUNK - 1
            )
            for i = cleanupIndex, chunkEnd do
                local t = qrTexturePool[i]
                if t then t:Hide() end
            end
            cleanupIndex = chunkEnd + 1
            if cleanupIndex <= cleanupTarget then
                C_Timer.After(0, ContinueCleanup)
                return
            end
            entryCreationKeyState.qrTextureVisibleHighWater = qrTextureUsed
            CompletePaint(success)
        end

        if cleanupIndex <= cleanupTarget then
            C_Timer.After(0, ContinueCleanup)
        else
            entryCreationKeyState.qrTextureVisibleHighWater = qrTextureUsed
            CompletePaint(success)
        end
    end

    local function ContinuePaint()
        if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
        local chunkEnd = math.min(
            runCount,
            runIndex + entryCreationKeyState.QR_TEXTURE_PAINT_CHUNK - 1
        )
        while runIndex <= chunkEnd do
            local baseIndex = (runIndex - 1) * entryCreationKeyState.QR_RUN_STRIDE
            if not _AcquireQRTexture(
                runs[baseIndex + 1],
                runs[baseIndex + 2],
                runs[baseIndex + 3],
                runs[baseIndex + 4]
            ) then
                FinishPaint(false)
                return
            end
            runIndex = runIndex + 1
        end
        if runIndex > runCount then
            FinishPaint(true)
            return
        end
        C_Timer.After(0, ContinuePaint)
    end

    C_Timer.After(0, ContinuePaint)
    return true
end

-- Hex-encode bytes as uppercase ASCII. WHY: the screenshot transport must be
-- lossless across WoW -> image codec -> QR decoder -> Python. Some QR decoders
-- reinterpret arbitrary binary bytes as text/UTF-8, which can alter APS1 bytes.
-- Hex stays ASCII, uses QR alphanumeric mode efficiently, and is deterministic.
-- If a full hex frame does not fit, bounded APS1 fragments carry the same bytes.
local function _HexEncode(data)
    local out = {}
    for i = 1, #data do
        out[i] = string.format("%02X", string.byte(data, i))
    end
    return table.concat(out)
end

local function _QREncodeModeLabel(kind, ec_level)
    local ec = (ec_level == 1 and "l")
            or (ec_level == 2 and "m")
            or ("ec" .. tostring(ec_level))
    return kind .. "-" .. ec
end

local function _SetLastQREncodeDiag(mode, payload_bytes, err)
    lastQREncodeMode = mode
    lastQREncodeBytes = payload_bytes or 0
    lastQREncodeError = err
    if not err then
        entryCreationKeyState.lastQREncodeFailurePrintAt = nil
    end
end

entryCreationKeyState.ShouldPrintQREncodeFailure = function()
    local now = GetTime()
    local lastPrintAt = entryCreationKeyState.lastQREncodeFailurePrintAt
    if lastPrintAt
       and now - lastPrintAt < entryCreationKeyState.QR_FAILURE_NOTICE_COOLDOWN_S then
        return false
    end
    entryCreationKeyState.lastQREncodeFailurePrintAt = now
    return true
end

-- Builds QR matrix from payload bytes via embedded lua-qrcode library. The
-- transport ladder uses only hexadecimal ASCII. Raw binary QR payloads are not
-- used because common desktop QR decoders can reinterpret high bytes as UTF-8,
-- breaking the byte-exact APS1 frame. Large payloads use hex/L and, if needed,
-- the existing bounded fragment transport.
-- WHY pcall: qrencode.lua's get_version_eclevel uses assert() (real Lua error)
-- on capacity overflow at line 214, NOT the documented (false, errmsg) tuple
-- return. Plain `local ok, result = _qrencode(...)` lets that error propagate
-- through scan-tick and floods BugSack with hundreds of identical errors per
-- minute on big payloads. pcall traps it; we then fall back to lower EC
-- (M=2 → L=1, ~26% more capacity at Version 40) for one more attempt.
local function _TryQrEncode(data, ec_level)
    local pcall_ok, ok, result = pcall(_qrencode, data, ec_level)
    if not pcall_ok then return nil, tostring(ok) end          -- assert blew up
    if not ok then return nil, tostring(result) end            -- documented failure
    return result, nil
end

local function BuildQRMatrix(
    payload,
    suppressFailurePrint,
    reliableHexOnly,
    jobGen,
    onComplete
)
    if not _qrencode then
        _SetLastQREncodeDiag("missing-lib", #payload, "QR library not loaded")
        if APSPrint and entryCreationKeyState.ShouldPrintQREncodeFailure() then
            APSPrint("CRITICAL: QR library not loaded — check libs/qrencode.lua")
        end
        onComplete(nil, nil)
        return
    end

    -- Start the encode ladder outside the 0.25s scan ticker callback. A Version
    -- 40 encode can legitimately consume most of one watchdog slice by itself.
    C_Timer.After(0, function()
        if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
        local attempts = {}
        local hex = _HexEncode(payload)
        if #payload > entryCreationKeyState.QR_LARGE_PAYLOAD_BYTES then
            table.insert(attempts, { kind = "hex", data = hex, ec_level = 1, size = #hex, unit = "hex" })
        else
            table.insert(attempts, { kind = "hex", data = hex, ec_level = QR_EC_LEVEL, size = #hex, unit = "hex" })
            if QR_EC_LEVEL ~= 1 then
                table.insert(attempts, { kind = "hex", data = hex, ec_level = 1, size = #hex, unit = "hex" })
            end
        end

        local first_label = nil
        local first_size = 0
        local first_unit = nil
        local failure_parts = {}
        local attemptIndex = 1

        local function FinishFailure()
            local err = table.concat(failure_parts, " | ")
            _SetLastQREncodeDiag("failed", #payload, err)
            if APSPrint
               and not suppressFailurePrint
               and entryCreationKeyState.ShouldPrintQREncodeFailure() then
                APSPrint("QR build failed (payload too large or too dense to render): "
                         .. tostring(err) .. " — payload=" .. #payload .. " bytes")
            end
            onComplete(nil, nil)
        end

        local function TryNextAttempt()
            if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
            local attempt = attempts[attemptIndex]
            attemptIndex = attemptIndex + 1
            if not attempt then
                FinishFailure()
                return
            end

            local label = _QREncodeModeLabel(attempt.kind, attempt.ec_level)
            if not first_label then
                first_label = label
                first_size = attempt.size
                first_unit = attempt.unit
            end
            local matrix, err = _TryQrEncode(attempt.data, attempt.ec_level)
            if not matrix then
                failure_parts[#failure_parts + 1] = label .. ": " .. tostring(err)
                C_Timer.After(0, TryNextAttempt)
                return
            end

            local module_ui_size = entryCreationKeyState.GetQRModuleUISize()
            _BuildQRBlackRunsAsync(
                matrix,
                QR_QUIET_ZONE * module_ui_size,
                module_ui_size,
                entryCreationKeyState.QR_TEXTURE_RENDER_BUDGET,
                jobGen,
                function(runs, renderRuns)
                    if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
                    if not runs then
                        failure_parts[#failure_parts + 1] = label .. ": render needs " ..
                            renderRuns .. " textures > pooled budget " ..
                            entryCreationKeyState.QR_TEXTURE_RENDER_BUDGET
                        C_Timer.After(0, TryNextAttempt)
                        return
                    end

                    _SetLastQREncodeDiag(label, #payload, nil)
                    if APSPrint and KeystoneLensBridgeDB and KeystoneLensBridgeDB.debug and label ~= first_label then
                        APSPrint(string.format(
                            "[APS-debug] QR fallback %s (%d %s) -> %s (%d bytes payload, %d textures)",
                            first_label, first_size, first_unit, label, #payload, renderRuns))
                    end
                    onComplete(matrix, runs, renderRuns, module_ui_size)
                end
            )
        end

        TryNextAttempt()
    end)
end


-- State for trigger throttling + dedup
-- (forward-declared at top — no `local` here. Without forward-decl, StartSession's
-- bare assignments would silently target globals instead of resetting these locals.)
lastSnapshotHash = nil
lastShotTime = 0
pendingShotDirty = false
lastQREncodeMode = "never"
lastQREncodeBytes = 0
lastQREncodeError = nil
qrForceVisibleForShot = false
qrForceVisibleShotGen = 0
entryCreationKeyState.SHOT_THROTTLE_S = 0.5
entryCreationKeyState.TRANSPORT_POLL_S = 1.0
local lastTransportPollTime = 0

local function _ReleaseForceVisibleShotLease(forceVisibleShotGen)
    if forceVisibleShotGen and qrForceVisibleShotGen == forceVisibleShotGen then
        qrForceVisibleForShot = false
        if qrFrame then qrFrame:SetFrameStrata("DIALOG") end
        _RefreshQRVisibility()
    end
end

local function _AcquireQRShotLease()
    -- WHY: every QR repaint needs a framebuffer settle delay, even when the
    -- frame was already visible; otherwise captures can decode APS1 magic with
    -- corrupt payload bytes from an old-new texture mix.
    qrForceVisibleShotGen = (qrForceVisibleShotGen or 0) + 1
    local forceVisibleShotGen = qrForceVisibleShotGen
    if not qrAlwaysVisible and not qrMoveMode then
        qrForceVisibleForShot = true
    end
    -- The capture lease is brief and non-interactive. TOOLTIP prevents chat
    -- replacements and other DIALOG-strata UI from covering QR pixels without
    -- leaving a permanently topmost frame after the capture finishes.
    if qrFrame then qrFrame:SetFrameStrata("TOOLTIP") end
    _RefreshQRVisibility()
    return forceVisibleShotGen, QR_RENDER_SETTLE_S
end

entryCreationKeyState.ClearQRTransportJob = function(jobGen)
    return entryCreationKeyState.screenshotController:Clear(jobGen)
end

entryCreationKeyState.OnScreenshotEvent = function(event)
    entryCreationKeyState.screenshotController:HandleEvent(event)
end

entryCreationKeyState.ScheduleTerminalClearRetry = function(clearSessionGen)
    if not clearSessionGen
       or entryCreationKeyState.terminalClearSessionGen ~= clearSessionGen
       or sessionGen ~= clearSessionGen
       or isSessionActive
       or entryCreationKeyState.terminalClearRetryScheduled
       or (entryCreationKeyState.terminalClearDispatchCount or 0)
          >= entryCreationKeyState.TERMINAL_CLEAR_MAX_DISPATCHES then
        return false
    end
    entryCreationKeyState.terminalClearRetryScheduled = true
    C_Timer.After(entryCreationKeyState.END_SESSION_CLEAR_RETRY_DELAY_S, function()
        if entryCreationKeyState.terminalClearSessionGen ~= clearSessionGen then
            return
        end
        entryCreationKeyState.terminalClearRetryScheduled = false
        if sessionGen ~= clearSessionGen
           or isSessionActive
           or entryCreationKeyState.qrPaintInProgress
           or entryCreationKeyState.qrCaptureInProgress
           or (entryCreationKeyState.terminalClearDispatchCount or 0)
              >= entryCreationKeyState.TERMINAL_CLEAR_MAX_DISPATCHES then
            return
        end
        MaybeTriggerScreenshot(true, nil, true)
    end)
    return true
end

entryCreationKeyState.RecoverStalledQRTransport = function(now)
    if not entryCreationKeyState.screenshotController:IsBusy() then
        return false
    end
    local startedAt = entryCreationKeyState.qrTransportJobStartedAt
    if type(startedAt) ~= "number"
       or now - startedAt < entryCreationKeyState.QR_TRANSPORT_JOB_TIMEOUT_S then
        return false
    end

    local wasTerminalClear = entryCreationKeyState.qrTransportJobTerminalClear
    local phase = entryCreationKeyState.screenshotController:GetPhase()
    local screenshotResultHandler = entryCreationKeyState.screenshotController:GetResultHandler()
    if entryCreationKeyState.screenshotController:IsCapturePhase()
       and type(screenshotResultHandler) == "function" then
        entryCreationKeyState.qrTransportRecoveryCount =
            (entryCreationKeyState.qrTransportRecoveryCount or 0) + 1
        entryCreationKeyState.qrTransportLastRecoveryReason = "capture result timeout"
        screenshotResultHandler(false, "result timeout")
        return true
    end
    entryCreationKeyState.qrPaintJobGen = (entryCreationKeyState.qrPaintJobGen or 0) + 1
    entryCreationKeyState.ClearQRTransportJob()
    _ReleaseForceVisibleShotLease(qrForceVisibleShotGen)
    pendingShotDirty = true
    entryCreationKeyState.qrTransportRecoveryCount =
        (entryCreationKeyState.qrTransportRecoveryCount or 0) + 1
    entryCreationKeyState.qrTransportLastRecoveryReason = phase .. " timeout"

    local lastPrintAt = entryCreationKeyState.qrTransportLastRecoveryPrintAt
    if APSPrint
       and (not lastPrintAt
            or now - lastPrintAt >= entryCreationKeyState.QR_RECOVERY_NOTICE_COOLDOWN_S) then
        entryCreationKeyState.qrTransportLastRecoveryPrintAt = now
        APSPrint("WARN: recovered stalled QR " .. phase .. " job; retrying latest snapshot")
    end

    if wasTerminalClear and not isSessionActive then
        entryCreationKeyState.ScheduleTerminalClearRetry(
            entryCreationKeyState.terminalClearSessionGen
        )
    else
        MarkDirty("qrwatchdog")
    end
    return true
end

-- Build payload, dedup vs last hash, throttle, paint QR, trigger Screenshot.
-- force=true bypasses dedup AND throttle (used by EndSession + /kl sync).
-- entryHint: optional pre-fetched C_LFGList.GetActiveEntryInfo() result from
-- the scan-tick caller — avoids a second API call per scan. nil falls back
-- to fetching here (force-shot from EndSession / /kl sync).
-- QR paints for a short visibility lease, then Screenshot runs after the render
-- settle window; manual debug/move modes can keep the frame visible outside it.
MaybeTriggerScreenshot = function(force, entryHint, terminalClear, lfgReadsAllowed)
    if lfgReadsAllowed == nil then lfgReadsAllowed = true end
    -- "Can't fire" early-returns clear pendingShotDirty so the scan-ticker drain
    -- (line further below) doesn't spin endlessly calling us back when conditions
    -- haven't changed. Throttle path (further down) is the ONLY legitimate reason
    -- to set pendingShotDirty=true.
    if not (KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled) and not force then
        pendingShotDirty = false
        return
    end
    if not qrFrameCreated then
        pendingShotDirty = false
        return
    end

    -- Early exit when not hosting LFG: no entry to encode, payload would be a
    -- no-op snapshot. EndSession() uses force=true to dispatch one final clear-
    -- snapshot for companion state cleanup. Outside that, idle BuildPayload
    -- spam wastes CPU on every GROUP_ROSTER_UPDATE.
    if not isSessionActive and not force then
        pendingShotDirty = false
        return
    end

    -- Render-pipeline grace right after StartSession: see suppressShotsUntil
    -- assignment in StartSession for the rationale (newly Show()'d frame
    -- needs ≥1 render pass before painted QR textures are committed to
    -- the framebuffer that Screenshot() captures). Set pendingShotDirty so
    -- the scan-tick drain retries on subsequent ticks once the window
    -- expires; force-shot path (EndSession final clear) bypasses.
    if not force and suppressShotsUntil and GetTime() < suppressShotsUntil then
        pendingShotDirty = true
        return
    end

    -- Interaction-hidden QR should not produce or dedupe a payload. Keep the
    -- latest state pending and let the scan ticker emit once the interaction
    -- frame closes; force shots still bypass for EndSession cleanup and
    -- explicit support commands.
    if not force and _qrSuppressedByInteraction then
        pendingShotDirty = true
        return
    end

    -- A terminal clear owns the transport through both bounded dispatches.
    -- Manual support shots are redundant after the session ended and must not
    -- replace its build, physical result waiter, or scheduled retry.
    if force
       and not terminalClear
       and entryCreationKeyState.TerminalClearOwnsTransport() then
        return
    end

    -- SCREENSHOT_* events carry no request identity. Never invoke Screenshot()
    -- twice concurrently: a forced/manual or terminal request waits until the
    -- old event (or watchdog timeout) is consumed, then rebuilds current state.
    if entryCreationKeyState.screenshotController:IsWaitingResult() then
        if force then
            entryCreationKeyState.QueuePendingForcedScreenshot(
                terminalClear,
                lfgReadsAllowed
            )
        else
            pendingShotDirty = true
            entryCreationKeyState.screenshotController:MarkDirty()
        end
        return
    end

    if entryCreationKeyState.screenshotController:IsBusy() and not force then
        pendingShotDirty = true
        entryCreationKeyState.screenshotController:MarkDirty()
        return
    end
    if force then
        entryCreationKeyState.screenshotController:ClearDirty()
    end

    local now = GetTime()
    local minShotInterval = entryCreationKeyState.qrOverflowState
        and entryCreationKeyState.QR_OVERFLOW_SHOT_INTERVAL_S
        or entryCreationKeyState.SHOT_THROTTLE_S
    if not force and now - lastShotTime < minShotInterval then
        pendingShotDirty = true
        return
    end

    local entry = nil
    if isSessionActive then
        -- Reuse caller's pre-fetched entry when available (scan-tick path);
        -- fall back to direct fetch for force-shot paths (EndSession, slash).
        entry = SafeTable(entryHint)
        if not entry and lfgReadsAllowed then
            entry = SafeTable(C_LFGList.GetActiveEntryInfo())
        end
    end
    local applicantIDs = {}
    entryCreationKeyState.applicantListReadIncomplete = false
    if entry and lfgReadsAllowed then
        local applicantsOK, rawApplicantIDs = pcall(C_LFGList.GetApplicants)
        local cleanApplicantIDs = applicantsOK and SafeTable(rawApplicantIDs) or nil
        if cleanApplicantIDs then
            applicantIDs = cleanApplicantIDs
            -- Blizzard exposes both the list and a count. If the list is
            -- temporarily shorter, keep every readable applicant but mark the
            -- snapshot partial so the Companion never deletes unseen rows and
            -- the transport keeps retrying until the list becomes authoritative.
            if type(C_LFGList.GetNumApplicants) == "function" then
                local countOK, rawCount = pcall(C_LFGList.GetNumApplicants)
                local expectedGroups = countOK and SafeNumber(rawCount, nil) or nil
                if expectedGroups and expectedGroups >= 0
                   and math.floor(expectedGroups) > #cleanApplicantIDs then
                    entryCreationKeyState.applicantListReadIncomplete = true
                end
            end
        else
            applicantIDs = nil
            entryCreationKeyState.applicantListReadIncomplete = true
        end
    end
    local lfgUnavailable = isSessionActive
       and not terminalClear
       and not lfgReadsAllowed
    local rosterLoadDeferredByOverflow = not force
        and not terminalClear
        and entryCreationKeyState.qrOverflowState ~= nil
        and entryCreationKeyState.qrOverflowState.rosterIncomplete == true
    local rosterLoadDeferred = not force
        and not terminalClear
        and (rosterLoadDeferredByOverflow
             or not entryCreationKeyState.ShouldAttemptRosterLoad())
    local rosterInspectPending = false
    if not terminalClear and not rosterLoadDeferred and applicantIDs ~= nil then
        -- Always give unresolved party data timeout/failure-budget ownership.
        -- Applicants only control whether the screenshot waits for that batch;
        -- they must not bypass the inspect lifecycle itself.
        rosterInspectPending =
            entryCreationKeyState.EnsureRosterInspectBatchBeforeSnapshot()
    end
    if not force
       and applicantIDs ~= nil
       and #applicantIDs == 0
       and entryCreationKeyState.lastEmittedApplicantCount == 0
       and entryCreationKeyState.ShouldDeferRosterChangeForPreflight()
       and rosterInspectPending
       and not entryCreationKeyState.rosterInspectBatchCombatDeferred then
        pendingShotDirty = true
        return
    end

    local payload, h = BuildPayload(
        entry,
        applicantIDs,
        terminalClear,
        lfgUnavailable,
        rosterLoadDeferred
    )
    local latestPayload, latestHash = payload, h
    local latestDirtyGeneration =
        entryCreationKeyState.transportDirtyGeneration or 0
    local logicalPayload = latestPayload
    local payloadDirtyGeneration = latestDirtyGeneration
    local payloadApplicantCount = entryCreationKeyState.lastPayloadApplicantCount
    local payloadApplicantsIncomplete =
        entryCreationKeyState.lastPayloadApplicantsIncomplete == true
    local payloadRosterIncomplete = rosterLoadDeferred
        or entryCreationKeyState.lastPayloadRosterIncomplete
    local quietSignature = entryCreationKeyState.lastPayloadQuietFullPartySignature
    local overflowState = entryCreationKeyState.qrOverflowState
    local overflowInUse = false

    if terminalClear and overflowState then
        entryCreationKeyState.ClearQROverflowTransport("terminal-clear")
        overflowState = nil
    elseif overflowState then
        -- Freeze one complete logical generation until at least one full pass
        -- has been captured. Rapid applicant churn is queued instead of
        -- repeatedly abandoning partial generations that the companion can
        -- never assemble.
        local newerQueued =
            latestPayload == nil or latestHash ~= overflowState.logicalHash
        if newerQueued and overflowState.pass > 1 then
            -- The first complete pass is already recoverable. Do not spend a
            -- whole redundant pass on stale bytes once a newer logical state
            -- is known; start its normal/full-or-fragment path immediately.
            entryCreationKeyState.ClearQROverflowTransport("superseded")
            overflowState = nil
        else
            overflowState.queuedNewer = newerQueued
        end
    end
    if not overflowState
       and not terminalClear
       and type(latestPayload) == "string"
       and #latestPayload > entryCreationKeyState.QR_STEALTH_FRAGMENT_THRESHOLD_BYTES then
        local startedState = entryCreationKeyState.StartQROverflowTransport(
            latestPayload,
            latestHash,
            latestDirtyGeneration,
            entryCreationKeyState.lastPayloadApplicantCount,
            payloadRosterIncomplete,
            quietSignature
        )
        if startedState then
            overflowState = startedState
        end
    end
    if overflowState then
        logicalPayload = overflowState.logicalPayload
        h = overflowState.logicalHash
        payloadDirtyGeneration = overflowState.dirtyGeneration
        payloadApplicantCount = overflowState.applicantCount
        payloadRosterIncomplete = overflowState.rosterIncomplete
        quietSignature = overflowState.quietSignature
        payload = entryCreationKeyState.BuildQROverflowFragment(overflowState)
        if not payload then
            overflowState.failure = "could not build overflow fragment"
            entryCreationKeyState.qrOverflowLastFailure = overflowState.failure
            pendingShotDirty = false
            return
        end
        overflowInUse = true
    elseif latestPayload == nil then
        local reason = entryCreationKeyState.lastPayloadBuildError
            or "complete snapshot serialization failed"
        lastQREncodeMode = "logical-failed"
        lastQREncodeBytes = entryCreationKeyState.lastPayloadTotalBytes or 0
        lastQREncodeError = reason
        entryCreationKeyState.qrOverflowLastFailure = reason
        pendingShotDirty = false
        if APSPrint and entryCreationKeyState.ShouldPrintQREncodeFailure() then
            APSPrint("QR transport failed: " .. reason)
        end
        return
    end

    if force then
        -- Explicit support/terminal shots always get a fresh bounded attempt.
        entryCreationKeyState.ClearScreenshotFailureState()
    elseif entryCreationKeyState.screenshotFailureHash == h then
        if (entryCreationKeyState.screenshotFailureAttemptCount or 0)
           >= entryCreationKeyState.SCREENSHOT_FAILURE_MAX_ATTEMPTS then
            pendingShotDirty = false
            return
        end
    else
        -- A new payload gets its own bounded retry budget. Event churn that
        -- serializes to the same bytes must not restart a persistent failure loop.
        entryCreationKeyState.ClearScreenshotFailureState()
    end
    -- WHY: companion cannot ACK successful decode. One malformed screenshot can
    -- otherwise suppress a changed listing or roster snapshot until another event.
    -- Bound this to one retry; stable snapshots never become periodic heartbeats.
    local resendSameNonterminalSnapshot =
        not force
        and not terminalClear
        and h == lastSnapshotHash
        and entryCreationKeyState.lastDeliverySnapshotHash == h
        and ((entryCreationKeyState.lastDeliverySnapshotSendCount or 0)
             < entryCreationKeyState.NONTERMINAL_SNAPSHOT_MIN_SENDS)
    if not force and h == lastSnapshotHash and not resendSameNonterminalSnapshot then
        if payloadRosterIncomplete then
            if rosterLoadDeferredByOverflow
               or entryCreationKeyState.ScheduleRosterLoadRetry() then
                pendingShotDirty = payloadApplicantsIncomplete and true or false
            else
                pendingShotDirty = true
            end
        elseif payloadApplicantsIncomplete then
            -- Do not capture the identical partial QR again. Keep the scan
            -- ticker alive so newly readable Blizzard applicant/member data is
            -- detected and emitted immediately when its payload hash changes.
            pendingShotDirty = true
        else
            pendingShotDirty = false  -- nothing new to render for same hash
            entryCreationKeyState.ClearRosterLoadRetryState()
        end
        entryCreationKeyState.ClearRosterCompositionChanged()
        return
    end

    if not force and quietSignature then
        if entryCreationKeyState.lastQuietFullPartySignature == quietSignature
           and not resendSameNonterminalSnapshot then
            lastSnapshotHash = h
            pendingShotDirty = false
            entryCreationKeyState.ClearRosterLoadRetryState()
            entryCreationKeyState.ClearRosterCompositionChanged()
            return
        end
    else
        entryCreationKeyState.lastQuietFullPartySignature = nil
    end

    if terminalClear then
        if entryCreationKeyState.terminalClearSessionGen ~= sessionGen then
            entryCreationKeyState.terminalClearSessionGen = sessionGen
            entryCreationKeyState.terminalClearDispatchCount = 0
            entryCreationKeyState.terminalClearRetryScheduled = false
        end
        if (entryCreationKeyState.terminalClearDispatchCount or 0)
           >= entryCreationKeyState.TERMINAL_CLEAR_MAX_DISPATCHES then
            pendingShotDirty = false
            return
        end
        entryCreationKeyState.terminalClearDispatchCount =
            (entryCreationKeyState.terminalClearDispatchCount or 0) + 1
    end

    -- Encode payload, analyze its row-RLE runs, then paint. The job generation
    -- cancels stale callbacks while each heavy stage yields to a fresh frame.
    -- Hex-only QR transport prevents binary/text reinterpretation by desktop
    -- QR decoders. If a full frame cannot fit or render, transmit the frozen
    -- complete payload as bounded v10 fragments. Capacity pressure must never
    -- pretend that an available roster vanished.
    local reliableHexOnly = overflowInUse
        or #payload > entryCreationKeyState.QR_LARGE_PAYLOAD_BYTES
    local jobGen = (entryCreationKeyState.qrPaintJobGen or 0) + 1
    entryCreationKeyState.qrPaintJobGen = jobGen
    entryCreationKeyState.screenshotController:BeginBuild(
        jobGen, terminalClear, GetTime()
    )
    -- WHY: terminal clears are delayed until the QR paints. If a new session
    -- starts before that callback, the stale clear must not wipe the companion
    -- state for the fresh listing.
    local terminalClearSessionGen = terminalClear and sessionGen or nil

    local function OnQRPaintComplete(paintOK)
        if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
        local dirtyDuringPaint = entryCreationKeyState.qrPaintDirtyDuringPaint and not force
        entryCreationKeyState.screenshotController:ClearDirty()
        local dirtySincePaintStarted =
            dirtyDuringPaint
            or (entryCreationKeyState.transportDirtyGeneration or 0) ~= payloadDirtyGeneration
        if not paintOK then
            -- Paint failure is not delivery. Keep dedup state unchanged; a
            -- stable deterministic failure remains visible in status and can
            -- be retried explicitly without spinning the ticker forever.
            if overflowInUse and overflowState then
                overflowState.failure = "fragment paint failed"
                entryCreationKeyState.qrOverflowLastFailure = overflowState.failure
            end
            pendingShotDirty = dirtySincePaintStarted and true or false
            entryCreationKeyState.ClearQRTransportJob(jobGen)
            if terminalClearSessionGen then
                entryCreationKeyState.ScheduleTerminalClearRetry(
                    terminalClearSessionGen
                )
            end
            return
        end

        -- An interaction can open while QR encoding/painting yields across
        -- frames. Non-force work must remain pending instead of acquiring a
        -- lease that makes the QR cover the newly opened Blizzard panel.
        if not force then
            _TryHookInfoPanels()
            _RecomputeInteractionSuppression()
        end
        if not force and _qrSuppressedByInteraction then
            pendingShotDirty = true
            entryCreationKeyState.ClearQRTransportJob(jobGen)
            return
        end

        entryCreationKeyState.screenshotController:BeginSettle(jobGen)
        local forceVisibleShotGen, forceVisibleShotDelay = _AcquireQRShotLease()
        local completedPaintGen = entryCreationKeyState.qrPaintJobGen

        -- PaintQR above just updated the textures. Always wait the settle window
        -- after a successful repaint so texture updates reach the GPU framebuffer
        -- before Screenshot(), even when the frame was already visible.
        C_Timer.After(forceVisibleShotDelay, function()
            if terminalClearSessionGen
               and (sessionGen ~= terminalClearSessionGen or isSessionActive) then
                _ReleaseForceVisibleShotLease(forceVisibleShotGen)
                entryCreationKeyState.ClearQRTransportJob(jobGen)
                return
            end
            if entryCreationKeyState.qrPaintJobGen ~= completedPaintGen then
                _ReleaseForceVisibleShotLease(forceVisibleShotGen)
                return
            end
            -- Suppression may also begin during the framebuffer settle delay,
            -- after the lease was acquired. Release it and rebuild the latest
            -- payload after the interaction closes; force/terminal shots keep
            -- their explicit bypass semantics.
            if not force then
                _TryHookInfoPanels()
                _RecomputeInteractionSuppression()
            end
            if not force and _qrSuppressedByInteraction then
                pendingShotDirty = true
                entryCreationKeyState.ClearQRTransportJob(jobGen)
                _ReleaseForceVisibleShotLease(forceVisibleShotGen)
                return
            end
            local dirtySincePayload =
                dirtySincePaintStarted
                or (entryCreationKeyState.transportDirtyGeneration or 0) ~= payloadDirtyGeneration
            lastShotTime = GetTime()
            local screenshotCVarLeaseGeneration = entryCreationKeyState.screenshotController:AcquireCVarLease()
            -- Keep the screenshot-format lease until SCREENSHOT_SUCCEEDED/FAILED.
            -- Screenshot() is asynchronous on Retail: restoring the user's CVar
            -- 50 ms after the API call can change the actual file format/quality
            -- before the framebuffer is written, destroying a dense QR.
            local screenshotResolved = false
            local function FinishScreenshotAttempt(screenshotSucceeded, failureReason)
            if screenshotResolved
               or entryCreationKeyState.qrPaintJobGen ~= jobGen then
                return false
            end
            screenshotResolved = true
            -- The screenshot result event means the physical capture is done;
            -- only now is it safe to restore the user's screenshot CVars.
            entryCreationKeyState.screenshotController:ReleaseCVarLease(screenshotCVarLeaseGeneration, 0)
            if entryCreationKeyState.screenshotController:IsSuperseded() then
                entryCreationKeyState.screenshotLastResult = "superseded " ..
                    (failureReason or (screenshotSucceeded and "success" or "failure"))
                entryCreationKeyState.ClearQRTransportJob(jobGen)
                _ReleaseForceVisibleShotLease(forceVisibleShotGen)
                if not entryCreationKeyState.DispatchPendingForcedScreenshot()
                   and isSessionActive then
                    pendingShotDirty = true
                    MarkDirty("screenshotsuperseded")
                end
                return true
            end
            entryCreationKeyState.screenshotLastResult = failureReason
                or (screenshotSucceeded and "succeeded" or "failed")
            if not screenshotSucceeded then
                -- Do not commit dedup/delivery state for a capture that never
                -- completed. The pending drain retries the same payload after
                -- the normal throttle instead of treating it as delivered.
                if entryCreationKeyState.screenshotFailureHash == h then
                    entryCreationKeyState.screenshotFailureAttemptCount =
                        (entryCreationKeyState.screenshotFailureAttemptCount or 0) + 1
                else
                    entryCreationKeyState.screenshotFailureHash = h
                    entryCreationKeyState.screenshotFailureAttemptCount = 1
                end
                local retryBudgetRemaining =
                    entryCreationKeyState.screenshotFailureAttemptCount
                    < entryCreationKeyState.SCREENSHOT_FAILURE_MAX_ATTEMPTS
                pendingShotDirty = false
                if not terminalClearSessionGen then
                    pendingShotDirty = dirtySincePayload or retryBudgetRemaining
                end
                entryCreationKeyState.ClearQRTransportJob(jobGen)
                _ReleaseForceVisibleShotLease(forceVisibleShotGen)
                if terminalClearSessionGen then
                    entryCreationKeyState.TakePendingForcedScreenshot()
                    entryCreationKeyState.ScheduleTerminalClearRetry(
                        terminalClearSessionGen
                    )
                else
                    entryCreationKeyState.DispatchPendingForcedScreenshot()
                end
                if force then
                    APSPrint("WARN: screenshot capture failed during forced capture")
                elseif not retryBudgetRemaining then
                    APSPrint("WARN: screenshot capture failed repeatedly; snapshot paused until data changes or /kl sync")
                elseif KeystoneLensBridgeDB and KeystoneLensBridgeDB.debug then
                    print("|cff999999[APS-debug]|r screenshot capture failed; snapshot remains pending")
                end
                return true
            end
            entryCreationKeyState.ClearScreenshotFailureState()
            local overflowDeliveryCompleted = false
            if overflowInUse and overflowState then
                overflowState.failure = nil
                entryCreationKeyState.qrOverflowLastFailure = nil
                overflowDeliveryCompleted = select(
                    2,
                    entryCreationKeyState.AdvanceQROverflowTransport(overflowState)
                )
            end

            if not overflowInUse or overflowDeliveryCompleted then
                if not force and quietSignature then
                    entryCreationKeyState.lastQuietFullPartySignature = quietSignature
                end
                entryCreationKeyState.lastEmittedApplicantCount = payloadApplicantCount
                if not dirtySincePayload then
                    entryCreationKeyState.ClearRosterCompositionChanged()
                end
                lastSnapshotHash = h
                if not terminalClear then
                    if overflowDeliveryCompleted then
                        entryCreationKeyState.lastDeliverySnapshotHash = h
                        entryCreationKeyState.lastDeliverySnapshotSendCount =
                            entryCreationKeyState.QR_OVERFLOW_MIN_SENDS
                    elseif entryCreationKeyState.lastDeliverySnapshotHash == h then
                        entryCreationKeyState.lastDeliverySnapshotSendCount =
                            (entryCreationKeyState.lastDeliverySnapshotSendCount or 0) + 1
                    else
                        entryCreationKeyState.lastDeliverySnapshotHash = h
                        entryCreationKeyState.lastDeliverySnapshotSendCount = 1
                    end
                else
                    entryCreationKeyState.lastDeliverySnapshotHash = nil
                    entryCreationKeyState.lastDeliverySnapshotSendCount = 0
                end
                pendingShotDirty = false
                if payloadRosterIncomplete then
                    local retryScheduled =
                        force
                        or rosterLoadDeferredByOverflow
                        or entryCreationKeyState.ScheduleRosterLoadRetry()
                    pendingShotDirty = dirtySincePayload
                        or payloadApplicantsIncomplete
                        or not retryScheduled
                elseif payloadApplicantsIncomplete then
                    pendingShotDirty = true
                elseif dirtySincePayload then
                    pendingShotDirty = true
                elseif not force
                   and not terminalClear
                   and ((entryCreationKeyState.lastDeliverySnapshotSendCount or 0)
                        < entryCreationKeyState.NONTERMINAL_SNAPSHOT_MIN_SENDS) then
                    pendingShotDirty = true
                else
                    entryCreationKeyState.ClearRosterLoadRetryState()
                end
            else
                -- Every fragment capture is only progress toward one complete
                -- logical delivery. Keep the same generation pending until a
                -- full pass (and, when unchanged, its bounded redundant pass)
                -- has been captured. If a newer snapshot was queued, the
                -- first completed pass retires this generation and rebuilds it.
                pendingShotDirty = true
            end
            if KeystoneLensBridgeDB and KeystoneLensBridgeDB.debug then
                local overflowProgress = overflowInUse and overflowState
                    and string.format(
                        " fragment=%d/%d pass=%d",
                        math.min(overflowState.chunkIndex + 1, overflowState.chunkCount),
                        overflowState.chunkCount,
                        overflowState.pass
                    ) or ""
                print(string.format("|cff999999[APS-debug]|r CAP qr_size=%.2fui hash=%x t=%.2f%s",
                      qrCurrentSize, h, GetTime(), overflowProgress))
            end
            entryCreationKeyState.ClearQRTransportJob(jobGen)
            if terminalClearSessionGen then
                entryCreationKeyState.TakePendingForcedScreenshot()
                entryCreationKeyState.ScheduleTerminalClearRetry(
                    terminalClearSessionGen
                )
            else
                entryCreationKeyState.DispatchPendingForcedScreenshot()
            end
            _ReleaseForceVisibleShotLease(forceVisibleShotGen)
            return true
            end

            -- Screenshot() has no delivery return value. Arm the result
            -- handler before invoking it because current Retail may dispatch a
            -- synchronous SCREENSHOT_* event from inside this call.
            entryCreationKeyState.screenshotController:ArmResult(
                jobGen, FinishScreenshotAttempt
            )
            entryCreationKeyState.screenshotLastResult = "requested"
            -- Keep Blizzard's normal screenshot feedback intact. KeystoneLens must not
            -- hide capture status from the player while the QR transport is active.
            local screenshotOK = pcall(Screenshot)
            -- Do NOT hide the QR when Screenshot() merely returns. Retail may
            -- finish the framebuffer capture later. FinishScreenshotAttempt()
            -- releases the QR only after SCREENSHOT_SUCCEEDED/FAILED (or the
            -- existing watchdog timeout), preventing blank/QR-less screenshots.
            if not screenshotOK then
                FinishScreenshotAttempt(false, "Screenshot() API error")
            end
        end)

        if KeystoneLensBridgeDB and KeystoneLensBridgeDB.debug then
            local applicantCount = applicantIDs and tostring(#applicantIDs)
                or "unavailable"
            print(string.format("|cff999999[APS-debug]|r SHOT bytes=%d apps=%s hash=%x",
                  #payload, applicantCount, h))
        end
    end

    local OnQRBuildComplete
    OnQRBuildComplete = function(matrix, runs, renderRunCount, module_ui_size)
        if entryCreationKeyState.qrPaintJobGen ~= jobGen then return end
        if not matrix and not overflowInUse and not terminalClear then
            local startedState, startError =
                entryCreationKeyState.StartQROverflowTransport(
                    logicalPayload,
                    h,
                    payloadDirtyGeneration,
                    payloadApplicantCount,
                    payloadRosterIncomplete,
                    quietSignature
                )
            if startedState then
                overflowState = startedState
                overflowInUse = true
                payload, startError =
                    entryCreationKeyState.BuildQROverflowFragment(startedState)
                if payload then
                    quietSignature = startedState.quietSignature
                    BuildQRMatrix(payload, false, true, jobGen, OnQRBuildComplete)
                    return
                end
            end
            entryCreationKeyState.qrOverflowLastFailure =
                startError or "overflow transport could not start"
        end
        if not matrix then
            -- Build failure is not delivery. Preserve a change that arrived
            -- while this async job was running, but do not spin indefinitely
            -- on a stable deterministic QR/library failure.
            local dirtySinceBuildStarted =
                (entryCreationKeyState.qrPaintDirtyDuringPaint and not force)
                or (entryCreationKeyState.transportDirtyGeneration or 0) ~= payloadDirtyGeneration
            entryCreationKeyState.ClearQRTransportJob(jobGen)
            pendingShotDirty = dirtySinceBuildStarted and true or false
            if overflowInUse and overflowState then
                overflowState.failure = lastQREncodeError or "fragment QR build failed"
                entryCreationKeyState.qrOverflowLastFailure = overflowState.failure
            end
            if terminalClearSessionGen then
                entryCreationKeyState.ScheduleTerminalClearRetry(
                    terminalClearSessionGen
                )
            end
            return
        end
        PaintQR(
            matrix,
            runs,
            renderRunCount,
            module_ui_size,
            jobGen,
            OnQRPaintComplete
        )
    end

    BuildQRMatrix(
        payload,
        reliableHexOnly and not overflowInUse,
        reliableHexOnly,
        jobGen,
        OnQRBuildComplete
    )
end


-- ───────────────────────────────────────────────────────────
-- LFG entry creation: capture the host key level only.
--
-- Blizzard may keep the active listing's exact key level out of ordinary reads.
-- These secure hooks do not modify the form, choose a playstyle, create/update a
-- listing, or send chat. They only queue a primitive flag; the normal clean
-- ticker later attaches the existing key-level capture helper.

entryCreationKeyState.QueueLFGEntryCreationKeyCapture = function()
    entryCreationKeyState.lfgEntryCreationKeyCapturePending = true
end

entryCreationKeyState.ProcessLFGEntryCreationDeferredWork = function()
    if not entryCreationKeyState.lfgEntryCreationKeyCapturePending then return end
    local frame = _G.LFGListFrame
    local panel = frame and frame.EntryCreation
    if not panel then return end
    entryCreationKeyState.lfgEntryCreationKeyCapturePending = false
    _HookEntryCreationKeyCapture(panel)
end

_SetupLFGEntryCreationHooks = function()
    if lfgEntryCreationHookState.hooksSetup then
        if _G.LFGListFrame and _G.LFGListFrame.EntryCreation then
            entryCreationKeyState.QueueLFGEntryCreationKeyCapture()
        end
        return true
    end
    if lfgEntryCreationHookState.hookError then return false end

    local hook = _G.hooksecurefunc
    if type(hook) ~= "function"
       or type(_G.LFGListEntryCreation_Select) ~= "function"
       or type(_G.LFGListEntryCreation_Show) ~= "function"
       or type(_G.LFGListEntryCreation_SetEditMode) ~= "function" then
        return false
    end

    local ok, err = pcall(function()
        hook("LFGListEntryCreation_Select", function()
            entryCreationKeyState.QueueLFGEntryCreationKeyCapture()
        end)
        hook("LFGListEntryCreation_Show", function()
            entryCreationKeyState.QueueLFGEntryCreationKeyCapture()
        end)
        hook("LFGListEntryCreation_SetEditMode", function()
            entryCreationKeyState.QueueLFGEntryCreationKeyCapture()
        end)
        -- Re-queue can be faster than the scheduler tick. Remember the actual
        -- CreateListing call and consume it only after an active entry is
        -- confirmed; this prevents applicants from the previous queue surviving
        -- when the new listing has identical dungeon/title/comment fields.
        if C_LFGList and type(C_LFGList.CreateListing) == "function" then
            hook(C_LFGList, "CreateListing", function()
                entryCreationKeyState.listingCreatePending = true
                lastSnapshotHash = nil
                entryCreationKeyState.ClearQROverflowTransport("listing-create")
                MarkDirty("listing-create")
            end)
        end
    end)
    if not ok then
        lfgEntryCreationHookState.hookError = tostring(err)
        if KeystoneLensBridgeDB and KeystoneLensBridgeDB.debug then
            print("|cff999999[KL-debug]|r LFG key capture hook failed: "
                  .. lfgEntryCreationHookState.hookError)
        end
        return false
    end

    lfgEntryCreationHookState.hooksSetup = true
    if _G.LFGListFrame and _G.LFGListFrame.EntryCreation then
        entryCreationKeyState.QueueLFGEntryCreationKeyCapture()
    end
    return true
end

-- Minimal pause/resume controller. `/kl off` is intentionally not a permanent
-- configuration switch: it stops applicant capture and ends the current
-- transport session, then waits for a later NEW active LFG listing. This gives
-- the group leader a one-command "group is full" stop without having to remember
-- to re-enable the addon before the next key.
entryCreationKeyState.ClearAutoResumeState = function()
    if not KeystoneLensBridgeDB then return end
    KeystoneLensBridgeDB.autoResumePending = false
    KeystoneLensBridgeDB.pausedListingSignature = ""
    KeystoneLensBridgeDB.pausedSawNoListing = false
end

entryCreationKeyState.CaptureAutoPauseReason = function()
    local groupCount = math.floor(SafeNumber(
        GetNumGroupMembers and GetNumGroupMembers(), 0
    ))
    local inRaid = false
    if IsInRaid then
        local ok, value = pcall(IsInRaid)
        inRaid = ok and value and true or false
    end

    local challengeActive = false
    if C_ChallengeMode and type(C_ChallengeMode.IsChallengeModeActive) == "function" then
        local ok, value = pcall(C_ChallengeMode.IsChallengeModeActive)
        challengeActive = ok and value and true or false
    end

    local inPartyInstance = false
    if IsInInstance then
        local ok, inInstance, instanceType = pcall(IsInInstance)
        inPartyInstance = ok and inInstance and instanceType == "party" or false
    end

    return CapturePolicy.PauseReason(
        groupCount, inRaid, challengeActive, inPartyInstance
    )
end

entryCreationKeyState.CurrentListingResumeSignature = function()
    if IsChatMessagingLockdown() then return nil, false end
    if not C_LFGList.HasActiveEntryInfo() then return "", true end
    local entry = SafeTable(C_LFGList.GetActiveEntryInfo())
    if not entry then return nil, false end
    local activityIDs = SafeTable(entry.activityIDs)
    local activityID = math.floor(SafeNumber(
        activityIDs and activityIDs[1] or entry.activityID, 0))
    local questID = math.floor(SafeNumber(entry.questID, 0))
    local categoryID = math.floor(SafeNumber(entry.categoryID, 0))
    local name = SafeStr(entry.name, "")
    local comment = SafeStr(entry.comment, "")
    return table.concat({
        tostring(activityID), tostring(questID), tostring(categoryID), name, comment,
    }, "\031"), true
end

entryCreationKeyState.MaybeAutoResumeForListing = function(reason)
    if not KeystoneLensBridgeDB
       or KeystoneLensBridgeDB.enabled
       or not KeystoneLensBridgeDB.autoResumePending then
        return false
    end
    -- A viewer/show event must never restart screenshot transport while the
    -- party is still full or while the player is inside/running the dungeon.
    if entryCreationKeyState.CaptureAutoPauseReason() then
        return false
    end
    local signature, readable = entryCreationKeyState.CurrentListingResumeSignature()
    if not readable then return false end
    if signature == "" then
        KeystoneLensBridgeDB.pausedSawNoListing = true
        return false
    end
    local pausedSignature = KeystoneLensBridgeDB.pausedListingSignature or ""
    local explicitNewListing = entryCreationKeyState.listingCreatePending == true
    local resumedAcrossReload =
        (reason == "login" or reason == "world") and signature ~= pausedSignature
    -- Opening the Application Viewer is an explicit signal that the leader is
    -- actively looking at applicants again. Resume even if Blizzard kept the
    -- same active-entry signature while the group was full/paused.
    local reopenedApplicantViewer = reason == "viewer"
    if KeystoneLensBridgeDB.pausedSawNoListing
       or pausedSignature == ""
       or explicitNewListing
       or resumedAcrossReload
       or reopenedApplicantViewer then
        entryCreationKeyState.ClearAutoResumeState()
        _SetEnabled(true)
        MarkDirty("auto-resume:" .. tostring(reason or "listing"))
        APSPrint("nieuwe LFG-listing gedetecteerd — automatisch weer ingeschakeld")
        return true
    end
    return false
end

-- `/kl off` should stay quiet while the current group is full, but the addon
-- must wake up without another command when the leader deliberately opens the
-- applicant viewer again. Hooking OnShow is read-only and does not click,
-- invite, decline or modify Blizzard's Group Finder UI.
local applicationViewerResumeHooked = false
local function _SetupApplicationViewerResumeHook()
    if applicationViewerResumeHooked then return true end
    local lfgFrame = _G.LFGListFrame
    local viewer = lfgFrame and lfgFrame.ApplicationViewer
    if not viewer or type(viewer.HookScript) ~= "function" then return false end
    viewer:HookScript("OnShow", function()
        if not KeystoneLensBridgeDB
           or KeystoneLensBridgeDB.enabled
           or not KeystoneLensBridgeDB.autoResumePending then
            return
        end
        C_Timer.After(0, function()
            entryCreationKeyState.MaybeAutoResumeForListing("viewer")
        end)
    end)
    applicationViewerResumeHooked = true
    return true
end

local EVENT_HANDLERS = {
    PLAYER_LOGIN                     = function()
        InitDB()
        entryCreationKeyState.RefreshInteractionTypeMappings()
        MarkDirty("login")
        -- KeystoneLens is transport-only: no chat greetings, listing-form
        -- mutation, settings chrome, or Blizzard-frame movement.
        _SetupLFGEntryCreationHooks() -- read/capture-only host-key fallback
        _SetupApplicationViewerResumeHook()
        _TryHookInfoPanels()      -- initial track; ADDON_LOADED/ticker catches LoD frames later
        C_Timer.After(1.0, function()
            entryCreationKeyState.MaybeAutoResumeForListing("login")
        end)
    end,
    PLAYER_ENTERING_WORLD            = function()
        entryCreationKeyState.ResetInteractionSlotsForWorldTransition()
        entryCreationKeyState.ClearRosterLoadRetryState()
        CreateQRFrame()
        entryCreationKeyState.RequestLeaderKeystone(true)
        -- Recover a lease interrupted by /reload. The next actual capture
        -- reacquires lossless PNG immediately before Screenshot().
        entryCreationKeyState.screenshotController:RestoreScreenshotCVars(false)
        MarkDirty("pew")
        C_Timer.After(1.0, function()
            entryCreationKeyState.MaybeAutoResumeForListing("world")
        end)
    end,
    PLAYER_INTERACTION_MANAGER_FRAME_SHOW =
        entryCreationKeyState.OnPlayerInteractionManagerEvent,
    PLAYER_INTERACTION_MANAGER_FRAME_HIDE =
        entryCreationKeyState.OnPlayerInteractionManagerEvent,
    SCREENSHOT_STARTED                = entryCreationKeyState.OnScreenshotEvent,
    SCREENSHOT_SUCCEEDED              = entryCreationKeyState.OnScreenshotEvent,
    SCREENSHOT_FAILED                 = entryCreationKeyState.OnScreenshotEvent,
    -- WHY register ADDON_LOADED globally: many info-panel frames live in
    -- LoD addons (Blizzard_AchievementUI, Blizzard_EncounterJournal, etc.).
    -- They don't exist at PLAYER_LOGIN. Re-scan on every ADDON_LOADED catches
    -- each as its addon loads. Cost: ~10-15 fires per session × 12-frame
    -- iteration = microseconds.
    ADDON_LOADED                     = function(_, loadedAddonName)
        if loadedAddonName == addonName then
            -- SavedVariables are available when this addon's ADDON_LOADED fires.
            -- Normalize them before any setup or transport path can read the DB.
            InitDB()
        end
        _SetupLFGEntryCreationHooks()
        _SetupApplicationViewerResumeHook()
        _TryHookInfoPanels()
        entryCreationKeyState.RequestLeaderKeystone(false)
    end,
    PLAYER_LOGOUT                    = function()
        entryCreationKeyState.screenshotCVarLeaseGeneration =
            (entryCreationKeyState.screenshotCVarLeaseGeneration or 0) + 1
        entryCreationKeyState.screenshotController:RestoreScreenshotCVars(true)
        _SaveQRFramePositionFromFrame()
    end,
    PARTY_LEADER_CHANGED             = function()
        entryCreationKeyState.ClearLeaderKeystone()
        entryCreationKeyState.RequestLeaderKeystone(true)
        MarkDirty("ldrchg")
    end,
    GROUP_ROSTER_UPDATE              = function()
        entryCreationKeyState.ReconcileRosterInspectMembership()
        entryCreationKeyState.MarkRosterCompositionChanged()
        MarkDirty("roster")
        entryCreationKeyState.RequestLeaderKeystone(false)
    end,
    -- Blizzard's own Group Finder UI listens to these events. KeystoneLens uses
    -- them only as clean dirty-signals; it deliberately ignores event payloads
    -- and reads one fresh authoritative snapshot on the scheduler tick.
    LFG_LIST_ACTIVE_ENTRY_UPDATE       = function()
        entryCreationKeyState.MaybeAutoResumeForListing("listing-event")
        MarkDirty("listing")
    end,
    LFG_LIST_APPLICANT_LIST_UPDATED    = function() MarkDirty("apps") end,
    LFG_LIST_APPLICANT_UPDATED         = function() MarkDirty("app") end,
    GROUP_LEFT                       = function()
        entryCreationKeyState.AdvanceGroupTransportGeneration()
        entryCreationKeyState.ClearLeaderKeystone()
        entryCreationKeyState.MarkRosterCompositionChanged()
        MarkDirty("groupleft")
    end,
    CHAT_MSG_ADDON                  = function(_, prefix, msg, channel, sender)
        entryCreationKeyState.LibKeystoneShimHandleAddonMessage(prefix, msg, channel, sender)
    end,
    PLAYER_SPECIALIZATION_CHANGED      = function(_, unit)
        _InvalidateRosterSpecCacheForUnit(unit)
        entryCreationKeyState.ClearRosterLoadRetryState()
        MarkDirty("spec")
    end,
    PLAYER_REGEN_ENABLED              = function()
        if entryCreationKeyState.leaderKeystoneContextCombatDeferred then
            entryCreationKeyState.leaderKeystoneContextCombatDeferred = false
            if entryCreationKeyState.CleanUnitAPIBoolean(IsInGroup) == true then
                entryCreationKeyState.RequestLeaderKeystone(true)
                MarkDirty("leaderkey")
            end
        end
        if entryCreationKeyState.rosterInspectBatchCombatDeferred then
            entryCreationKeyState.ClearRosterLoadRetryState()
            entryCreationKeyState.rosterInspectBatchCombatDeferred = false
            entryCreationKeyState.rosterInspectBatchLastBlockReason = nil
            if not entryCreationKeyState.FlushOrContinueRosterInspectBatch() then
                MarkDirty("inspect")
            end
        end
    end,
    INSPECT_READY                    = function(_, guid)
        if _OnRosterInspectReady(guid) then
            entryCreationKeyState.ClearRosterLoadRetryState()
        end
    end,
}


-- Bind every interaction event to _OnInteractionEvent.
-- The frame passes the event name as the first argument, so per-event proxy
-- closures add no state.
for evt in pairs(INTERACTION_EVENTS) do
    EVENT_HANDLERS[evt] = _OnInteractionEvent
end

local frame = CreateFrame("Frame")
for event in pairs(EVENT_HANDLERS) do frame:RegisterEvent(event) end
frame:SetScript("OnEvent", function(_, event, ...)
    local h = EVENT_HANDLERS[event]
    if h then h(event, ...) end
end)

-- Scheduler ticker. Relevant Blizzard LFG events only flip scanDirty; the
-- authoritative C_LFGList read happens here outside the event callback. A slow
-- recovery poll remains for missed/late events and companion-start-mid-listing.
-- CheckSessionTransition handles StartSession/EndSession lifecycle;
-- MaybeTriggerScreenshot does the rest (read C_LFGList, build payload, paint QR,
-- trigger Screenshot()).
-- Lockdown short-circuit: skip scheduler-driven C_LFGList reads during
-- ChatMessagingLockdown. An already-running recruitment session may remain
-- alive briefly from roster state, but roster-only transport can no longer
-- start or keep normal screenshot capture alive after delisting.
C_Timer.NewTicker(0.25, function()
    local now = GetTime()
    -- Recruitment capture has a hard lifecycle boundary. Once the five-player
    -- party is complete or the player is inside/running the dungeon, stop
    -- scheduling new QR paints/screenshots. This check runs before dirty/poll
    -- draining so a roster or challenge-mode event cannot squeeze in one more
    -- capture after the boundary.
    if KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled then
        local pauseReason = entryCreationKeyState.CaptureAutoPauseReason()
        if pauseReason then
            _PauseUntilNextListing(pauseReason, false)
            return
        end
    end
    if KeystoneLensBridgeDB
       and not KeystoneLensBridgeDB.enabled
       and KeystoneLensBridgeDB.autoResumePending
       and now - (entryCreationKeyState.autoResumeLastPollAt or 0) >= 1.0 then
        entryCreationKeyState.autoResumeLastPollAt = now
        entryCreationKeyState.MaybeAutoResumeForListing("pause-poll")
    end
    entryCreationKeyState.RecoverStalledQRTransport(now)
    _TryHookInfoPanels()
    _SetupApplicationViewerResumeHook()
    _RecomputeInteractionSuppression()
    entryCreationKeyState.ProcessLFGEntryCreationDeferredWork()
    local lfgReadsAllowed = not IsChatMessagingLockdown()
    if not (scanDirty and KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled) then
        -- Drain pending throttled shot: data was changed during throttle
        -- window (pendingShotDirty=true), but no new events fired since.
        -- Without this drain: shot never goes out for sustained state.
        if pendingShotDirty
           and (now - lastShotTime) >= entryCreationKeyState.SHOT_THROTTLE_S then
            local transportReady = lfgReadsAllowed or _HasGroupRosterForTransport() or isSessionActive
            if transportReady then
                MaybeTriggerScreenshot(false, nil, nil, lfgReadsAllowed)
            end
        end
        if KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled
           and (now - lastTransportPollTime)
               >= entryCreationKeyState.TRANSPORT_POLL_S then
            lastTransportPollTime = now
            local entry = CheckSessionTransition(lfgReadsAllowed)
            if isSessionActive then
                MaybeTriggerScreenshot(false, entry, nil, lfgReadsAllowed)
            end
        end
        return
    end
    lastTransportPollTime = now
    scanDirty = false
    -- CheckSessionTransition starts/ends session as needed AND returns the
    -- live entry; pass it to MaybeTriggerScreenshot so we don't re-call
    -- C_LFGList.GetActiveEntryInfo a second time in the same tick.
    local entry = CheckSessionTransition(lfgReadsAllowed)
    local transportReady = lfgReadsAllowed or _HasGroupRosterForTransport() or isSessionActive
    if transportReady then
        MaybeTriggerScreenshot(false, entry, nil, lfgReadsAllowed)
    end
end)


-- ───────────────────────────────────────────────────────────
-- Runtime controls. The release bridge intentionally has no in-game settings
-- panel; normal users configure the desktop companion instead.

local function _RunDisabledCleanup(emitTerminalClear)
    if emitTerminalClear == nil then emitTerminalClear = true end
    local wasSessionActive = isSessionActive
    local restoreSessionGen = nil
    if wasSessionActive then
        EndSession(emitTerminalClear)
        restoreSessionGen = sessionGen
    end

    KeystoneLensBridgeDB.enabled = false
    entryCreationKeyState.AdvanceGroupTransportGeneration()
    entryCreationKeyState.ClearLeaderKeystone()
    scanDirty = false
    pendingShotDirty = false

    if not entryCreationKeyState.TerminalClearOwnsTransport() then
        entryCreationKeyState.ClearPendingForcedScreenshot()
        if not entryCreationKeyState.screenshotController:IsWaitingResult() then
            entryCreationKeyState.qrPaintJobGen =
                (entryCreationKeyState.qrPaintJobGen or 0) + 1
            entryCreationKeyState.ClearQRTransportJob()
            qrForceVisibleShotGen = (qrForceVisibleShotGen or 0) + 1
            qrForceVisibleForShot = false
            if qrFrame then qrFrame:SetFrameStrata("DIALOG") end
        end
    end

    entryCreationKeyState.SetQRAlwaysVisible(false)
    qrMoveMode = false
    _RefreshQRMouse()
    _RefreshQRVisibility()
    entryCreationKeyState.RestoreScreenshotCVarsWhenSafe(
        wasSessionActive
            and entryCreationKeyState.DISABLE_CVAR_RESTORE_AFTER_CLEAR_DELAY_S
            or 0,
        restoreSessionGen
    )
end

_SetEnabled = function(flag)
    flag = not not flag
    if flag == KeystoneLensBridgeDB.enabled then
        if not flag then _RunDisabledCleanup() end
        APSPrint(flag and "already enabled" or "already disabled")
        return
    end
    if flag then
        entryCreationKeyState.ClearAutoResumeState()
        KeystoneLensBridgeDB.enabled = true
        scanDirty = true
        APSPrint("enabled — will emit during LFG hosting")
    else
        entryCreationKeyState.ClearAutoResumeState()
        _RunDisabledCleanup()
        APSPrint("disabled (no scans, no emits)")
    end
end

_PauseUntilNextListing = function(reason, emitTerminalClear)
    InitDB()
    local signature, readable = entryCreationKeyState.CurrentListingResumeSignature()
    KeystoneLensBridgeDB.autoResumePending = true
    KeystoneLensBridgeDB.pausedListingSignature = readable and (signature or "") or ""
    KeystoneLensBridgeDB.pausedSawNoListing = readable and signature == "" or false
    _RunDisabledCleanup(emitTerminalClear)
    if reason == "party-full" then
        APSPrint("groep vol — screenshottransport gepauzeerd tot de volgende recruitment")
    elseif reason == "dungeon-active" then
        APSPrint("dungeon actief — screenshottransport gepauzeerd tot de volgende recruitment")
    else
        APSPrint("gestopt voor deze groep — automatisch AAN bij nieuwe listing of opnieuw openen van applicants")
    end
end

_SetDebug = function(flag)
    flag = not not flag
    KeystoneLensBridgeDB.debug = flag
    APSPrint("debug " .. (flag and "ON — every scan/emit will print" or "OFF"))
end

entryCreationKeyState.ToggleQRMoveMode = function()
    qrMoveMode = not qrMoveMode
    _RefreshQRMouse()
    _RefreshQRVisibility()
    APSPrint("QR move mode: " .. tostring(qrMoveMode) ..
             (qrMoveMode and " — Alt+drag the QR frame to reposition" or ""))
    return qrMoveMode
end

entryCreationKeyState.ResetQRPositionForSupport = function()
    _ResetQRFramePosition()
    local position = _CurrentQRPositionText()
    APSPrint("QR position reset: " .. position)
    return position
end

entryCreationKeyState.RequestForcedSnapshot = function()
    if not (KeystoneLensBridgeDB and KeystoneLensBridgeDB.enabled) then
        APSPrint("forced snapshot skipped — enable KeystoneLens Bridge first")
        return false, "disabled"
    end
    if not qrFrameCreated then
        APSPrint("forced snapshot skipped — QR frame unavailable; /reload and retry")
        return false, "qr-frame-unavailable"
    end
    local lfgReadsAllowed = not IsChatMessagingLockdown()
    local entry = CheckSessionTransition(lfgReadsAllowed)
    MaybeTriggerScreenshot(true, entry, nil, lfgReadsAllowed)
    APSPrint("forced snapshot requested — check Screenshots/ folder")
    return true, "requested"
end

-- ───────────────────────────────────────────────────────────
-- slash commands

entryCreationKeyState.PrintTroubleshootingStatus = function()
    print("|cff5da8ffKeystoneLens Bridge|r status:")
    print("  enabled: " .. tostring(KeystoneLensBridgeDB.enabled))
    print("  session active: " .. tostring(isSessionActive))
    print("  session gen: " .. tostring(sessionGen))
    print("  scanDirty: " .. tostring(scanDirty))
    print("  group members: "
          .. tostring(math.floor(SafeNumber(GetNumGroupMembers and GetNumGroupMembers(), 0))))
    print("  transport poll age: "
          .. (lastTransportPollTime > 0
               and string.format("%.1fs", GetTime() - lastTransportPollTime)
               or "never"))
    print("  shot suppressed: " .. (suppressShotsUntil and suppressShotsUntil > 0
          and (GetTime() < suppressShotsUntil
               and string.format("yes (%.2fs left)", suppressShotsUntil - GetTime())
               or "no (window expired)")
          or "no"))
    local lfgReadsAllowed = not IsChatMessagingLockdown()
    print("  ChatMessagingLockdown: " .. tostring(not lfgReadsAllowed))
    print("  leader key request: "
          .. tostring(entryCreationKeyState.leaderKeystoneLastRequestStatus or "never"))
    print("  LibKS send: "
          .. tostring(entryCreationKeyState.libKeystoneLastSendStatus or "never"))
    -- QR transport diagnostics
    print("|cff00ff7f---|r QR transport:")
    print("  QR library loaded: " .. tostring(_qrencode ~= nil))
    print("  QR frame created: " .. tostring(qrFrameCreated))
    if qrFrame then
        print("  QR frame visible: " .. tostring(qrFrame:IsShown()) ..
              " (always-visible mode: " .. tostring(qrAlwaysVisible) ..
              ", move mode: " .. tostring(qrMoveMode) .. ")")
        print(string.format(
            "  QR frame size: %.2f×%.2f UI units (modules are physical-pixel snapped)",
            qrCurrentSize,
            qrCurrentSize
        ))
        print("  QR frame position: " .. _CurrentQRPositionText())
        print("  QR mouse enabled: " .. tostring(qrMoveMode and true or false))
    end
    print("  QR force-visible shot lease: " .. tostring(qrForceVisibleForShot or false))
    print("  QR transport phase: " .. tostring(entryCreationKeyState.screenshotController:GetPhase()))
    print("  QR build/paint active: " .. tostring(entryCreationKeyState.qrPaintInProgress))
    print("  QR capture settle active: " .. tostring(entryCreationKeyState.qrCaptureInProgress))
    print("  screenshot result pending: "
          .. tostring(entryCreationKeyState.screenshotAwaitingResult))
    print("  last screenshot result: "
          .. tostring(entryCreationKeyState.screenshotLastResult or "never"))
    print("  screenshot failure attempts: "
          .. tostring(entryCreationKeyState.screenshotFailureAttemptCount or 0)
          .. "/" .. tostring(entryCreationKeyState.SCREENSHOT_FAILURE_MAX_ATTEMPTS))
    print("  QR job generation: " .. tostring(entryCreationKeyState.qrPaintJobGen or 0))
    print("  QR job age: " .. (entryCreationKeyState.qrTransportJobStartedAt
          and string.format("%.1fs", GetTime() - entryCreationKeyState.qrTransportJobStartedAt)
          or "idle"))
    print("  QR dirty during job: " .. tostring(entryCreationKeyState.qrPaintDirtyDuringPaint))
    print("  QR watchdog recoveries: "
          .. tostring(entryCreationKeyState.qrTransportRecoveryCount or 0)
          .. " (last: "
          .. tostring(entryCreationKeyState.qrTransportLastRecoveryReason or "never")
          .. ")")
    print("  texture pool: " .. #qrTexturePool
          .. " (used last paint: " .. qrTextureUsed
          .. ", visible high-water: "
          .. tostring(entryCreationKeyState.qrTextureVisibleHighWater or 0) .. ")")
    print("  last snapshot hash: " .. tostring(lastSnapshotHash))
    print("  last delivery snapshot hash: "
          .. tostring(entryCreationKeyState.lastDeliverySnapshotHash))
    print("  last delivery snapshot sends: "
          .. tostring(entryCreationKeyState.lastDeliverySnapshotSendCount or 0)
          .. "/" .. tostring(entryCreationKeyState.NONTERMINAL_SNAPSHOT_MIN_SENDS))
    local overflowState = entryCreationKeyState.qrOverflowState
    if overflowState then
        print(string.format(
            "  overflow transport: fragmented stream=%u generation=%u frame=%d/%d pass=%d/%d queued-newer=%s bytes=%d",
            overflowState.streamID,
            overflowState.generation,
            overflowState.chunkIndex + 1,
            overflowState.chunkCount,
            overflowState.pass,
            entryCreationKeyState.QR_OVERFLOW_MIN_SENDS,
            tostring(overflowState.queuedNewer == true),
            overflowState.logicalBytes
        ))
    else
        print("  overflow transport: idle")
    end
    print("  overflow superseded generations: "
          .. tostring(entryCreationKeyState.qrOverflowSupersededCount or 0))
    print("  overflow last failure: "
          .. tostring(entryCreationKeyState.qrOverflowLastFailure or "none"))
    print("  last logical payload: "
          .. tostring(entryCreationKeyState.lastPayloadTotalBytes or 0)
          .. " bytes (error: "
          .. tostring(entryCreationKeyState.lastPayloadBuildError or "none") .. ")")
    print("  last shot time: " .. (lastShotTime > 0
          and string.format("%.1fs ago", GetTime() - lastShotTime) or "never"))
    print("  pending throttled shot: " .. tostring(pendingShotDirty))
    entryCreationKeyState.PrintRosterInspectBatchDiagnostics()
    print("  last QR encode: " .. tostring(lastQREncodeMode)
          .. " (" .. tostring(lastQREncodeBytes) .. " bytes)")
    print("  last QR error: " .. tostring(lastQREncodeError or "none"))
    print("  screenshotQuality: " .. tostring(GetCVar("screenshotQuality")))
    print("  screenshotFormat: " .. tostring(GetCVar("screenshotFormat")))
    print("  prior screenshotQuality stash: " ..
          tostring(KeystoneLensBridgeDB.priorScreenshotQuality))
    print("  prior screenshotFormat stash: " ..
          tostring(KeystoneLensBridgeDB.priorScreenshotFormat))
    -- raw API diagnostics
    print("|cff00ff7f---|r raw API:")
    if lfgReadsAllowed then
    print("  HasActiveEntryInfo: " .. tostring(C_LFGList.HasActiveEntryInfo()))
    local entry = SafeTable(C_LFGList.GetActiveEntryInfo())
    if entry then
        local activityIDs = SafeTable(entry.activityIDs)
        local cleanActivityID = math.floor(SafeNumber(activityIDs and activityIDs[1], 0))
        if cleanActivityID <= 0 then
            cleanActivityID = math.floor(SafeNumber(entry.activityID, 0))
        end
        local cleanQuestID = math.floor(SafeNumber(entry.questID, 0))
        local statusActivityInfo =
            _GetActivityInfoForListing(cleanActivityID, cleanQuestID)
        local statusDungeonName = _ActivityInfoListingName(statusActivityInfo)
        print("  entry.activityIDs[1]: " .. SafeDiag(activityIDs and activityIDs[1]))
        print("  entry.activityID: " .. SafeDiag(entry.activityID))
        print("  entry.questID: " .. SafeDiag(entry.questID))
        if cleanActivityID > 0 then
            if statusActivityInfo then
                print("  activity.name: " .. statusDungeonName)
                print("  activity.shortName: " .. SafeDiag(statusActivityInfo.shortName))
                print("  activity.fullName: " .. SafeDiag(statusActivityInfo.fullName))
                print("  activity.categoryID: " .. SafeDiag(statusActivityInfo.categoryID))
                print("  activity.difficultyID: " .. SafeDiag(statusActivityInfo.difficultyID))
            end
            if C_LFGList.GetKeystoneForActivity then
                print("  activity.keystoneLevel: "
                      .. SafeDiag(C_LFGList.GetKeystoneForActivity(cleanActivityID)))
            else
                print("  activity.keystoneLevel: n/a")
            end
        end
        print("  entry.name: " .. SafeDiag(entry.name))
        print("  entry.comment: " .. SafeDiag(entry.comment))
        print("  visibleFrame.keyLevel: "
              .. tostring(_GetVisibleApplicationViewerKeystoneLevel()))
        local visibleDiagnostics = _GetVisibleApplicationViewerKeystoneDiagnostics()
        for _, line in ipairs(visibleDiagnostics) do
            print(line)
        end
        local cachedKeyLevel =
            entryCreationKeyState.PeekCachedEntryCreationKeystoneLevel(
                cleanActivityID, cleanQuestID)
        print("  entryCreationCache.keyLevel: " .. tostring(cachedKeyLevel))
        local statusListingName = SafeStr(entry.name, "?")
        local statusListingComment = SafeStr(entry.comment, "?")
        local ownedActivityID, ownedGroupID, ownedLevel, ownedInfo =
            _GetOwnedKeystoneListingInfo()
        print("  ownedKeystone.activityID: " .. tostring(ownedActivityID))
        print("  ownedKeystone.groupID: " .. tostring(ownedGroupID))
        print("  ownedKeystone.level: " .. tostring(ownedLevel))
        print("  ownedKeystone.activityName: " .. _ActivityInfoListingName(ownedInfo))
        local statusUseOwned = ownedLevel > 0
            and ownedActivityID > 0
            and ownedInfo
            and entryCreationKeyState.CanUseOwnedKeystoneForListingFallback()
            and (ownedActivityID == cleanActivityID
                or statusDungeonName == "Mythic+"
                or statusDungeonName == "?")
        print("  ownedKeystone.usedForListing: " .. tostring(statusUseOwned))
        local statusDerivedKeyLevel = _GetListingKeystoneLevel(
            cleanActivityID,
            cleanQuestID,
            statusListingName,
            statusListingComment,
            statusActivityInfo)
        if statusDerivedKeyLevel == 0 and statusUseOwned then
            statusDerivedKeyLevel = ownedLevel
        end
        print("  derived keyLevel: "
              .. tostring(statusDerivedKeyLevel))
    else
        print("  entry: nil")
    end
    local applicants = SafeTable(C_LFGList.GetApplicants()) or {}
    print("  GetApplicants count: " .. #applicants)
    for i = 1, math.min(3, #applicants) do
        local rawID = applicants[i]
        local id, info = entryCreationKeyState.GetApplicantInfoForTransport(rawID)
        if info then
            print(string.format("    #%d id=%s status=%s numMembers=%s",
                  i, SafeDiag(id), SafeDiag(_GetApplicantApplicationStatus(info)),
                  SafeDiag(info.numMembers)))
        else
            print(string.format("    #%d id=%s status=n/a numMembers=n/a",
                  i, SafeDiag(rawID)))
        end
    end
    else
        print("  raw API skipped during ChatMessagingLockdown")
    end
    print("|cff00ff7f---|r host key capture:")
    entryCreationKeyState.PrintDiagnostics()
    print("|cff00ff7f---|r visibility:")
    print("  QR suppressed by interaction: " .. tostring(_qrSuppressedByInteraction or false))
    local activeKinds = {}
    for kind, active in pairs(_interactionSlots) do
        if active then activeKinds[#activeKinds + 1] = tostring(kind) end
    end
    print("  active interaction slots: " .. (#activeKinds > 0
          and table.concat(activeKinds, ", ") or "(none)"))
    local trackedCount = 0
    for _ in pairs(_trackedInfoPanels) do trackedCount = trackedCount + 1 end
    print("  info panels tracked: " .. trackedCount .. "/" .. #INFO_PANEL_FRAMES)
end

local function PrintPublicStatus()
    local pending = KeystoneLensBridgeDB.autoResumePending and not KeystoneLensBridgeDB.enabled
    print("|cff5da8ffKeystoneLens Bridge v" .. ADDON_VERSION .. "|r")
    print("  status: " .. (KeystoneLensBridgeDB.enabled and "AAN" or "UIT"))
    print("  huidige sessie: " .. (isSessionActive and "actief" or "inactief"))
    print("  auto-start LFG hervatten: " .. (pending and "JA" or "NEE"))
    print("  laatste applicants in payload: " .. tostring(entryCreationKeyState.lastPayloadApplicantCount or 0))
end

local function QueuePublicResync()
    if not KeystoneLensBridgeDB.enabled then
        APSPrint("sync overgeslagen — gebruik eerst /kl on")
        return
    end
    lastSnapshotHash = nil
    pendingShotDirty = false
    entryCreationKeyState.ClearScreenshotFailureState()
    entryCreationKeyState.lastQuietFullPartySignature = nil
    entryCreationKeyState.lastPayloadQuietFullPartySignature = nil
    entryCreationKeyState.MarkRosterCompositionChanged()
    entryCreationKeyState.ClearRosterInspectBatchState()
    entryCreationKeyState.ClearRosterInspectFailureState()
    entryCreationKeyState.ResetInteractionSlotsForWorldTransition()
    scanDirty = true
    APSPrint("sync queued — nieuwe snapshot wordt gemaakt zodra transport beschikbaar is")
end

local function PrintHelp()
    print("|cff5da8ffKeystoneLens Bridge v" .. ADDON_VERSION .. "|r")
    print("  /kl off | stop   stop nu; auto-start bij nieuwe listing of opnieuw openen LFG")
    print("  /kl on           direct weer inschakelen")
    print("  /kl status       korte status")
    print("  /kl sync         huidige listing opnieuw synchroniseren")
    print("  /kl help         deze commands")
end

SLASH_KEYSTONELENSBRIDGE1 = "/kl"
SlashCmdList.KEYSTONELENSBRIDGE = function(msg)
    InitDB()
    msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    if msg == "on" then
        _SetEnabled(true)
    elseif msg == "off" or msg == "stop" then
        _PauseUntilNextListing()
    elseif msg == "status" then
        PrintPublicStatus()
    elseif msg == "sync" then
        QueuePublicResync()
    elseif msg == "help" or msg == "" then
        PrintHelp()
    else
        APSPrint("onbekend command: " .. tostring(msg))
        PrintHelp()
    end
end

