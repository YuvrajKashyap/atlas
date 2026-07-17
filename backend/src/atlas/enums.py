from enum import StrEnum


class CrawlRunStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FrontierStatus(StrEnum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    EXTRACTING = "extracting"
    INDEXING = "indexing"
    INDEXED = "indexed"
    RETRY_SCHEDULED = "retry_scheduled"
    ROBOTS_BLOCKED = "robots_blocked"
    DISALLOWED_DOMAIN = "disallowed_domain"
    DUPLICATE_URL = "duplicate_url"
    DUPLICATE_CONTENT = "duplicate_content"
    UNSUPPORTED_CONTENT = "unsupported_content"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FAILED = "failed"


class FetchOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    TRANSIENT_ERROR = "transient_error"
    PERMANENT_ERROR = "permanent_error"
    ROBOTS_BLOCKED = "robots_blocked"
    UNSUPPORTED_CONTENT = "unsupported_content"


class PipelineTaskType(StrEnum):
    FETCH = "fetch"
    EXTRACT = "extract"
    INDEX = "index"


class PipelineTaskStatus(StrEnum):
    READY = "ready"
    LEASED = "leased"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


class ChangeKind(StrEnum):
    INITIAL = "initial"
    UNCHANGED = "unchanged"
    METADATA_ONLY = "metadata_only"
    MINOR = "minor"
    SUBSTANTIAL = "substantial"


class ObservationOutcome(StrEnum):
    FETCHED = "fetched"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"
    ROBOTS_BLOCKED = "robots_blocked"


class IndexOperationStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"


class IndexBuildStatus(StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class IncidentStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


TERMINAL_FRONTIER_STATUSES = {
    FrontierStatus.INDEXED,
    FrontierStatus.ROBOTS_BLOCKED,
    FrontierStatus.DISALLOWED_DOMAIN,
    FrontierStatus.DUPLICATE_URL,
    FrontierStatus.DUPLICATE_CONTENT,
    FrontierStatus.UNSUPPORTED_CONTENT,
    FrontierStatus.BUDGET_EXHAUSTED,
    FrontierStatus.FAILED,
}
