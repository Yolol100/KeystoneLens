-- KeystoneLens transport state ownership.
-- Keeps long-lived mutable transport/QR bookkeeping out of Transport.lua so the
-- main transport chunk has more Lua 5.1 local-variable headroom.

local _, KL = ...
if type(KL) ~= "table" then return end

local State = {}

State.DB_DEFAULTS = {
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
    -- Keep the 1..255 listing-generation ring monotonic across /reload. The
    -- desktop Companion can remain running while the Bridge reloads; resetting
    -- this counter to 1 would make a fresh post-reload listing look older than
    -- the last pre-reload generation and be rejected as stale.
    listingGeneration = 0,
}

function State.New(renderSettleSeconds)
    local QR_RENDER_SETTLE_S = tonumber(renderSettleSeconds) or 0.16
    local state = {
            qrFrame = nil,
            qrTexturePool = {},
            qrTextureUsed = 0,
            qrFrameCreated = false,
            qrCurrentSize = 0,
            lfgEntryCreationHookState = { hooksSetup = false, hookError = nil },
            lfgEntryCreationKeyCaptureHooked = setmetatable({}, { __mode = "k" }),
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

    state.ClearScreenshotFailureState = function()
        state.screenshotFailureHash = nil
        state.screenshotFailureAttemptCount = 0
    end
    return state
end

KL.TransportState = State
