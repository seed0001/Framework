"""CLI for the background memory service.

Usage
-----
  python -m src.memory_service start     Start daemon in background
  python -m src.memory_service stop      Signal daemon to stop
  python -m src.memory_service restart   Stop + start
  python -m src.memory_service status    Show health and segment counts
  python -m src.memory_service compile   Compile the current partial hour now

  python -m src.memory_service get-hourly  <segment-id>
  python -m src.memory_service get-daily   <YYYY-MM-DD>
  python -m src.memory_service get-weekly  <year> <week>

  python -m src.memory_service _run      (internal: run service in foreground)
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _load_config():
    from src.memory_service.config import MemoryServiceConfig
    return MemoryServiceConfig.load()


def _is_running(pid_file: Path) -> tuple[bool, int]:
    if not pid_file.exists():
        return False, -1
    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return False, -1
    # Check if the process is alive.
    try:
        os.kill(pid, 0)
        return True, pid
    except (ProcessLookupError, PermissionError):
        return False, pid


def cmd_start() -> None:
    cfg = _load_config()
    running, pid = _is_running(cfg.pid_file)
    if running:
        print(f"Already running (PID {pid})")
        return

    log_path = cfg.service_log_path
    print(f"Starting memory service… (log: {log_path})")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.memory_service", "_run"],
        stdout=open(log_path, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        start_new_session=(sys.platform != "win32"),
    )

    # Wait briefly for the PID file to appear.
    deadline = time.time() + 5.0
    while time.time() < deadline:
        time.sleep(0.2)
        if cfg.pid_file.exists():
            print(f"Started (PID {cfg.pid_file.read_text().strip()})")
            return

    # PID file never appeared — check if the process is still alive.
    if proc.poll() is None:
        print(f"Started (PID {proc.pid}, PID file pending)")
    else:
        print(f"Failed to start (exit code {proc.returncode}). See {log_path}.")
        sys.exit(1)


def cmd_stop() -> None:
    cfg = _load_config()
    running, pid = _is_running(cfg.pid_file)
    if not running:
        print("Not running.")
        cfg.stop_file.unlink(missing_ok=True)
        return

    # Write stop file (the service polls this).
    cfg.stop_file.write_text("stop", encoding="utf-8")
    print(f"Stop signal sent to PID {pid}. Waiting…")

    # Also send SIGTERM on POSIX.
    if sys.platform != "win32":
        try:
            import signal as _sig
            os.kill(pid, _sig.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.time() + 10.0
    while time.time() < deadline:
        time.sleep(0.3)
        if not cfg.pid_file.exists():
            print("Stopped.")
            cfg.stop_file.unlink(missing_ok=True)
            return

    print("Service did not stop within 10 s. PID file still present.")
    sys.exit(1)


def cmd_restart() -> None:
    cmd_stop()
    time.sleep(0.5)
    cmd_start()


def cmd_status() -> None:
    cfg = _load_config()
    running, pid = _is_running(cfg.pid_file)
    print(f"Status : {'RUNNING (PID ' + str(pid) + ')' if running else 'STOPPED'}")
    print(f"Storage: {cfg.storage_path}")
    print(f"DB     : {cfg.db_path}")

    from src.memory_service.segment_store import SegmentStore
    store = SegmentStore(cfg.storage_path)
    info = store.status()
    counts = info.get("counts", {})
    newest = info.get("newest", {})
    print(f"DB size: {info.get('db_size_kb', 0)} KB")
    for stype in ("hourly", "daily", "weekly"):
        n = counts.get(stype, 0)
        last = newest.get(stype, "—")
        print(f"  {stype:7s}: {n:4d} segments  (newest: {last})")


def cmd_compile() -> None:
    from src.memory_service.service import MemoryService
    svc = MemoryService()
    svc.compile_now()
    print("Compiled current partial hour.")


def cmd_get_hourly(segment_id: str) -> None:
    cfg = _load_config()
    from src.memory_service.segment_store import SegmentStore
    store = SegmentStore(cfg.storage_path)
    seg = store.get_hourly(segment_id)
    if seg is None:
        print(f"Hourly segment not found: {segment_id}")
        sys.exit(1)
    _print_segment(seg)


def cmd_get_daily(date: str) -> None:
    cfg = _load_config()
    from src.memory_service.segment_store import SegmentStore
    store = SegmentStore(cfg.storage_path)
    seg = store.get_daily(date)
    if seg is None:
        print(f"Daily segment not found for: {date}")
        sys.exit(1)
    _print_segment(seg)


def cmd_get_weekly(year: str, week: str) -> None:
    cfg = _load_config()
    from src.memory_service.segment_store import SegmentStore
    store = SegmentStore(cfg.storage_path)
    seg = store.get_weekly(int(year), int(week))
    if seg is None:
        print(f"Weekly segment not found: {year} W{week}")
        sys.exit(1)
    _print_segment(seg)


def _print_segment(seg) -> None:
    print(json.dumps(
        {
            "id": seg.id,
            "type": seg.segment_type,
            "start": seg.start_time.isoformat(),
            "end": seg.end_time.isoformat(),
            "duration_s": seg.duration_s,
            "summary": seg.summary,
            "events": seg.event_count,
            "errors": seg.error_count,
            "user_messages": seg.user_messages,
            "assistant_replies": seg.assistant_replies,
            "child_segments": seg.child_ids,
            "data_path": seg.data_path,
            "compressed": seg.compressed,
        },
        indent=2,
    ))


def cmd_run() -> None:
    """Internal: run the service in the foreground (called by start subprocess)."""
    from src.memory_service.service import MemoryService
    svc = MemoryService()
    asyncio.run(svc.run())


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    rest = args[1:]

    dispatch = {
        "start": (cmd_start, 0),
        "stop": (cmd_stop, 0),
        "restart": (cmd_restart, 0),
        "status": (cmd_status, 0),
        "compile": (cmd_compile, 0),
        "get-hourly": (cmd_get_hourly, 1),
        "get-daily": (cmd_get_daily, 1),
        "get-weekly": (cmd_get_weekly, 2),
        "_run": (cmd_run, 0),
    }

    if cmd not in dispatch:
        print(f"Unknown command: {cmd}\n")
        print(__doc__)
        sys.exit(1)

    fn, nargs = dispatch[cmd]
    if len(rest) < nargs:
        print(f"'{cmd}' requires {nargs} argument(s).")
        sys.exit(1)

    fn(*rest[:nargs])


if __name__ == "__main__":
    main()
