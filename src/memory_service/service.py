"""Background memory service daemon.

Runs an asyncio loop that:
  1. Wakes at each hourly boundary.
  2. Reads new events from audit.log since the last pass.
  3. Compiles them into an hourly Segment and persists it.
  4. At midnight, compiles the day's hourly segments into a daily Segment.
  5. On Sunday midnight, compiles the week's daily segments into a weekly one.
  6. Applies the configured retention / compression policy.

Process control
---------------
  PID  → storage_path/memory_service.pid   (written on startup, deleted on exit)
  Stop → storage_path/memory_service.stop  (touch this file to request shutdown)

The service also installs signal handlers (SIGINT / SIGTERM on POSIX) that
set the internal stop event so it shuts down cleanly without waiting for the
next interval.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
from src.memory_service.segment_store import SegmentStore

log = logging.getLogger("memory_service")


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


class MemoryService:
    def __init__(self, config: MemoryServiceConfig | None = None) -> None:
        self.config = config or MemoryServiceConfig.load()
        self.store = SegmentStore(self.config.storage_path)
        self._stop = asyncio.Event()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, *, integrated: bool = False) -> None:
        """Run the service.

        integrated=True  — launched as an asyncio task inside the main web
                           process.  Skips PID file and signal-handler setup;
                           shutdown is handled by task cancellation.
        integrated=False — standalone daemon process (default).  Manages a
                           PID file and installs POSIX signal handlers.
        """
        _setup_logging(self.config.service_log_path)
        log.info("Memory service starting (PID %d, integrated=%s)", os.getpid(), integrated)

        if not integrated:
            self.config.pid_file.write_text(str(os.getpid()), encoding="utf-8")
            self.config.stop_file.unlink(missing_ok=True)
            if sys.platform != "win32":
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, self._stop.set)

        try:
            await self._loop()
        except asyncio.CancelledError:
            log.info("Memory service task cancelled.")
            raise
        finally:
            if not integrated:
                try:
                    self.config.pid_file.unlink()
                except FileNotFoundError:
                    pass
            log.info("Memory service stopped.")

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        # Accumulate events that arrived since the last interval boundary
        # but haven't been compiled yet (e.g. if we restarted mid-hour).
        _pending_events: list[dict] = []
        read_state = load_read_state(self.config.read_state_path)

        while True:
            if self._stop.is_set() or self.config.stop_file.exists():
                break

            now = datetime.now(timezone.utc)
            next_boundary = hour_boundary(now) + timedelta(hours=1)
            sleep_s = max((next_boundary - now).total_seconds(), 0.5)

            log.info("Next compilation at %s (%.0fs away)", next_boundary.isoformat(), sleep_s)

            # Sleep until the next hourly boundary, waking early if stopped.
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=sleep_s)
                break  # stop was set
            except asyncio.TimeoutError:
                pass

            if self._stop.is_set() or self.config.stop_file.exists():
                break

            # ----------------------------------------------------------------
            # Compile the hour that just ended.
            # ----------------------------------------------------------------
            interval_start = hour_boundary(now)
            interval_end = next_boundary
            log.info("Compiling %s → %s", interval_start.isoformat(), interval_end.isoformat())

            try:
                new_events, read_state = read_new_events(
                    self.config.audit_log_path, read_state
                )
                save_read_state(self.config.read_state_path, read_state)

                window_events = filter_events_in_window(
                    new_events, interval_start, interval_end
                )
                segment = compile_hourly(window_events, interval_start, interval_end)
                self.store.save_segment(segment, window_events)
                log.info(
                    "Hourly segment %s saved: %d events, %d errors",
                    segment.id, segment.event_count, segment.error_count,
                )
            except Exception as exc:
                log.error("Error compiling hourly segment: %s", exc, exc_info=True)

            # ----------------------------------------------------------------
            # At midnight → compile previous day.
            # ----------------------------------------------------------------
            if interval_end.hour == 0:
                prev_day = (interval_end - timedelta(days=1)).date()
                try:
                    self._compile_day(prev_day)
                except Exception as exc:
                    log.error("Error compiling daily segment: %s", exc, exc_info=True)

                # At week boundary (Monday 00:00) → compile previous week.
                if interval_end.weekday() == 0:
                    prev_week_dt = interval_end - timedelta(weeks=1)
                    iso_cal = prev_week_dt.isocalendar()
                    try:
                        self._compile_week(iso_cal.year, iso_cal.week)
                    except Exception as exc:
                        log.error("Error compiling weekly segment: %s", exc, exc_info=True)

            # ----------------------------------------------------------------
            # Retention / compression.
            # ----------------------------------------------------------------
            try:
                stats = self.store.apply_retention(
                    hourly_days=self.config.retention_hourly_days,
                    daily_weeks=self.config.retention_daily_weeks,
                    weekly_months=self.config.retention_weekly_months,
                    compression_enabled=self.config.compression_enabled,
                    compress_after_days=self.config.compress_after_days,
                )
                if any(stats.values()):
                    log.info("Retention: %s", stats)
            except Exception as exc:
                log.error("Error applying retention: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Daily and weekly roll-ups
    # ------------------------------------------------------------------

    def _compile_day(self, date) -> None:
        from datetime import date as date_type
        if isinstance(date, date_type):
            dt = datetime(date.year, date.month, date.day, tzinfo=timezone.utc)
        else:
            dt = date
        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        hourly = self.store.list_segments("hourly", start=start, end=end)
        if not hourly:
            log.info("No hourly segments for %s — skipping daily compile.", date)
            return

        segment = compile_daily(hourly, start)
        events = []
        for h in hourly:
            events.extend(self.store.load_events(h))
        self.store.save_segment(segment, events)
        log.info("Daily segment %s saved: %d events", segment.id, segment.event_count)

    def _compile_week(self, year: int, week: int) -> None:
        from src.memory_service.compiler import _week_start
        start = _week_start(year, week)
        end = start + timedelta(weeks=1)

        daily = self.store.list_segments("daily", start=start, end=end)
        if not daily:
            log.info("No daily segments for W%02d/%d — skipping weekly compile.", week, year)
            return

        segment = compile_weekly(daily, year, week)
        events = []
        for d in daily:
            events.extend(self.store.load_events(d))
        self.store.save_segment(segment, events)
        log.info("Weekly segment %s saved: %d events", segment.id, segment.event_count)

    # ------------------------------------------------------------------
    # Forced one-shot compile (for testing / manual invocation)
    # ------------------------------------------------------------------

    def compile_now(self) -> None:
        """Compile the current partial hour immediately (blocking)."""
        now = datetime.now(timezone.utc)
        start = hour_boundary(now)
        end = now

        read_state = load_read_state(self.config.read_state_path)
        new_events, read_state = read_new_events(self.config.audit_log_path, read_state)
        save_read_state(self.config.read_state_path, read_state)

        window_events = filter_events_in_window(new_events, start, end)
        segment = compile_hourly(window_events, start, end)
        self.store.save_segment(segment, window_events)
        log.info("Manual compile: %s (%d events)", segment.id, segment.event_count)
