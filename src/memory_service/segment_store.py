"""SQLite-backed segment store with JSON data files.

Schema
------
  segments      — one row per compiled segment (metadata only)
  segment_links — parent→child relationships for the hierarchy

The full event list for each segment is stored in a separate JSON file
(``data_path``) so the SQLite index stays small and fast.  Older data files
can be gzip-compressed without touching the index.
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.memory_service.models import Segment, ToolCallStat

_DDL = """
CREATE TABLE IF NOT EXISTS segments (
    id              TEXT PRIMARY KEY,
    segment_type    TEXT NOT NULL CHECK(segment_type IN ('hourly','daily','weekly')),
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    duration_s      REAL NOT NULL,
    summary         TEXT,
    event_count     INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0,
    user_messages   INTEGER DEFAULT 0,
    assistant_replies INTEGER DEFAULT 0,
    data_path       TEXT NOT NULL,
    compressed      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segment_links (
    parent_id TEXT NOT NULL,
    child_id  TEXT NOT NULL,
    PRIMARY KEY (parent_id, child_id)
);

CREATE INDEX IF NOT EXISTS idx_type_start ON segments(segment_type, start_time);
"""


def _row_to_segment(row: sqlite3.Row, children: list[str]) -> Segment:
    return Segment(
        id=row["id"],
        segment_type=row["segment_type"],
        start_time=datetime.fromisoformat(row["start_time"]),
        end_time=datetime.fromisoformat(row["end_time"]),
        summary=row["summary"] or "",
        event_count=row["event_count"],
        error_count=row["error_count"],
        user_messages=row["user_messages"],
        assistant_replies=row["assistant_replies"],
        tool_call_stats=[],   # not stored in DB — load from data file if needed
        child_ids=children,
        data_path=row["data_path"],
        compressed=bool(row["compressed"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SegmentStore:
    """Read/write segment metadata (SQLite) and event data (JSON files)."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._db_path = storage_path / "segments.db"
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(_DDL)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self._db_path), timeout=10)
        con.row_factory = sqlite3.Row
        return con

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_segment(self, segment: Segment, events: list[dict]) -> None:
        """Persist a segment: write JSON data file, then upsert into SQLite."""
        # Write event data file atomically.
        data_file = self._data_file_path(segment)
        _atomic_write_json(data_file, {"segment_id": segment.id, "events": events})
        segment.data_path = str(data_file.relative_to(self.storage_path))

        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO segments
                    (id, segment_type, start_time, end_time, duration_s,
                     summary, event_count, error_count, user_messages,
                     assistant_replies, data_path, compressed, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    segment.id,
                    segment.segment_type,
                    segment.start_time.isoformat(),
                    segment.end_time.isoformat(),
                    segment.duration_s,
                    segment.summary,
                    segment.event_count,
                    segment.error_count,
                    segment.user_messages,
                    segment.assistant_replies,
                    segment.data_path,
                    int(segment.compressed),
                    segment.created_at.isoformat(),
                ),
            )
            for child_id in segment.child_ids:
                con.execute(
                    "INSERT OR IGNORE INTO segment_links (parent_id, child_id) VALUES (?,?)",
                    (segment.id, child_id),
                )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, segment_id: str) -> Segment | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM segments WHERE id = ?", (segment_id,)
            ).fetchone()
            if row is None:
                return None
            children = [
                r["child_id"]
                for r in con.execute(
                    "SELECT child_id FROM segment_links WHERE parent_id = ?",
                    (segment_id,),
                ).fetchall()
            ]
        return _row_to_segment(row, children)

    def get_hourly(self, segment_id: str) -> Segment | None:
        seg = self.get_by_id(segment_id)
        return seg if seg and seg.segment_type == "hourly" else None

    def get_daily(self, date: str) -> Segment | None:
        """date: 'YYYY-MM-DD'"""
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM segments WHERE segment_type='daily' AND start_time LIKE ?",
                (f"{date}%",),
            ).fetchone()
            if row is None:
                return None
            children = [
                r["child_id"]
                for r in con.execute(
                    "SELECT child_id FROM segment_links WHERE parent_id = ?",
                    (row["id"],),
                ).fetchall()
            ]
        return _row_to_segment(row, children)

    def get_weekly(self, year: int, week: int) -> Segment | None:
        segment_id = f"weekly_{year}_W{week:02d}"
        return self.get_by_id(segment_id)

    def list_segments(
        self,
        segment_type: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Segment]:
        query = "SELECT * FROM segments WHERE segment_type = ?"
        params: list[Any] = [segment_type]
        if start:
            query += " AND end_time >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND start_time < ?"
            params.append(end.isoformat())
        query += " ORDER BY start_time"

        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
            results = []
            for row in rows:
                children = [
                    r["child_id"]
                    for r in con.execute(
                        "SELECT child_id FROM segment_links WHERE parent_id = ?",
                        (row["id"],),
                    ).fetchall()
                ]
                results.append(_row_to_segment(row, children))
        return results

    def load_events(self, segment: Segment) -> list[dict]:
        """Load the full event list from the segment's data file.

        Handles both plain JSON and gzip-compressed JSON transparently,
        detected by the stored data_path extension rather than probing.
        """
        p = self.storage_path / segment.data_path
        # If the stored path ends in .gz the file is already compressed.
        if segment.data_path.endswith(".gz"):
            if not p.exists():
                return []
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f).get("events", [])
        # Plain JSON path.
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f).get("events", [])
        # Fallback: check if a .gz version exists (e.g. compressed externally).
        gz = Path(str(p) + ".gz")
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8") as f:
                return json.load(f).get("events", [])
        return []

    # ------------------------------------------------------------------
    # Retention & compression
    # ------------------------------------------------------------------

    def apply_retention(
        self,
        *,
        hourly_days: int = 7,
        daily_weeks: int = 4,
        weekly_months: int = 6,
        compression_enabled: bool = True,
        compress_after_days: int = 1,
    ) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        deleted = {"hourly": 0, "daily": 0, "weekly": 0}
        compressed = 0

        cutoffs = {
            "hourly": now - timedelta(days=hourly_days),
            "daily": now - timedelta(weeks=daily_weeks),
            "weekly": now - timedelta(days=weekly_months * 30),
        }
        compress_cutoff = now - timedelta(days=compress_after_days)

        with self._connect() as con:
            for stype, cutoff in cutoffs.items():
                rows = con.execute(
                    "SELECT id, data_path FROM segments "
                    "WHERE segment_type=? AND end_time < ?",
                    (stype, cutoff.isoformat()),
                ).fetchall()
                for row in rows:
                    self._delete_segment_files(row["data_path"])
                    con.execute("DELETE FROM segment_links WHERE parent_id=? OR child_id=?",
                                (row["id"], row["id"]))
                    con.execute("DELETE FROM segments WHERE id=?", (row["id"],))
                    deleted[stype] += 1

            # Compress old data files.
            if compression_enabled:
                rows = con.execute(
                    "SELECT id, data_path FROM segments "
                    "WHERE compressed=0 AND end_time < ?",
                    (compress_cutoff.isoformat(),),
                ).fetchall()
                for row in rows:
                    p = self.storage_path / row["data_path"]
                    if p.exists():
                        gz = Path(str(p) + ".gz")
                        with open(p, "rb") as f_in, gzip.open(gz, "wb") as f_out:
                            f_out.write(f_in.read())
                        p.unlink()
                        con.execute(
                            "UPDATE segments SET compressed=1, data_path=? WHERE id=?",
                            (row["data_path"] + ".gz", row["id"]),
                        )
                        compressed += 1

        return {**deleted, "compressed": compressed}

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._connect() as con:
            counts = {
                row["segment_type"]: row["cnt"]
                for row in con.execute(
                    "SELECT segment_type, COUNT(*) as cnt FROM segments GROUP BY segment_type"
                ).fetchall()
            }
            newest = {
                row["segment_type"]: row["newest"]
                for row in con.execute(
                    "SELECT segment_type, MAX(end_time) as newest "
                    "FROM segments GROUP BY segment_type"
                ).fetchall()
            }
        return {
            "db_path": str(self._db_path),
            "counts": counts,
            "newest": newest,
            "db_size_kb": round(self._db_path.stat().st_size / 1024, 1)
            if self._db_path.exists()
            else 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _data_file_path(self, segment: Segment) -> Path:
        sub = segment.start_time.strftime("%Y/%m/%d")
        d = self.storage_path / sub
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{segment.id}.json"

    def _delete_segment_files(self, data_path: str) -> None:
        for p in [
            self.storage_path / data_path,
            Path(str(self.storage_path / data_path) + ".gz"),
        ]:
            try:
                p.unlink()
            except FileNotFoundError:
                pass


def _atomic_write_json(path: Path, data: Any) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
