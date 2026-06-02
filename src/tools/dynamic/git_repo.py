"""
git_repo.py — clone and manage Git repositories.

Exposes the `git_repo` tool so the agent can pull repos from GitHub (or any
Git remote) without falling back to a web search.

Supported actions:
    clone   — git clone <url> [dest]
    pull    — git pull inside an existing repo directory
    status  — git status inside a repo directory
    log     — recent commit log for a repo directory

URL formats accepted for clone:
    https://github.com/owner/repo
    github.com/owner/repo
    owner/repo              (expanded to https://github.com/owner/repo)
    git@github.com:owner/repo.git
"""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

TOOL_DEF = {
    "name": "git_repo",
    "description": (
        "Clone a Git repository from GitHub or any remote URL, or run git "
        "pull / status / log on an existing local repo. "
        "Use this whenever Travis asks to clone, pull, or fetch a repo. "
        "For clone, accepts full URLs (https://github.com/owner/repo), "
        "short 'owner/repo' notation, or SSH URLs. "
        "Clones into a destination directory on disk; defaults to the Desktop."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["clone", "pull", "status", "log"],
                "description": (
                    "clone — download a repo for the first time. "
                    "pull  — fetch and merge latest changes in an existing local repo. "
                    "status — show working-tree status. "
                    "log   — show recent commits."
                ),
            },
            "url": {
                "type": "string",
                "description": (
                    "Remote URL or 'owner/repo' shorthand. Required for clone. "
                    "Examples: 'https://github.com/anthropics/claude-code', "
                    "'torvalds/linux', 'git@github.com:owner/repo.git'."
                ),
            },
            "dest": {
                "type": "string",
                "description": (
                    "Local path where the repo should be cloned. "
                    "Optional for clone — defaults to ~/Desktop/<repo-name>. "
                    "Required for pull / status / log (the existing repo directory)."
                ),
            },
            "branch": {
                "type": "string",
                "description": "Branch to clone (passed as --branch). Optional.",
            },
            "depth": {
                "type": "integer",
                "description": "Shallow clone depth (e.g. 1 for latest commit only). Optional.",
            },
        },
        "required": ["action"],
    },
}


def _normalize_url(raw: str) -> str:
    """Turn short 'owner/repo' or 'github.com/owner/repo' into a full HTTPS URL."""
    raw = raw.strip()
    if raw.startswith("git@") or raw.startswith("https://") or raw.startswith("http://"):
        return raw
    # github.com/owner/repo  →  prepend https://
    if raw.startswith("github.com/"):
        return "https://" + raw
    # owner/repo  →  assume GitHub
    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", raw):
        return f"https://github.com/{raw}"
    # Anything else: return as-is and let git complain
    return raw


def _repo_name_from_url(url: str) -> str:
    """Extract 'repo' from any remote URL format."""
    # Strip .git suffix
    name = url.rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    return name.split("/")[-1].split(":")[-1]


def _default_dest(url: str) -> Path:
    desktop = Path.home() / "Desktop"
    return desktop / _repo_name_from_url(url)


async def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a subprocess and return (returncode, combined stdout+stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
    )
    stdout, stderr = await proc.communicate()
    combined = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
    return proc.returncode, combined


async def run(**kwargs) -> str:
    action = (kwargs.get("action") or "clone").lower().strip()

    # ── Validate git is available ──────────────────────────────────────────
    if not shutil.which("git"):
        return "ERROR: git is not installed or not on PATH. Install Git first."

    # ── CLONE ──────────────────────────────────────────────────────────────
    if action == "clone":
        url_raw = kwargs.get("url", "").strip()
        if not url_raw:
            return "ERROR: 'url' is required for clone."

        url = _normalize_url(url_raw)
        dest_str = kwargs.get("dest", "")
        dest = Path(dest_str).expanduser().resolve() if dest_str else _default_dest(url)

        if dest.exists():
            return (
                f"Directory already exists: {dest}\n"
                f"If you want to update it, use action='pull' with dest='{dest}'."
            )

        cmd = ["git", "clone"]
        branch = kwargs.get("branch", "")
        depth = kwargs.get("depth")
        if branch:
            cmd += ["--branch", branch]
        if depth and int(depth) > 0:
            cmd += ["--depth", str(int(depth))]
        cmd += [url, str(dest)]

        rc, out = await _run(cmd)
        if rc == 0:
            return (
                f"Cloned successfully.\n"
                f"  Remote : {url}\n"
                f"  Local  : {dest}\n"
                + (f"\n{out}" if out else "")
            )
        else:
            return f"Clone failed (exit {rc}):\n{out}"

    # ── PULL ───────────────────────────────────────────────────────────────
    if action == "pull":
        dest_str = kwargs.get("dest", "")
        if not dest_str:
            return "ERROR: 'dest' (local repo path) is required for pull."
        dest = Path(dest_str).expanduser().resolve()
        if not (dest / ".git").exists():
            return f"ERROR: '{dest}' is not a git repository (no .git directory found)."

        rc, out = await _run(["git", "pull"], cwd=dest)
        if rc == 0:
            return f"Pull complete in {dest}:\n{out}"
        else:
            return f"Pull failed (exit {rc}) in {dest}:\n{out}"

    # ── STATUS ─────────────────────────────────────────────────────────────
    if action == "status":
        dest_str = kwargs.get("dest", "")
        if not dest_str:
            return "ERROR: 'dest' (local repo path) is required for status."
        dest = Path(dest_str).expanduser().resolve()
        if not (dest / ".git").exists():
            return f"ERROR: '{dest}' is not a git repository."

        rc, out = await _run(["git", "status"], cwd=dest)
        return out if out else "No output from git status."

    # ── LOG ────────────────────────────────────────────────────────────────
    if action == "log":
        dest_str = kwargs.get("dest", "")
        if not dest_str:
            return "ERROR: 'dest' (local repo path) is required for log."
        dest = Path(dest_str).expanduser().resolve()
        if not (dest / ".git").exists():
            return f"ERROR: '{dest}' is not a git repository."

        rc, out = await _run(
            ["git", "log", "--oneline", "--decorate", "-20"],
            cwd=dest,
        )
        return out if out else "No commits found."

    return f"ERROR: Unknown action '{action}'. Use clone, pull, status, or log."
