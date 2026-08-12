-- KeystoneLens screenshot transport controller.
--
-- Owns the capture lifecycle and screenshot-specific CVar leasing.
-- Transport.lua is responsible for building/painting QR data; this module keeps
-- the asynchronous Screenshot() state machine explicit and serialised:
--   IDLE -> BUILDING -> SETTLING -> WAITING_RESULT -> IDLE
--
-- SCREENSHOT_* events have no request id, so there may only be one physical
-- capture in flight. Legacy fields on the shared transport state are mirrored
-- for /kl status and compatibility with older guard code.

local _, KL = ...
if type(KL) ~= "table" then return end

local Controller = {}
Controller.__index = Controller

local PHASE_IDLE = "IDLE"
local PHASE_BUILDING = "BUILDING"
local PHASE_SETTLING = "SETTLING"
local PHASE_WAITING = "WAITING_RESULT"
local PHASE_PAINT_FAILED = "PAINT_FAILED"

local function SafeInteger(value, default)
    local n = tonumber(value)
    if not n or n ~= n or n == math.huge or n == -math.huge then
        return default
    end
    return math.floor(n)
end

function Controller:New(state, printFn)
    local obj = setmetatable({}, self)
    obj.state = state
    obj.printFn = printFn
    obj.phase = PHASE_IDLE
    obj.jobGen = nil
    obj.terminalClear = false
    obj.startedAt = nil
    obj.dirtyDuringJob = false
    obj.superseded = false
    obj.resultHandler = nil
    obj:_SyncLegacy()
    return obj
end

function Controller:_SyncLegacy()
    local state = self.state
    if type(state) ~= "table" then return end
    state.qrTransportPhase = self.phase
    state.qrPaintInProgress = self.phase == PHASE_BUILDING
    state.qrCaptureInProgress = self.phase == PHASE_SETTLING
        or self.phase == PHASE_WAITING
    state.qrPaintDirtyDuringPaint = self.dirtyDuringJob and true or false
    state.qrTransportJobStartedAt = self.startedAt
    state.qrTransportJobTerminalClear = self.terminalClear and true or false
    state.screenshotAwaitingResult = self.phase == PHASE_WAITING
    state.screenshotAwaitingJobGen = self.phase == PHASE_WAITING and self.jobGen or nil
    state.screenshotAwaitingSuperseded = self.superseded and true or false
    state.screenshotResultHandler = self.resultHandler
end

function Controller:BeginBuild(jobGen, terminalClear, startedAt)
    self.phase = PHASE_BUILDING
    self.jobGen = jobGen
    self.terminalClear = terminalClear and true or false
    self.startedAt = startedAt
    self.dirtyDuringJob = false
    self.superseded = false
    self.resultHandler = nil
    self:_SyncLegacy()
end

function Controller:FinishPaint(jobGen, success)
    if self.jobGen ~= jobGen then return false end
    if success then
        self.phase = PHASE_SETTLING
    else
        self.phase = PHASE_PAINT_FAILED
    end
    self:_SyncLegacy()
    return true
end

function Controller:BeginSettle(jobGen)
    if self.jobGen ~= jobGen then return false end
    self.phase = PHASE_SETTLING
    self:_SyncLegacy()
    return true
end

function Controller:ArmResult(jobGen, handler)
    if self.jobGen ~= jobGen or type(handler) ~= "function" then
        return false
    end
    self.phase = PHASE_WAITING
    self.resultHandler = handler
    self:_SyncLegacy()
    return true
end

function Controller:HandleEvent(event)
    if event == "SCREENSHOT_STARTED" then
        if self.phase == PHASE_WAITING then
            self.state.screenshotLastResult = "started"
        end
        return
    end
    if self.phase ~= PHASE_WAITING or type(self.resultHandler) ~= "function" then
        return
    end
    if event == "SCREENSHOT_SUCCEEDED" then
        self.resultHandler(true, "succeeded event")
    elseif event == "SCREENSHOT_FAILED" then
        self.resultHandler(false, "failed event")
    end
end

function Controller:MarkDirty()
    self.dirtyDuringJob = true
    self:_SyncLegacy()
end

function Controller:ClearDirty()
    self.dirtyDuringJob = false
    self:_SyncLegacy()
end

function Controller:IsBusy()
    return self.phase == PHASE_BUILDING
        or self.phase == PHASE_SETTLING
        or self.phase == PHASE_WAITING
end

function Controller:IsWaitingResult()
    return self.phase == PHASE_WAITING
