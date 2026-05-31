"""
Agent logging. Writes to logs/agent.log (rotating, gitignored).
Logs: tool calls, results, Doctor Mode, Cursor CLI escalation, errors.

Also writes to logs/debug.log via the watchdog helpers: every tool
invocation is bracketed by log_watchdog_start / log_watchdog_done (or
log_watchdog_error) so a developer can see exactly which tool hung and
how long each call took.
"""
import logging
import time
import uuid
from pathlib import Path

from config.settings import LOGS_DIR

AGENT_LOG_PATH = LOGS_DIR / "agent.log"
DEBUG_LOG_PATH = LOGS_DIR / "debug.log"


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("agent")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(AGENT_LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def _setup_debug_logger() -> logging.Logger:
    """Separate logger for the per-tool watchdog trace (logs/debug.log)."""
    logger = logging.getLogger("agent.debug")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    # Prevent messages from bubbling up to the root logger / agent logger.
    logger.propagate = False
    fh = logging.FileHandler(DEBUG_LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


# ---------------------------------------------------------------------------
# Watchdog helpers — called by _run_tool in core.py
# ---------------------------------------------------------------------------

def make_call_id() -> str:
    """Return a short unique ID to correlate start/done/error entries."""
    return uuid.uuid4().hex[:8]


def log_watchdog_start(name: str, call_id: str) -> None:
    """Write a [CALL] start line to debug.log."""
    _setup_debug_logger().info(f"[CALL] {name} | id={call_id} | start={time.time():.3f}")


def log_watchdog_done(name: str, call_id: str, elapsed: float) -> None:
    """Write a [DONE] completion line to debug.log."""
    _setup_debug_logger().info(f"[DONE] {name} | id={call_id} | elapsed={elapsed:.3f}s")


def log_watchdog_error(name: str, call_id: str, elapsed: float, error: Exception) -> None:
    """Write an [ERROR] line to debug.log."""
    _setup_debug_logger().error(
        f"[ERROR] {name} | id={call_id} | elapsed={elapsed:.3f}s | {type(error).__name__}: {error}"
    )


def log_tool_start(name: str, args: dict) -> None:
    _setup_logger().info(f"TOOL_START | {name} | args={args}")


def log_tool_result(name: str, result_preview: str, is_error: bool) -> None:
    preview = (result_preview or "")[:500].replace("\n", " ")
    level = logging.WARNING if is_error else logging.INFO
    _setup_logger().log(level, f"TOOL_RESULT | {name} | error={is_error} | {preview}")


def log_doctor_mode(tool_name: str, error_result: str, strategies: str) -> None:
    _setup_logger().warning(
        f"DOCTOR_MODE | tool={tool_name} | error={error_result[:300]} | strategies={strategies}"
    )


def log_escalation(reason: str, failed_tools: list, errors: list, cursor_prompt: str) -> None:
    _setup_logger().warning(
        f"ESCALATION | reason={reason} | failed={failed_tools} | "
        f"errors={errors} | prompt={cursor_prompt[:300]}"
    )


def log_cursor_cli(called: bool, outcome: str) -> None:
    _setup_logger().info(f"CURSOR_CLI | called={called} | {outcome[:300]}")


def log_error(context: str, exc: Exception | str) -> None:
    _setup_logger().error(f"ERROR | {context} | {exc}")


def log_outreach_attempt(channel: str, target: str, content_preview: str) -> None:
    _setup_logger().info(f"OUTREACH_ATTEMPT | channel={channel} target={target} | {content_preview[:100]}")


def log_outreach_success(channel: str, target: str) -> None:
    _setup_logger().info(f"OUTREACH_SUCCESS | channel={channel} target={target}")


def log_outreach_failure(channel: str, target: str, error: str) -> None:
    _setup_logger().warning(f"OUTREACH_FAILURE | channel={channel} target={target} | {error}")


def log_subagent_spawn(aid: str, task: str, script: str) -> None:
    _setup_logger().info(f"SUBAGENT_SPAWN | {aid} | task={task} | script={script}")


def log_subagent_status(aid: str, status: str, extra: str = "") -> None:
    _setup_logger().info(f"SUBAGENT_STATUS | {aid} | status={status} | {extra}")


def log_status_check(result: str, issues: bool) -> None:
    level = logging.WARNING if issues else logging.INFO
    _setup_logger().log(level, f"STATUS_CHECK | issues={issues} | {result[:300]}")
