"""
Cursor CLI as Andrew's editor.

Why this exists
---------------
Andrew's previous flow used ``write_file`` directly. That worked for short,
fully-known content but failed on:

* multi-file scaffolds (e.g. a Vite + React + Three.js project for Rusty),
* surgical edits inside long existing files where Andrew risked clobbering
  unrelated regions,
* cross-file refactors.

This module routes those edits through Cursor CLI in headless mode. Cursor is
itself an LLM agent, so each call is non-deterministic and billed — we wrap
it with budget caps, path scoping, structured results, and a verify step so
Andrew can confirm what changed.

Public surface
--------------
``cursor_edit(prompt, mode, paths_hint, write, speaker_tier)`` — invoke Cursor
to perform an edit. Returns a structured string for the LLM that includes the
session id, the changed-files diff vs the pre-snapshot, and the model's
summary text.

``cursor_verify(paths)`` — read back files and report which of them changed
since the most recent ``cursor_edit`` snapshot. Used to confirm a delegated
edit actually landed.

``get_cursor_usage()`` — budget introspection (mirrors ``get_image_usage``).

Design notes
------------
* **Path scoping:** every path is resolved and rejected if it escapes
  ``PROJECT_ROOT``. This matches the user's choice (``scope=repo_only``).
* **Tier gating for writes:** ``--force`` (file mutations) is only added when
  the speaker tier is ``creator``. Lower tiers can still call ``cursor_edit``
  to *plan* changes (read-only output), but Cursor will not write.
* **Budget:** ``CURSOR_EDIT_DAILY_LIMIT`` env var (default 100) caps total
  invocations per day to avoid burning credits on a runaway loop.
* **Snapshots:** before each write-mode call we hash the candidate files. The
  follow-up verify reports which files actually changed.
* **Session log:** every call appends to ``data/cursor_sessions.jsonl`` so
  Andrew can reference past edits in multi-step work.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
import re

from config.settings import DATA_DIR, PROJECT_ROOT
from src.logging_config import log_cursor_cli, log_error
from src.tools.cursor_cli import run_cursor_cli


USAGE_PATH = DATA_DIR / "cursor_usage.json"
SESSIONS_LOG = DATA_DIR / "cursor_sessions.jsonl"
SNAPSHOT_PATH = DATA_DIR / "cursor_last_snapshot.json"

DEFAULT_DAILY_LIMIT = 100

VALID_MODES = ("scaffold", "refactor", "patch", "plan")

_MODE_HINTS = {
    "scaffold": (
        "Create new files / project structure. Use when starting something "
        "fresh (e.g. a React Three.js app)."
    ),
    "refactor": (
        "Coordinated edits across multiple existing files. Cursor will read "
        "first, then write."
    ),
    "patch": (
        "Surgical edit inside one or two existing files. Preserve unrelated "
        "content. Best when you want a small, targeted change."
    ),
    "plan": (
        "Read-only. Cursor returns its proposed plan/diff but does not write. "
        "Use to preview before committing to a write call."
    ),
}


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

def _load_usage() -> dict[str, Any]:
    if not USAGE_PATH.exists():
        return {"by_date": {}, "total": 0}
    try:
        with open(USAGE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"by_date": {}, "total": 0}


def _save_usage(data: dict) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _inc_usage() -> dict[str, Any]:
    today = str(date.today())
    data = _load_usage()
    by_date = data.get("by_date", {})
    by_date[today] = by_date.get(today, 0) + 1
    data["by_date"] = by_date
    data["total"] = data.get("total", 0) + 1
    data["last_used"] = datetime.now().isoformat()
    _save_usage(data)
    return data


def _daily_limit() -> int:
    return int(os.getenv("CURSOR_EDIT_DAILY_LIMIT", str(DEFAULT_DAILY_LIMIT)))


def get_cursor_usage() -> str:
    """Return current Cursor CLI usage (budget introspection)."""
    limit = _daily_limit()
    data = _load_usage()
    today = str(date.today())
    today_count = data.get("by_date", {}).get(today, 0)
    remaining = max(0, limit - today_count)
    return (
        f"Cursor CLI usage: {today_count}/{limit} today, {remaining} remaining. "
        f"Total all-time: {data.get('total', 0)}. "
        f"Last used: {data.get('last_used', 'never')}"
    )


def _check_budget() -> tuple[bool, str]:
    limit = _daily_limit()
    data = _load_usage()
    today_count = data.get("by_date", {}).get(str(date.today()), 0)
    if today_count >= limit:
        return False, (
            f"Cursor CLI daily budget exhausted ({today_count}/{limit}). "
            "Try again tomorrow or raise CURSOR_EDIT_DAILY_LIMIT in .env."
        )
    return True, ""


# ---------------------------------------------------------------------------
# Path scoping
# ---------------------------------------------------------------------------

def _project_root_resolved() -> Path:
    return Path(PROJECT_ROOT).resolve()


def _is_within_project(p: Path) -> bool:
    try:
        p.resolve().relative_to(_project_root_resolved())
        return True
    except (OSError, ValueError):
        return False


def _normalise_paths(paths: Iterable[str] | None) -> list[Path]:
    """Resolve each path, drop any that escape PROJECT_ROOT."""
    if not paths:
        return []
    out: list[Path] = []
    for raw in paths:
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = _project_root_resolved() / candidate
        if _is_within_project(candidate):
            out.append(candidate.resolve())
    return out


# ---------------------------------------------------------------------------
# Snapshots / diffs
# ---------------------------------------------------------------------------

def _hash_file(p: Path) -> str | None:
    try:
        if not p.exists() or not p.is_file():
            return None
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _gather_paths_for_snapshot(hint: list[Path]) -> list[Path]:
    """
    Expand directory hints into file lists (shallow). For files, keep as-is.
    Capped at 200 files to keep snapshots cheap.
    """
    files: list[Path] = []
    for p in hint:
        if p.is_dir():
            for child in p.rglob("*"):
                if child.is_file() and ".git" not in child.parts and "__pycache__" not in child.parts:
                    files.append(child)
                    if len(files) >= 200:
                        return files
        elif p.is_file() or not p.exists():
            # include non-existent paths so we can detect creation
            files.append(p)
        if len(files) >= 200:
            break
    return files


def _take_snapshot(paths: list[Path]) -> dict[str, str | None]:
    """Map absolute_path → sha256 (or None if missing)."""
    return {str(p): _hash_file(p) for p in paths}


def _save_snapshot(snapshot: dict[str, str | None], session_id: str, prompt: str) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "prompt": prompt[:500],
        "taken_at": datetime.now().isoformat(),
        "files": snapshot,
    }
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _load_snapshot() -> dict[str, Any] | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


@dataclass
class _DiffEntry:
    path: str
    status: str  # created | modified | deleted | unchanged | unknown


def _diff_against_snapshot(
    snapshot: dict[str, str | None],
    extra_paths: list[Path] | None = None,
) -> list[_DiffEntry]:
    """Compare current on-disk hashes to the snapshot."""
    diffs: list[_DiffEntry] = []
    seen: set[str] = set()
    for raw_path, prev_hash in snapshot.items():
        p = Path(raw_path)
        seen.add(str(p))
        cur = _hash_file(p)
        if prev_hash is None and cur is None:
            continue
        if prev_hash is None and cur is not None:
            diffs.append(_DiffEntry(raw_path, "created"))
        elif prev_hash is not None and cur is None:
            diffs.append(_DiffEntry(raw_path, "deleted"))
        elif prev_hash != cur:
            diffs.append(_DiffEntry(raw_path, "modified"))
        else:
            diffs.append(_DiffEntry(raw_path, "unchanged"))
    for extra in extra_paths or []:
        s = str(extra.resolve())
        if s in seen:
            continue
        if extra.exists():
            diffs.append(_DiffEntry(s, "created"))
    return diffs


# ---------------------------------------------------------------------------
# Session log
# ---------------------------------------------------------------------------

def _log_session(entry: dict[str, Any]) -> None:
    SESSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(SESSIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log_error("cursor_editor.session_log", e)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_full_prompt(prompt: str, mode: str, paths_hint: list[Path]) -> str:
    """
    Wrap Andrew's natural-language intent with a structured envelope so
    Cursor knows mode, target files, and verification expectations.
    """
    rel_hints = []
    root = _project_root_resolved()
    for p in paths_hint:
        try:
            rel_hints.append(str(p.relative_to(root)))
        except ValueError:
            rel_hints.append(str(p))
    hint_block = ""
    if rel_hints:
        hint_block = "\nTarget files / directories:\n  - " + "\n  - ".join(rel_hints) + "\n"

    mode_note = _MODE_HINTS.get(mode, "")
    return (
        f"[Andrew → Cursor | mode={mode}]\n"
        f"Intent: {prompt.strip()}\n"
        f"{hint_block}"
        f"Mode guidance: {mode_note}\n"
        "Constraints: do not touch files outside the project root. Preserve unrelated code. "
        "When done, list the files you created or modified."
    )


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------

def apply_multi_file_edits(workspace_root: Path, response_text: str) -> tuple[bool, str]:
    """Parse file targets and search-replace blocks, and apply them surgically."""
    parts = re.split(r"#\s*FILE:\s*", response_text)
    if len(parts) <= 1:
        # Fallback check for raw blocks without file headers
        pattern = re.compile(
            r"<<<<<<< SEARCH\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>> REPLACE",
            re.DOTALL
        )
        matches = list(pattern.finditer(response_text))
        if not matches:
            return False, "No target file header (# FILE: path) and no SEARCH/REPLACE blocks found."
        return False, "SEARCH/REPLACE blocks found but target file header (# FILE: path/to/file) is missing."

    results = []
    success = False

    for part in parts[1:]:
        lines = part.splitlines()
        if not lines:
            continue
        file_path_str = lines[0].strip().strip("'\"` ")
        
        target_path = Path(file_path_str)
        if not target_path.is_absolute():
            target_path = (workspace_root / target_path).resolve()
        
        try:
            target_path.relative_to(workspace_root.resolve())
        except ValueError:
            results.append(f"Skipped {file_path_str}: outside workspace root.")
            continue

        if not target_path.exists():
            results.append(f"Skipped {file_path_str}: file does not exist.")
            continue

        pattern = re.compile(
            r"<<<<<<< SEARCH\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>> REPLACE",
            re.DOTALL
        )
        matches = list(pattern.finditer(part))
        if not matches:
            results.append(f"No SEARCH/REPLACE blocks found for {file_path_str}")
            continue

        try:
            content = target_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            results.append(f"Failed to read {file_path_str}: {e}")
            continue

        new_content = content
        applied = 0
        failed = 0

        for match in matches:
            search_block = match.group(1)
            replace_block = match.group(2)

            search_norm = search_block.replace("\r\n", "\n").strip()
            new_content_norm = new_content.replace("\r\n", "\n")

            if search_norm in new_content_norm:
                new_content_norm = new_content_norm.replace(search_norm, replace_block, 1)
                if "\r\n" in content:
                    new_content = new_content_norm.replace("\n", "\r\n")
                else:
                    new_content = new_content_norm
                applied += 1
            elif search_block in new_content:
                new_content = new_content.replace(search_block, replace_block, 1)
                applied += 1
            else:
                failed += 1

        if applied > 0:
            try:
                target_path.write_text(new_content, encoding="utf-8")
                success = True
                results.append(f"Applied {applied} edits to {file_path_str}" + (f" (failed {failed})" if failed else "") + ".")
            except OSError as e:
                results.append(f"Failed to write {file_path_str}: {e}")
        else:
            results.append(f"Failed to apply any edits to {file_path_str}. SEARCH block mismatch.")

    return success, "\n".join(results)


async def cursor_edit(
    prompt: str,
    *,
    mode: str = "patch",
    paths_hint: list[str] | None = None,
    write: bool = True,
    speaker_tier: str = "creator",
    timeout: int = 240,
) -> str:
    """
    Surgically edit files by calling the active LLM backend with a coding persona
    to generate search-replace conflict blocks.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return "Error: cursor_edit requires a non-empty prompt."

    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        return f"Error: invalid mode '{mode}'. Use one of {', '.join(VALID_MODES)}."

    effective_write = bool(write) and mode != "plan" and speaker_tier == "creator"
    if write and not effective_write:
        log_cursor_cli(
            False,
            f"write requested but downgraded: tier={speaker_tier} mode={mode}",
        )

    hint_paths = _normalise_paths(paths_hint or [])
    rejected = [p for p in (paths_hint or []) if p and not any(str(Path(p).expanduser().resolve()) == str(hp) for hp in hint_paths)]
    if rejected:
        for r in rejected:
            log_cursor_cli(False, f"path rejected (outside PROJECT_ROOT): {r}")

    snapshot_targets = _gather_paths_for_snapshot(hint_paths) if hint_paths else []
    pre_snapshot = _take_snapshot(snapshot_targets) if snapshot_targets else {}

    system_prompt = (
        "You are Andrew's elite software engineering brain (Coding Persona).\n"
        "Your goal is to surgically edit files in the workspace based on the user's instructions.\n"
        "You MUST output your edits ONLY as target file markers and SEARCH/REPLACE blocks.\n\n"
        "Format:\n"
        "# FILE: relative/path/to/file\n"
        "<<<<<<< SEARCH\n"
        "[exact lines of code to find and replace]\n"
        "=======\n"
        "[new replacement lines of code]\n"
        ">>>>>>> REPLACE\n\n"
        "Rules:\n"
        "1. Do not output markdown code blocks (like ```python) around SEARCH/REPLACE blocks. Output them directly.\n"
        "2. The SEARCH block must match the existing file content EXACTLY, character-for-character, including indentation and spacing.\n"
        "3. Output SEARCH/REPLACE blocks ONLY for files that require edits. Do not output blocks for unmodified files.\n"
        "4. Do not provide any introductory text, notes, chat, explanation, or wrap-up. Output ONLY target files and search/replace blocks."
    )

    context_files = []
    for p in hint_paths:
        if p.exists() and p.is_file():
            try:
                rel = p.relative_to(_project_root_resolved())
            except ValueError:
                rel = p
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                context_files.append(f"--- FILE: {rel} ---\n{content}\n-----------------")
            except OSError:
                pass
    
    context_str = "\n\n".join(context_files)
    user_message = (
        f"Workspace files contents:\n{context_str}\n\n"
        f"User Instruction: {prompt}\n\n"
        "Please provide the search-replace blocks now."
    )

    from src import backend_switching
    from openai import AsyncOpenAI
    import time

    start_time = time.time()
    try:
        active = backend_switching.get_active_backend(user_id="default")
        client = AsyncOpenAI(api_key=active.api_key, base_url=active.base_url)

        resp = await client.chat.completions.create(
            model=active.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )
        llm_output = (resp.choices[0].message.content or "").strip()
        ok = True
        err_msg = ""
    except Exception as e:
        ok = False
        llm_output = ""
        err_msg = str(e)

    duration_ms = int((time.time() - start_time) * 1000)
    session_id = f"sess_{int(start_time)}"

    applied_details = "Plan-only mode: no files modified."
    if ok and effective_write:
        success, applied_details = apply_multi_file_edits(_project_root_resolved(), llm_output)
        if not success:
            ok = False
            err_msg = applied_details

    usage = _inc_usage()
    diffs: list[_DiffEntry] = []
    if effective_write and pre_snapshot:
        diffs = _diff_against_snapshot(pre_snapshot, extra_paths=hint_paths)
        _save_snapshot(pre_snapshot, session_id, prompt)
        try:
            from src.artifact_memory import record_artifact
            for d in diffs:
                if d.status in ("created", "modified"):
                    record_artifact(
                        d.path,
                        title=Path(d.path).name,
                        summary=f"Created or updated surgically via coding brain (session {session_id}).",
                        source="coding_persona_edit",
                    )
        except Exception as e:
            log_error("cursor_editor.record_artifacts", e)

    _log_session(
        {
            "ts": datetime.now().isoformat(),
            "mode": mode,
            "write": effective_write,
            "speaker_tier": speaker_tier,
            "prompt": prompt[:1000],
            "paths_hint": [str(p) for p in hint_paths],
            "rejected_paths": rejected,
            "ok": ok,
            "session_id": session_id,
            "duration_ms": duration_ms,
            "returncode": 0 if ok else 1,
            "error": err_msg[:500] if err_msg else "",
            "changes": [d.__dict__ for d in diffs if d.status != "unchanged"],
            "usage_today": usage.get("by_date", {}).get(str(date.today()), 0),
        }
    )

    lines: list[str] = []
    status_label = "ok" if ok else "error"
    lines.append(
        f"[coding_persona_edit | mode={mode} | write={effective_write} | {status_label}]"
    )
    if session_id:
        lines.append(f"session_id: {session_id}")
    if duration_ms:
        lines.append(f"duration_ms: {duration_ms}")

    if not ok:
        lines.append(f"error: {err_msg or 'unknown'}")
        if llm_output:
            lines.append(f"output: {llm_output[:1500]}")
        if rejected:
            lines.append(f"rejected_paths (outside repo): {rejected}")
        return "\n".join(lines)

    if write and not effective_write:
        lines.append("Plan mode: proposed changes:\n" + llm_output[:2000])

    if diffs:
        changed = [d for d in diffs if d.status in ("created", "modified", "deleted")]
        if changed:
            lines.append("changed_files:")
            for d in changed[:50]:
                lines.append(f"  - {d.status}: {d.path}")
        else:
            lines.append("changed_files: none detected in hinted paths")

    if applied_details:
        lines.append("\nEdit log:\n" + applied_details)

    lines.append(f"\nbudget: {usage.get('by_date', {}).get(str(date.today()), 0)}/{_daily_limit()} today")
    return "\n".join(lines)


