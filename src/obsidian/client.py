"""
Obsidian vault client.

Supports two modes, tried in order:
  1. Obsidian Local REST API (plugin) — richer search, live vault updates
  2. Direct filesystem writes — always works, Obsidian picks up changes on disk

All public methods are async and never raise; they return None / [] / False on
failure so callers don't need try/except everywhere.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_httpx_ok = False
try:
    import httpx  # type: ignore
    _httpx_ok = True
except ImportError:
    pass


class VaultClient:
    """Thin wrapper around the vault directory + optional REST API."""

    def __init__(self, vault_dir: Path, api_url: str = "", api_key: str = "") -> None:
        self.vault_dir = vault_dir
        self._api_url = api_url.rstrip("/") if api_url else ""
        self._api_key = api_key
        self._api_available: bool | None = None   # None = unchecked
        self._api_check_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "text/markdown"}
        if self._api_key:
            h["Authorization"] = f"ApiKey {self._api_key}"
        return h

    async def _api_ok(self) -> bool:
        """Lazy-check whether the REST API is reachable."""
        if not (_httpx_ok and self._api_url and self._api_key):
            return False
        if self._api_available is not None:
            return self._api_available
        async with self._api_check_lock:
            if self._api_available is not None:
                return self._api_available
            try:
                async with httpx.AsyncClient(timeout=2.0) as c:
                    r = await c.get(f"{self._api_url}/", headers=self._headers())
                    self._api_available = r.status_code < 500
            except Exception:
                self._api_available = False
            return self._api_available  # type: ignore[return-value]

    def _abs(self, vault_path: str) -> Path:
        """Resolve a vault-relative path to absolute."""
        p = vault_path.lstrip("/")
        if not p.endswith(".md"):
            p += ".md"
        return self.vault_dir / p

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #

    async def write_note(self, vault_path: str, content: str) -> bool:
        """Write (create or overwrite) a markdown note. Returns True on success."""
        abs_p = self._abs(vault_path)
        try:
            abs_p.parent.mkdir(parents=True, exist_ok=True)
            abs_p.write_text(content, encoding="utf-8")
        except Exception as exc:
            logger.warning("vault write_note filesystem error %s: %s", vault_path, exc)
            return False

        # Best-effort REST API notification (keeps the live graph current)
        if await self._api_ok():
            try:
                async with httpx.AsyncClient(timeout=5.0) as c:
                    await c.put(
                        f"{self._api_url}/vault/{vault_path.lstrip('/')}",
                        headers=self._headers(),
                        content=content.encode(),
                    )
            except Exception:
                pass  # filesystem write already succeeded

        return True

    async def append_note(self, vault_path: str, content: str) -> bool:
        """Append content to an existing note (or create it)."""
        abs_p = self._abs(vault_path)
        try:
            existing = abs_p.read_text(encoding="utf-8") if abs_p.exists() else ""
            return await self.write_note(vault_path, existing + "\n" + content)
        except Exception as exc:
            logger.warning("vault append_note error %s: %s", vault_path, exc)
            return False

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #

    async def read_note(self, vault_path: str) -> str | None:
        abs_p = self._abs(vault_path)
        try:
            if abs_p.exists():
                return abs_p.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("vault read_note error %s: %s", vault_path, exc)
        return None

    async def list_notes(self, folder: str = "") -> list[str]:
        """Return vault-relative paths of all .md files under *folder*."""
        base = self.vault_dir / folder if folder else self.vault_dir
        if not base.exists():
            return []
        try:
            return [
                str(p.relative_to(self.vault_dir)).replace("\\", "/").removesuffix(".md")
                for p in sorted(base.rglob("*.md"))
            ]
        except Exception as exc:
            logger.warning("vault list_notes error: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Search the vault. Tries the REST API first; falls back to a simple
        filesystem keyword scan.
        """
        if await self._api_ok():
            try:
                async with httpx.AsyncClient(timeout=8.0) as c:
                    r = await c.get(
                        f"{self._api_url}/search/simple/",
                        params={"query": query, "contextLength": 200},
                        headers=self._headers(),
                    )
                    if r.status_code == 200:
                        raw = r.json()
                        results = []
                        for item in (raw if isinstance(raw, list) else []):
                            results.append({
                                "path": item.get("filename", ""),
                                "score": item.get("score", 0),
                                "excerpt": _first_match(item.get("matches", []), query),
                            })
                        return results[:limit]
            except Exception as exc:
                logger.debug("vault REST search failed, falling back: %s", exc)

        return await self._fs_search(query, limit)

    async def _fs_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Naive filesystem keyword search."""
        keywords = set(re.findall(r"\w+", query.lower()))
        if not keywords:
            return []

        results: list[tuple[int, str, str]] = []
        notes = await self.list_notes()
        for path in notes:
            try:
                content = (self.vault_dir / (path + ".md")).read_text(encoding="utf-8", errors="replace")
                words = set(re.findall(r"\w+", content.lower()))
                score = len(keywords & words)
                if score:
                    excerpt = _extract_excerpt(content, next(iter(keywords & words)), 150)
                    results.append((score, path, excerpt))
            except Exception:
                continue

        results.sort(key=lambda x: x[0], reverse=True)
        return [{"path": p, "score": s, "excerpt": e} for s, p, e in results[:limit]]

    # ------------------------------------------------------------------ #
    # Delete / archive
    # ------------------------------------------------------------------ #

    async def delete_note(self, vault_path: str) -> bool:
        abs_p = self._abs(vault_path)
        try:
            if abs_p.exists():
                abs_p.unlink()
            return True
        except Exception as exc:
            logger.warning("vault delete_note error %s: %s", vault_path, exc)
            return False


# ------------------------------------------------------------------ #
# Module-level singleton (lazy)
# ------------------------------------------------------------------ #

_client: VaultClient | None = None


def get_client() -> VaultClient:
    global _client
    if _client is None:
        from config.settings import OBSIDIAN_VAULT_DIR, OBSIDIAN_URL, OBSIDIAN_API_KEY
        _client = VaultClient(
            vault_dir=OBSIDIAN_VAULT_DIR,
            api_url=OBSIDIAN_URL,
            api_key=OBSIDIAN_API_KEY,
        )
    return _client


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _first_match(matches: list, query: str) -> str:
    if matches:
        m = matches[0]
        if isinstance(m, dict):
            return m.get("context", "")[:200]
    return ""


def _extract_excerpt(text: str, keyword: str, length: int) -> str:
    lower = text.lower()
    idx = lower.find(keyword)
    if idx == -1:
        return text[:length]
    start = max(0, idx - 60)
    return text[start: start + length]
