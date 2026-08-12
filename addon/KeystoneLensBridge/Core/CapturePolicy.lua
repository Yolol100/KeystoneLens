-- KeystoneLens recruitment capture policy.
--
-- This module deliberately contains only pure decision logic so the transport
-- lifecycle can be tested without a running WoW client. Transport.lua is still
-- responsible for reading Blizzard APIs and performing the actual pause/resume.

local _, KL = ...
if type(KL) ~= "table" then return end

local Policy = {}

function Policy.PauseReason(groupCount, inRaid, challengeActive, inPartyInstance)
    groupCount = tonumber(groupCount) or 0
    inRaid = inRaid and true or false
    challengeActive = challengeActive and true or false
    inPartyInstance = inPartyInstance and true or false

    if challengeActive or inPartyInstance then
        return "dungeon-active"
    end
    if not inRaid and groupCount >= 5 then
        return "party-full"
    end
    return nil
end

function Policy.TransportActive(hosting, hasRoster, lfgReadsAllowed, sessionActive)
    hosting = hosting and true or false
    hasRoster = hasRoster and true or false
    lfgReadsAllowed = lfgReadsAllowed and true or false
    sessionActive = sessionActive and true or false

    if lfgReadsAllowed then
        -- Recruitment transport follows the player's active LFG listing. A
        -- party roster alone must never keep screenshot capture alive after
        -- delisting or after the group enters the dungeon.
        return hosting
    end

    -- During ChatMessagingLockdown the active listing may be unreadable. Keep
    -- an already-running session alive only long enough to avoid a false close;
    -- never start a new session solely because a roster exists.
    return sessionActive and hasRoster
end

KL.CapturePolicy = Policy
