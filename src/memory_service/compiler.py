"""Audit log reader and segment compiler.

Reads raw JSON lines from logs/audit.log and compiles them into
hourly, daily, and weekly Segment objects.

Read-state tracking
-------------------
A small JSON file (``audit_read_state.json``) in the storage directory
records the byte offset we last read to.  On the next compilation pass we
seek directly to that offset rather than re-reading the whole file.  If the
file shrinks (rotation / recreation) we fall back to reading from the start.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.memory_service.models import AuditReadState, Segment, ToolCallStat


# ---------------------------------------------------------------------------
# Audit log reader
# ---------------------------------------------------------------------------

def load_read_state(state_path: Path) -> AuditReadState:
    if not state_path.exists():
        return AuditReadState()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return AuditReadState(
            offset=data.get("offset", 0),
            file_size_at_last_read=data.get("file_size_at_last_read", 0),
            last_compiled_hour=data.get("last_compiled_hour", ""),
        )
    except Exception:
        return AuditReadState()


def save_read_state(state_path: Path, state: AuditReadState) -> None:
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "offset": state.offset,
                "file_size_at_last_read": state.file_size_at_last_read,
                "last_compiled_hour": state.last_compiled_hour,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(state_path)


def read_new_events(
    audit_log_path: Path,
    state: AuditReadState,
) -> tuple[list[dict], AuditReadState]:
    """Return all audit events written since the last read, plus updated state."""
    if not audit_log_path.exists():
        return [], state

    current_size = audit_log_path.stat().st_size

    if state.is_rotated(current_size):
        # Log was replaced or truncated — start over.
        state = AuditReadState()

    events: list[dict] = []
    new_offset = state.offset

    with open(audit_log_path, "rb") as f:
        f.seek(state.offset)
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        new_offset = f.tell()

    new_state = AuditReadState(
        offset=new_offset,
        file_size_at_last_read=current_size,
        last_compiled_hour=state.last_compiled_hour,
    )
    return events, new_state


def filter_events_in_window(
    events: list[dict],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Return only events whose 'ts' falls within [start, end)."""
    result = []
    for ev in events:
        ts_str = ev.get("ts", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if start <= ts < end:
                result.append(ev)
        except ValueError:
            pass
    return result


# ---------------------------------------------------------------------------
# Hourly compiler
# ---------------------------------------------------------------------------

def compile_hourly(
    events: list[dict],
    start: datetime,
    end: datetime,
    segment_id: str | None = None,
) -> Segment:
    """Compile a list of audit events into an hourly Segment."""
    seg_id = segment_id or f"hourly_{start.strftime('%Y%m%dT%H%M%S')}Z"

    tool_stats: dict[str, ToolCallStat] = {}
    error_count = 0
    user_messages = 0
    assistant_replies = 0
    hang_warnings = 0

    for ev in events:
        etype = ev.get("event", "")
        if etype == "tool_call":
            name = ev.get("name", "unknown")
            if name not in tool_stats:
                tool_stats[name] = ToolCallStat(name=name)
            tool_stats[name].count += 1
        elif etype == "tool_response":
            name = ev.get("name", "unknown")
            if name not in tool_stats:
                tool_stats[name] = ToolCallStat(name=name)
            elapsed = ev.get("elapsed_s", 0.0)
            tool_stats[name].total_elapsed_s += elapsed
            if ev.get("is_error"):
                tool_stats[name].error_count += 1
                error_count += 1
        elif etype == "tool_hang_warning":
            name = ev.get("name", "unknown")
            if name not in tool_stats:
                tool_stats[name] = ToolCallStat(name=name)
            tool_stats[name].hang_count += 1
            hang_warnings += 1
        elif etype == "error":
            error_count += 1
        elif etype == "user_message":
            user_messages += 1
        elif etype == "assistant_reply":
            assistant_replies += 1

    tool_list = sorted(tool_stats.values(), key=lambda s: s.count, reverse=True)

    top_tools = ", ".join(
        f"{s.name}×{s.count}" for s in tool_list[:5]
    ) or "none"
    summary_parts = [
        f"{len(events)} events",
        f"{user_messages} user msgs",
        f"{assistant_replies} replies",
        f"top tools: {top_tools}",
    ]
    if error_count:
        summary_parts.append(f"{error_count} errors")
    if hang_warnings:
        summary_parts.append(f"{hang_warnings} hang warnings")
    summary = " | ".join(summary_parts)

    return Segment(
        id=seg_id,
        segment_type="hourly",
        start_time=start,
        end_time=end,
        summary=summary,
        event_count=len(events),
        error_count=error_count,
        user_messages=user_messages,
        assistant_replies=assistant_replies,
        tool_call_stats=tool_list,
        child_ids=[],
        data_path="",   # filled in by SegmentStore.save_segment
    )


# ---------------------------------------------------------------------------
# Daily compiler (rolls up hourly segments)
# ---------------------------------------------------------------------------

def compile_daily(
    hourly_segments: list[Segment],
    date: datetime,
) -> Segment:
    """Aggregate hourly segments into a daily segment."""
    if not hourly_segments:
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        start = min(s.start_time for s in hourly_segments)
        end = max(s.end_time for s in hourly_segments)

    seg_id = f"daily_{date.strftime('%Y-%m-%d')}"

    merged: dict[str, ToolCallStat] = {}
    total_events = 0
    total_errors = 0
    total_users = 0
    total_replies = 0

    for seg in hourly_segments:
        total_events += seg.event_count
        total_errors += seg.error_count
        total_users += seg.user_messages
        total_replies += seg.assistant_replies
        for stat in seg.tool_call_stats:
            if stat.name not in merged:
                merged[stat.name] = ToolCallStat(name=stat.name)
            merged[stat.name].count += stat.count
            merged[stat.name].total_elapsed_s += stat.total_elapsed_s
            merged[stat.name].error_count += stat.error_count
            merged[stat.name].hang_count += stat.hang_count

    tool_list = sorted(merged.values(), key=lambda s: s.count, reverse=True)
    top_tools = ", ".join(f"{s.name}×{s.count}" for s in tool_list[:5]) or "none"
    summary = (
        f"{len(hourly_segments)} hours | {total_events} events | "
        f"{total_users} user msgs | {total_replies} replies | "
        f"top tools: {top_tools}"
        + (f" | {total_errors} errors" if total_errors else "")
    )

    return Segment(
        id=seg_id,
        segment_type="daily",
        start_time=start,
        end_time=end,
        summary=summary,
        event_count=total_events,
        error_count=total_errors,
        user_messages=total_users,
        assistant_replies=total_replies,
        tool_call_stats=tool_list,
        child_ids=[s.id for s in hourly_segments],
        data_path="",
    )


# ---------------------------------------------------------------------------
# Weekly compiler (rolls up daily segments)
# ---------------------------------------------------------------------------

def compile_weekly(
    daily_segments: list[Segment],
    year: int,
    week: int,
) -> Segment:
    """Aggregate daily segments into a weekly segment."""
    if not daily_segments:
        start = _week_start(year, week)
        end = start + timedelta(weeks=1)
    else:
        start = min(s.start_time for s in daily_segments)
        end = max(s.end_time for s in daily_segments)

    seg_id = f"weekly_{year}_W{week:02d}"

    merged: dict[str, ToolCallStat] = {}
    total_events = 0
    total_errors = 0
    total_users = 0
    total_replies = 0

    for seg in daily_segments:
        total_events += seg.event_count
        total_errors += seg.error_count
        total_users += seg.user_messages
        total_replies += seg.assistant_replies
        for stat in seg.tool_call_stats:
            if stat.name not in merged:
                merged[stat.name] = ToolCallStat(name=stat.name)
            merged[stat.name].count += stat.count
            merged[stat.name].total_elapsed_s += stat.total_elapsed_s
            merged[stat.name].error_count += stat.error_count
            merged[stat.name].hang_count += stat.hang_count

    tool_list = sorted(merged.values(), key=lambda s: s.count, reverse=True)
    top_tools = ", ".join(f"{s.name}×{s.count}" for s in tool_list[:5]) or "none"
    summary = (
        f"Week {week}/{year} | {len(daily_segments)} days | "
        f"{total_events} events | {total_users} user msgs | "
        f"top tools: {top_tools}"
        + (f" | {total_errors} errors" if total_errors else "")
    )

    return Segment(
        id=seg_id,
        segment_type="weekly",
        start_time=start,
        end_time=end,
        summary=summary,
        event_count=total_events,
        error_count=total_errors,
        user_messages=total_users,
        assistant_replies=total_replies,
        tool_call_stats=tool_list,
        child_ids=[s.id for s in daily_segments],
        data_path="",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _week_start(year: int, week: int) -> datetime:
    """Return UTC midnight for ISO week start (Monday)."""
    jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    return start_of_week1 + timedelta(weeks=week - 1)


def hour_boundary(dt: datetime) -> datetime:
    """Truncate dt to the start of its hour in UTC."""
    utc = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return utc.replace(minute=0, second=0, microsecond=0)
