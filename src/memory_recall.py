"""Unified recall helpers across profile, schedules, artifacts, contacts, and episodic memory."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src import contacts
from src.agent.memory_db import db_path
from src.artifact_memory import format_artifact, search_artifacts
from src.schedule_memory import format_schedule, list_schedules


# ── Legacy shape (kept for backward compat) ───────────────────────────────────

@dataclass
class RecallHit:
    source: str
    title: str
    content: str
    score: int = 1


# ── Structured recall result ──────────────────────────────────────────────────

@dataclass
class RecallResult:
    """A single ranked memory returned by :func:`recall`.

    Attributes:
        source:    Where this came from — ``"episodic"``, ``"profile"``,
                   ``"artifact"``, ``"schedule"``, or ``"contact"``.
        title:     Short label (timestamp, category, artifact name, …).
        content:   The raw text content of the memory.
        score:     Relevance score normalised to ``[0.0, 1.0]``.
        timestamp: ISO-8601 string when the memory was created, if known.
        metadata:  Extra key/value pairs (role, session_id, confidence, …).
    """

    source: str
    title: str
    content: str
    score: float = 0.5
    timestamp: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _words(query: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-zA-Z0-9']{3,}", query or "")}


def _score(query_words: set[str], text: str) -> int:
    blob = (text or "").lower()
    return sum(1 for w in query_words if w in blob)


def _kw_norm(q_words: set[str], text: str) -> float:
    """Keyword overlap ratio in [0, 1]."""
    if not q_words:
        return 0.0
    hits = sum(1 for w in q_words if w in (text or "").lower())
    return min(1.0, hits / len(q_words))


def _recency_score(timestamp_iso: str | None, decay_days: float = 30.0) -> float:
    """Linear recency bonus in [0, 1], full score = today, zero = decay_days ago."""
    if not timestamp_iso:
        return 0.5
    try:
        dt_str = (timestamp_iso or "").replace("T", " ")
        dt = datetime.fromisoformat(dt_str)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        days_ago = max(0.0, (now - dt).total_seconds() / 86400.0)
        return max(0.0, 1.0 - days_ago / decay_days)
    except (ValueError, OSError):
        return 0.5


# ── Public recall() API ───────────────────────────────────────────────────────

def recall(
    query: str,
    *,
    top_k: int = 5,
    mode: str = "episodic",
    user_id: str = "default",
) -> list[RecallResult]:
    """Return the top-*k* ranked memories relevant to *query*.

    Args:
        query:   Free-text search query.
        top_k:   Maximum number of results to return.
        mode:    ``"episodic"`` (default) — lexical keyword + recency +
                 importance scoring on stored conversation turns and profile
                 facts.  ``"semantic"`` — cosine similarity via
                 :class:`~src.agent.memory_embeddings.SemanticIndex`; falls
                 back gracefully to ``"episodic"`` when the embedding service
                 is unavailable.
        user_id: Which profile's SQLite database to query.

    Returns:
        List of :class:`RecallResult` sorted descending by score.

    Example:
        >>> results = recall("what did we discuss about the project?", top_k=3)
        >>> [r.source for r in results]  # ['episodic', 'episodic', 'profile']
    """
    if mode == "semantic":
        return _recall_semantic(query, top_k=top_k, user_id=user_id)
    return _recall_episodic(query, top_k=top_k, user_id=user_id)


def format_recall_for_prompt(
    results: list[RecallResult],
    header: str = "## Recalled memory",
    max_content_chars: int = 400,
) -> str:
    """Format *results* as a prompt-ready Markdown block.

    Returns an empty string when *results* is empty so callers can gate on
    truthiness without an extra ``if``.

    Example:
        >>> block = format_recall_for_prompt(results, header="## Past context")
        >>> block.startswith("## Past context") or block == ""
        True
    """
    if not results:
        return ""
    lines = [header]
    for r in results:
        ts = f"[{r.timestamp}] " if r.timestamp else ""
        snippet = r.content[:max_content_chars].replace("\n", " ")
        label = f"(score {r.score:.2f})"
        lines.append(f"- {ts}{r.source}: {snippet} {label}")
    return "\n".join(lines)


# ── Episodic recall (lexical + recency + importance) ──────────────────────────

def _recall_episodic(query: str, top_k: int, user_id: str) -> list[RecallResult]:
    q_words = _words(query)
    if not q_words:
        return []

    path = db_path(user_id)
    if not path.exists():
        return []

    results: list[RecallResult] = []

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        # Pull a window of recent turns — score client-side so we can combine
        # keyword overlap with recency and importance without a heavyweight FTS.
        rows = con.execute(
            "SELECT id, session_id, role, content, importance, created_at "
            "FROM episodic_memory "
            "WHERE deleted_at IS NULL "
            "ORDER BY created_at DESC "
            "LIMIT 300",
        ).fetchall()

        for row in rows:
            content = row["content"] or ""
            kw = _kw_norm(q_words, content)
            if kw == 0.0:
                continue
            recency = _recency_score(row["created_at"])
            importance = float(row["importance"] or 0.5)
            # Weighted: keyword overlap dominates, recency and importance nudge
            combined = 0.55 * kw + 0.25 * recency + 0.20 * importance
            results.append(
                RecallResult(
                    source="episodic",
                    title=row["created_at"] or "",
                    content=content,
                    score=round(combined, 4),
                    timestamp=row["created_at"],
                    metadata={
                        "role": row["role"],
                        "session_id": row["session_id"],
                        "importance": importance,
                    },
                )
            )

        # Profile facts — high confidence facts are very relevant
        fact_rows = con.execute(
            "SELECT key, value, category, confidence "
            "FROM profile_facts "
            "WHERE deleted_at IS NULL "
            "ORDER BY confidence DESC "
            "LIMIT 100",
        ).fetchall()
        for row in fact_rows:
            text = f"{row['value']} {row['key']} {row['category']}"
            kw = _kw_norm(q_words, text)
            if kw == 0.0:
                continue
            conf = float(row["confidence"] or 0.5)
            combined = round(0.50 * kw + 0.50 * conf, 4)
            results.append(
                RecallResult(
                    source="profile",
                    title=row["category"] or "profile",
                    content=f"{row['category']}: {row['value']}",
                    score=combined,
                    metadata={"key": row["key"], "confidence": conf},
                )
            )

    finally:
        con.close()

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]


# ── Semantic recall (embedding cosine similarity) ─────────────────────────────

def _recall_semantic(query: str, top_k: int, user_id: str) -> list[RecallResult]:
    try:
        from src.agent.memory_embeddings import SemanticIndex

        idx = SemanticIndex(user_id)
        if not idx.service.is_available:
            return _recall_episodic(query, top_k=top_k, user_id=user_id)
        hits = idx.find_similar_text(query, limit=top_k, source_table="episodic_memory")
        if not hits:
            return _recall_episodic(query, top_k=top_k, user_id=user_id)
        return [
            RecallResult(
                source="episodic_semantic",
                title=h.source_id,
                content=h.content,
                score=round(float(h.score), 4),
                metadata={"embedding_id": h.embedding_id},
            )
            for h in hits
        ]
    except Exception:
        return _recall_episodic(query, top_k=top_k, user_id=user_id)


# ── Legacy search_memory() — unchanged ───────────────────────────────────────

def search_memory(query: str, *, user_id: str = "default", limit: int = 12) -> str:
    """Search across all memory sources and return a formatted string.

    This is the legacy interface used by the agent's tool layer.  New code
    should prefer :func:`recall` which returns structured :class:`RecallResult`
    objects with scores.
    """
    q_words = _words(query)
    hits: list[RecallHit] = []

    for sched in list_schedules(include_archived=False):
        content = format_schedule(sched)
        score = _score(q_words, content)
        if score:
            hits.append(RecallHit("schedule", sched.title, content, score))

    for art in search_artifacts(query, limit=limit):
        content = format_artifact(art)
        hits.append(RecallHit("artifact", art.title, content, _score(q_words, content) or 1))

    for contact in contacts.get_all_contacts():
        content = "\n".join(f"{k}: {v}" for k, v in contact.items() if not k.startswith("_"))
        score = _score(q_words, content)
        if score:
            hits.append(
                RecallHit(
                    "contact",
                    contact.get("name") or contact.get("id", "contact"),
                    content,
                    score,
                )
            )

    path = db_path(user_id)
    if path.exists():
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        try:
            like = f"%{query}%"
            rows = con.execute(
                "select created_at, role, content from episodic_memory "
                "where content like ? order by created_at desc limit ?",
                (like, limit),
            ).fetchall()
            for row in rows:
                content = f"{row['created_at']} {row['role']}: {row['content']}"
                hits.append(RecallHit("episodic", row["created_at"], content, 1))

            rows = con.execute(
                "select category, value, confidence from profile_facts "
                "where deleted_at is null and value like ? order by confidence desc limit ?",
                (like, limit),
            ).fetchall()
            for row in rows:
                content = f"{row['category']}: {row['value']} (confidence {row['confidence']:.2f})"
                hits.append(RecallHit("profile", row["category"], content, 2))
        finally:
            con.close()

    hits.sort(key=lambda h: h.score, reverse=True)
    if not hits:
        return f"No memory matches for: {query}"

    lines = [f"Memory search results for: {query}"]
    for hit in hits[:limit]:
        lines.append(f"\n[{hit.source}] {hit.title}\n{hit.content[:1200]}")
    return "\n".join(lines)
