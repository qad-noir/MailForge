from enum import StrEnum


class ConsentStatus(StrEnum):
    OPTED_IN = "opted_in"
    UNSUBSCRIBED = "unsubscribed"
    UNKNOWN = "unknown"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    QUEUEING = "queueing"
    QUEUED = "queued"
    SENDING = "sending"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RecipientStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    DEFERRED = "deferred"
    BOUNCED = "bounced"
    DROPPED = "dropped"
    FAILED = "failed"
    SUPPRESSED = "suppressed"
    UNSUBSCRIBED = "unsubscribed"
    SPAM_REPORT = "spam_report"
    CANCELLED = "cancelled"


class SuppressionType(StrEnum):
    UNSUBSCRIBE = "unsubscribe"
    HARD_BOUNCE = "hard_bounce"
    SPAM_REPORT = "spam_report"
    MANUAL = "manual"
    BLOCKED = "blocked"
    INVALID = "invalid"