async def cursor_verify(paths: list[str] | None = None) -> str:
    """
    Verify the on-disk state after a cursor_edit call.

    With no paths   → diff every file in the most recent snapshot.
    With paths      → re-read those files and report sizes/excerpts plus
                      compare to snapshot if present.
    """
    snapshot_payload = _load_snapshot()
    snapshot = (snapshot_payload or {}).get("files", {})

    target_paths = _normalise_paths(paths or [])

    out_lines: list[str] = []
    if snapshot_payload:
        out_lines.append(
            f"[cursor_verify] snapshot from session {snapshot_payload.get('session_id') or '(none)'}"
            f" taken {snapshot_payload.get('taken_at', 'unknown')}"
        )

    if snapshot:
        diffs = _diff_against_snapshot(snapshot, extra_paths=target_paths)
        relevant = [d for d in diffs if d.status != "unchanged"]
        if relevant:
            out_lines.append("changes vs last snapshot:")
            for d in relevant[:80]:
                out_lines.append(f"  - {d.status}: {d.path}")
        else:
            out_lines.append("no changes detected vs last snapshot.")

    if target_paths:
        out_lines.append("\ncurrent state of requested paths:")
        for p in target_paths:
            if not p.exists():
                out_lines.append(f"  - missing: {p}")
                continue
            if p.is_dir():
                try:
                    children = sorted(c.name for c in p.iterdir())
                    out_lines.append(f"  - dir {p} ({len(children)} entries): {', '.join(children[:20])}")
                except OSError as e:
                    out_lines.append(f"  - dir {p}: error {e}")
                continue
            try:
                size = p.stat().st_size
                head = p.read_text(encoding="utf-8", errors="replace")[:600]
                out_lines.append(f"  - file {p} ({size} bytes):")
                for ln in head.splitlines()[:20]:
                    out_lines.append(f"      {ln}")
            except OSError as e:
                out_lines.append(f"  - file {p}: read error {e}")

    if not out_lines:
        return "[cursor_verify] no snapshot and no paths requested. Provide paths or call cursor_edit first."
    return "\n".join(out_lines)
