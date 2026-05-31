"""Data models for the background memory service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ToolCallStat:
    name: str
    count: int = 0
    total_elapsed_s: float = 0.0
    error_count: int = 0
    hang_count: int = 0

    @property
    def avg_elapsed_s(self) -> float:
        return self.total_elapsed_s / self.count if self.count else 0.0


@dataclass
class Segment:
    """One compiled time-slice of the audit log."""
    id: str
    segment_type: str           # "hourly" | "daily" | "weekly"
    start_time: datetime
    end_time: datetime
    summary: str
    event_count: int
    error_count: int
    user_messages: int
    assistant_replies: int
    tool_call_stats: list[ToolCallStat]
    child_ids: list[str]        # IDs of constituent finer-grained segments
    data_path: str              # path to JSON file with full event list
    compressed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_s(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def tool_calls_total(self) -> int:
        return sum(s.count for s in self.tool_call_stats)

    @property
    def tool_errors_total(self) -> int:
        return sum(s.error_count for s in self.tool_call_stats)


@dataclass
class AuditReadState:
    """Tracks how far through audit.log we have already compiled."""
    offset: int = 0
    file_size_at_last_read: int = 0
    last_compiled_hour: str = ""    # ISO-8601 UTC of the last hour start we compiled

    def is_rotated(self, current_size: int) -> bool:
        """True if the log was truncated/replaced since we last read it."""
        return current_size < self.offset