end

function Controller:IsCapturePhase()
    return self.phase == PHASE_SETTLING or self.phase == PHASE_WAITING
end

function Controller:GetResultHandler()
    return self.resultHandler
end

function Controller:GetPhase()
    return self.phase
end

function Controller:SupersedeWaitingResult()
    if self.phase ~= PHASE_WAITING then return false end
    self.superseded = true
    self:_SyncLegacy()
    return true
end

function Controller:IsSuperseded()
    return self.superseded and true or false
end

function Controller:Clear(jobGen)
    if jobGen and self.jobGen ~= jobGen then
        return false
    end
    self.phase = PHASE_IDLE
    self.jobGen = nil
    self.terminalClear = false
    self.startedAt = nil
    self.dirtyDuringJob = false
    self.superseded = false
    self.resultHandler = nil
    self:_SyncLegacy()
    return true
end

function Controller:EnsureScreenshotCVars(quiet)
    if not (SetCVar and GetCVar) then return end
    local db = _G.KeystoneLensBridgeDB
    if type(db) ~= "table" then return end

    local format = tostring(GetCVar("screenshotFormat") or "")
    if format:lower() ~= "png" then
        if db.priorScreenshotFormat == nil then
            db.priorScreenshotFormat = format
        end
        SetCVar("screenshotFormat", "png")
        local verifyFormat = tostring(GetCVar("screenshotFormat") or "")
        if verifyFormat:lower() ~= "png" then
            if self.printFn then
                self.printFn("WARN: screenshotFormat SetCVar didn't stick (read back " ..
                    verifyFormat .. "); QR transport expects lossless PNG")
            end
        elseif self.printFn and not quiet then
            self.printFn("temporarily set screenshotFormat=png for QR transport")
        end
    end
end

function Controller:RestoreScreenshotCVars(quiet)
    if not (SetCVar and GetCVar) then return end
    local db = _G.KeystoneLensBridgeDB
    if type(db) ~= "table" then return end

    if db.priorScreenshotQuality ~= nil then
        local prior = SafeInteger(db.priorScreenshotQuality, -1)
        local currentQuality = SafeInteger(GetCVar("screenshotQuality"), 0)
        if prior >= 1 and prior <= 10 then
            if currentQuality == 8 then
                SetCVar("screenshotQuality", tostring(prior))
                if self.printFn and not quiet then
                    self.printFn("restored screenshotQuality=" .. prior .. " (pre-KeystoneLens value)")
                end
            elseif self.printFn and not quiet then
                self.printFn("kept screenshotQuality=" .. currentQuality ..
                    " (changed after KeystoneLens forced 8)")
            end
        end
        db.priorScreenshotQuality = nil
    end

    if db.priorScreenshotFormat ~= nil then
        local rawPriorFormat = db.priorScreenshotFormat
        local priorFormat = type(rawPriorFormat) == "string" and rawPriorFormat:lower() or ""
        local currentFormat = tostring(GetCVar("screenshotFormat") or "")
        local validPriorFormat = priorFormat == "jpg"
            or priorFormat == "jpeg"
            or priorFormat == "png"
            or priorFormat == "tga"
        if validPriorFormat then
            if currentFormat:lower() == "png" then
                SetCVar("screenshotFormat", priorFormat)
                if self.printFn and not quiet then
                    self.printFn("restored screenshotFormat=" .. priorFormat ..
                        " (pre-KeystoneLens value)")
                end
            elseif self.printFn and not quiet then
                self.printFn("kept screenshotFormat=" .. currentFormat ..
                    " (changed after KeystoneLens forced png)")
            end
        end
        db.priorScreenshotFormat = nil
    end
end

function Controller:AcquireCVarLease()
    self.state.screenshotCVarLeaseGeneration =
        (self.state.screenshotCVarLeaseGeneration or 0) + 1
    local generation = self.state.screenshotCVarLeaseGeneration
    self:EnsureScreenshotCVars(true)
    return generation
end

function Controller:ReleaseCVarLease(leaseGeneration, delay)
    local function releaseIfCurrent()
        if self.state.screenshotCVarLeaseGeneration ~= leaseGeneration then
            return
        end
        self:RestoreScreenshotCVars(true)
    end
    if delay and delay > 0 and C_Timer and C_Timer.After then
        C_Timer.After(delay, releaseIfCurrent)
    else
        releaseIfCurrent()
    end
end

KL.NewScreenshotController = function(state, printFn)
    return Controller:New(state, printFn)
end
