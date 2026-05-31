"""
Non-blocking audit logger — writes every agent event to logs/audit.log.

Every line is a JSON object:
  {"ts": "<ISO-8601-UTC>", "event": "<type>", ...details}

Event types
-----------
  user_message      — incoming user text
  assistant_reply   — outgoing agent text
  tool_call         — tool invocation start  {name, args}
  tool_response     — tool invocation end    {name, result, elapsed_s, is_error}
  tool_hang_warning — tool running >5 s      {name, elapsed_s}
  error             — unexpected exception   {context, message}

Design: a daemon thread drains a Queue and writes to the file so that the
async event loop is never blocked. If the queue is full (>10 000 pending
entries) the emit call is silently dropped rather than blocking the caller.
Call flush_audit_log() during shutdown to drain the queue before exit.
"""
from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR

_AUDIT_LOG_PATH = LOGS_DIR / "audit.log"

# --------------------------------------------------------------------------- #
# Internal worker thread                                                        #
# --------------------------------------------------------------------------- #

_queue: queue.Queue[str] = queue.Queue(maxsize=10_000)
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _worker() -> None:
    with open(_AUDIT_LOG_PATH, "a", encoding="utf-8", buffering=1) as f:
        while not _stop_event.is_set() or not _queue.empty():
            try:
                line = _queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                f.write(line + "\n")
                f.flush()
            except Exception:
                pass
            finally:
                _queue.task_done()


def _ensure_started() -> None:
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _stop_event.clear()
            _thread = threading.Thread(
                target=_worker,
                name="audit-log",
                daemon=True,
            )
            _thread.start()


# --------------------------------------------------------------------------- #
# Public emit helpers                                                           #
# --------------------------------------------------------------------------- #

def _emit(event: str, details: dict[str, Any]) -> None:
    _ensure_started()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
        **details,
    }
    try:
        _queue.put_nowait(json.dumps(entry, ensure_ascii=False, default=str))
    except queue.Full:
        pass  # never block the caller


def audit_user_message(text: str, speaker_id: str | None = None) -> None:
    _emit("user_message", {"text": text[:2000], "speaker_id": speaker_id})


def audit_assistant_reply(text: str) -> None:
    _emit("assistant_reply", {"text": text[:2000]})


def audit_tool_call(name: str, args: dict[str, Any]) -> None:
    # Strip 'content' to avoid logging multi-MB file payloads.
    safe_args = {k: (v if k != "content" else f"<{len(str(v))} chars>")
                 for k, v in args.items()}
    _emit("tool_call", {"name": name, "args": safe_args})


def audit_tool_response(
    name: str, result: str, elapsed_s: float, is_error: bool
) -> None:
    _emit(
        "tool_response",
        {
            "name": name,
            "result": result[:1000],
            "elapsed_s": round(elapsed_s, 3),
            "is_error": is_error,
        },
    )


def audit_tool_hang_warning(name: str, elapsed_s: float) -> None:
    _emit(
        "tool_hang_warning",
        {"name": name, "elapsed_s": round(elapsed_s, 1)},
    )


def audit_error(context: str, message: str) -> None:
    _emit("error", {"context": context, "message": str(message)[:500]})


# --------------------------------------------------------------------------- #
# Shutdown                                                                      #
# --------------------------------------------------------------------------- #

def flush_audit_log(timeout: float = 5.0) -> None:
    """Drain pending audit entries and stop the background thread.

    Call this once during application shutdown so that no entries are lost.
    Safe to call even if the thread was never started.
    """
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            return
        _stop_event.set()
    try:
        _queue.join()
    except Exception:
        pass
    if _thread is not None:
        _thread.join(timeout=timeout)
