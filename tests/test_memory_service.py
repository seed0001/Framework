"""Unit tests for the background memory service.

Covers: config loading, segment store CRUD, hourly/daily/weekly compilation,
audit log reading with offset tracking, and retention policy.
"""
from __future__ import annotations

import gzip
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.memory_service.compiler import (
    compile_daily,
    compile_hourly,
    compile_weekly,
    filter_events_in_window,
    hour_boundary,
    load_read_state,
    read_new_events,
    save_read_state,
)
from src.memory_service.config import MemoryServiceConfig
from src.memory_service.models import AuditReadState, Segment, ToolCallStat
from src.memory_service.segment_store import SegmentStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_storage(tmp_path: Path) -> Path:
    return tmp_path / "segments"


@pytest.fixture
def store(tmp_storage: Path) -> SegmentStore:
    return SegmentStore(tmp_storage)


@pytest.fixture
def t0() -> datetime:
    """Fixed UTC hour boundary for deterministic tests."""
    return datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)


def _make_events(t0: datetime, n: int = 5) -> list[dict]:
    """Generate a small realistic audit-log event list."""
    events = []
    for i in range(n):
        ts = (t0 + timedelta(minutes=i * 10)).isoformat()
        events.append({"ts": ts, "event": "user_message", "text": f"msg {i}"})
        events.append({"ts": ts, "event": "tool_call", "name": "read_file", "args": {}})
        events.append({
            "ts": ts, "event": "tool_response", "name": "read_file",
            "result": "ok", "elapsed_s": 0.05, "is_error": False,
        })
        events.append({"ts": ts, "event": "assistant_reply", "text": f"reply {i}"})
    return events


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_defaults(self, tmp_path: Path) -> None:
        cfg = MemoryServiceConfig()
        assert cfg.interval_seconds == 3600
        assert cfg.retention_hourly_days == 7

    def test_load_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text(
            "interval_seconds: 1800\nretention:\n  hourly_days: 3\n",
            encoding="utf-8",
        )
        cfg = MemoryServiceConfig.load(yaml_file)
        assert cfg.interval_seconds == 1800
        assert cfg.retention_hourly_days == 3

    def test_env_override(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("MEMORY_SERVICE_INTERVAL", "900")
        cfg = MemoryServiceConfig.load(tmp_path / "nonexistent.yaml")
        assert cfg.interval_seconds == 900


# ---------------------------------------------------------------------------
# Segment store
# ---------------------------------------------------------------------------

class TestSegmentStore:
    def test_save_and_get_hourly(self, store: SegmentStore, t0: datetime) -> None:
        events = _make_events(t0, n=3)
        seg = compile_hourly(events, t0, t0 + timedelta(hours=1))
        store.save_segment(seg, events)

        retrieved = store.get_hourly(seg.id)
        assert retrieved is not None
        assert retrieved.id == seg.id
        assert retrieved.segment_type == "hourly"
        assert retrieved.event_count == len(events)

    def test_get_daily(self, store: SegmentStore, t0: datetime) -> None:
        seg = compile_hourly(_make_events(t0), t0, t0 + timedelta(hours=1))
        store.save_segment(seg, [])
        daily = compile_daily([seg], t0)
        store.save_segment(daily, [])

        result = store.get_daily("2026-05-27")
        assert result is not None
        assert result.segment_type == "daily"
        assert seg.id in result.child_ids

    def test_get_weekly(self, store: SegmentStore, t0: datetime) -> None:
        day_seg = compile_daily([], t0)
        store.save_segment(day_seg, [])
        week_seg = compile_weekly([day_seg], 2026, 22)
        store.save_segment(week_seg, [])

        result = store.get_weekly(2026, 22)
        assert result is not None
        assert result.segment_type == "weekly"
        assert day_seg.id in result.child_ids

    def test_get_nonexistent(self, store: SegmentStore) -> None:
        assert store.get_hourly("does_not_exist") is None
        assert store.get_daily("1900-01-01") is None
        assert store.get_weekly(1900, 1) is None

    def test_list_segments(self, store: SegmentStore, t0: datetime) -> None:
        for hour_offset in range(3):
            start = t0 + timedelta(hours=hour_offset)
            seg = compile_hourly(_make_events(start, n=2), start, start + timedelta(hours=1))
            store.save_segment(seg, [])

        segs = store.list_segments("hourly", start=t0, end=t0 + timedelta(hours=3))
        assert len(segs) == 3

    def test_load_events_roundtrip(self, store: SegmentStore, t0: datetime) -> None:
        events = _make_events(t0, n=2)
        seg = compile_hourly(events, t0, t0 + timedelta(hours=1))
        store.save_segment(seg, events)

        loaded = store.load_events(seg)
        assert len(loaded) == len(events)
        assert loaded[0]["event"] == events[0]["event"]

    def test_status(self, store: SegmentStore, t0: datetime) -> None:
        seg = compile_hourly(_make_events(t0), t0, t0 + timedelta(hours=1))
        store.save_segment(seg, [])
        info = store.status()
        assert info["counts"].get("hourly", 0) >= 1


# ---------------------------------------------------------------------------
# Retention and compression
# ---------------------------------------------------------------------------

class TestRetention:
    def test_old_hourly_deleted(self, store: SegmentStore) -> None:
        old_t = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
        seg = compile_hourly([], old_t, old_t + timedelta(hours=1))
        store.save_segment(seg, [])

        assert store.get_hourly(seg.id) is not None

        store.apply_retention(
            hourly_days=1, daily_weeks=4, weekly_months=6,
            compression_enabled=False,
        )

        assert store.get_hourly(seg.id) is None

    def test_recent_hourly_kept(self, store: SegmentStore, t0: datetime) -> None:
        seg = compile_hourly([], t0, t0 + timedelta(hours=1))
        store.save_segment(seg, [])

        store.apply_retention(
            hourly_days=7, daily_weeks=4, weekly_months=6,
            compression_enabled=False,
        )
        assert store.get_hourly(seg.id) is not None

    def test_compression(self, store: SegmentStore) -> None:
        old_t = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        events = _make_events(old_t, n=2)
        seg = compile_hourly(events, old_t, old_t + timedelta(hours=1))
        store.save_segment(seg, events)

        store.apply_retention(
            hourly_days=9999, daily_weeks=9999, weekly_months=9999,
            compression_enabled=True, compress_after_days=1,
        )

        updated = store.get_hourly(seg.id)
        assert updated is not None
        assert updated.compressed

        # Data is still loadable via the .gz file.
        loaded = store.load_events(updated)
        assert len(loaded) == len(events)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class TestCompiler:
    def test_compile_hourly_counts(self, t0: datetime) -> None:
        events = _make_events(t0, n=4)
        seg = compile_hourly(events, t0, t0 + timedelta(hours=1))

        assert seg.segment_type == "hourly"
        assert seg.event_count == len(events)
        assert seg.user_messages == 4
        assert seg.assistant_replies == 4
        assert any(s.name == "read_file" for s in seg.tool_call_stats)

    def test_compile_hourly_errors(self, t0: datetime) -> None:
        events = [
            {"ts": t0.isoformat(), "event": "tool_response",
             "name": "run_command", "result": "Error: boom", "elapsed_s": 1.0, "is_error": True},
            {"ts": t0.isoformat(), "event": "error", "context": "x", "message": "y"},
        ]
        seg = compile_hourly(events, t0, t0 + timedelta(hours=1))
        assert seg.error_count == 2

    def test_compile_hourly_hang(self, t0: datetime) -> None:
        events = [
            {"ts": t0.isoformat(), "event": "tool_hang_warning",
             "name": "run_command", "elapsed_s": 6.0},
        ]
        seg = compile_hourly(events, t0, t0 + timedelta(hours=1))
        stat = next((s for s in seg.tool_call_stats if s.name == "run_command"), None)
        assert stat is not None
        assert stat.hang_count == 1

    def test_compile_daily_aggregates(self, t0: datetime) -> None:
        hourly_segs = []
        for i in range(4):
            start = t0 + timedelta(hours=i)
            events = _make_events(start, n=2)
            hourly_segs.append(compile_hourly(events, start, start + timedelta(hours=1)))

        daily = compile_daily(hourly_segs, t0)
        assert daily.segment_type == "daily"
        assert daily.event_count == sum(s.event_count for s in hourly_segs)
        assert set(daily.child_ids) == {s.id for s in hourly_segs}

    def test_compile_weekly_aggregates(self, t0: datetime) -> None:
        daily_segs = []
        for i in range(3):
            day_t = t0 + timedelta(days=i)
            daily_segs.append(compile_daily([], day_t))

        weekly = compile_weekly(daily_segs, 2026, 22)
        assert weekly.segment_type == "weekly"
        assert weekly.id == "weekly_2026_W22"
        assert set(weekly.child_ids) == {s.id for s in daily_segs}

    def test_filter_events_in_window(self, t0: datetime) -> None:
        events = [
            {"ts": (t0 - timedelta(hours=1)).isoformat(), "event": "user_message"},
            {"ts": t0.isoformat(), "event": "user_message"},
            {"ts": (t0 + timedelta(minutes=30)).isoformat(), "event": "user_message"},
            {"ts": (t0 + timedelta(hours=1)).isoformat(), "event": "user_message"},
        ]
        window = filter_events_in_window(events, t0, t0 + timedelta(hours=1))
        assert len(window) == 2  # exactly [t0, t0+30m)


# ---------------------------------------------------------------------------
# Audit log reader
# ---------------------------------------------------------------------------

class TestAuditLogReader:
    def _write_events(self, path: Path, events: list[dict]) -> None:
        with open(path, "a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

    def test_read_new_events(self, tmp_path: Path, t0: datetime) -> None:
        log = tmp_path / "audit.log"
        events = _make_events(t0, n=3)
        self._write_events(log, events)

        state = AuditReadState()
        new_events, new_state = read_new_events(log, state)

        assert len(new_events) == len(events)
        assert new_state.offset > 0

    def test_incremental_read(self, tmp_path: Path, t0: datetime) -> None:
        log = tmp_path / "audit.log"
        batch1 = _make_events(t0, n=2)
        self._write_events(log, batch1)

        state = AuditReadState()
        ev1, state = read_new_events(log, state)

        batch2 = _make_events(t0 + timedelta(hours=1), n=3)
        self._write_events(log, batch2)

        ev2, state = read_new_events(log, state)
        assert len(ev1) == len(batch1)
        assert len(ev2) == len(batch2)

    def test_rotation_detection(self, tmp_path: Path, t0: datetime) -> None:
        log = tmp_path / "audit.log"
        self._write_events(log, _make_events(t0, n=5))  # 5*4 = 20 events

        state = AuditReadState()
        _, state = read_new_events(log, state)

        # Simulate log rotation (file replaced with a shorter one).
        log.write_text("", encoding="utf-8")
        after_rotation = _make_events(t0, n=2)           # 2*4 = 8 events
        self._write_events(log, after_rotation)

        new_events, _ = read_new_events(log, state)
        # Rotation detected → re-read from start → all 8 new events returned.
        assert len(new_events) == len(after_rotation)

    def test_missing_log(self, tmp_path: Path) -> None:
        log = tmp_path / "nonexistent.log"
        events, state = read_new_events(log, AuditReadState())
        assert events == []
        assert state.offset == 0

    def test_read_state_persistence(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        original = AuditReadState(offset=999, file_size_at_last_read=1234)
        save_read_state(state_path, original)

        loaded = load_read_state(state_path)
        assert loaded.offset == 999
        assert loaded.file_size_at_last_read == 1234

    def test_malformed_lines_skipped(self, tmp_path: Path, t0: datetime) -> None:
        log = tmp_path / "audit.log"
        with open(log, "w", encoding="utf-8") as f:
            f.write('{"ts": "' + t0.isoformat() + '", "event": "user_message"}\n')
            f.write("NOT JSON AT ALL\n")
            f.write('{"ts": "' + t0.isoformat() + '", "event": "assistant_reply"}\n')

        events, _ = read_new_events(log, AuditReadState())
        assert len(events) == 2  # malformed line silently skipped
