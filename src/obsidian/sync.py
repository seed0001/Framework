"""
Bidirectional SQLite ↔ vault sync.

Called by the memory consolidator (and optionally decay hooks) when memory
state changes. Mirrors confidence updates and deprecations into vault nodes
so the markdown files stay truthful about the health of each memory.

All functions are async and never raise.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from src.obsidian.client import get_client
from src.obsidian.nodes import update_node_confidence

logger = logging.getLogger(__name__)


async def on_fact_consolidated(
    user_id: str,
    key: str,
    value: str,
    confidence: float,
    source: str = "consolidated",
) -> None:
    """
    When the consolidator extracts a new profile fact, write a reasoning/ node
    capturing it so the vault has a record.
    """
    try:
        from datetime import datetime, timezone
        from src.obsidian.nodes import _ts_prefix, _fm, _slug, _now_iso

        ts = _ts_prefix()
        slug = _slug(key, 40)
        path = f"reasoning/{ts}_fact-{slug}"
        client = get_client()

        fm = _fm({
            "id": f"fact_{ts}_{slug}",
            "type": "consolidated_fact",
            "memory_key": key,
            "source": source,
            "timestamp": _now_iso(),
            "confidence": round(confidence, 3),
            "tags": ["reasoning", "consolidated-fact"],
        })
        content = (
            f"{fm}\n\n"
            f"# Consolidated fact\n\n"
            f"**Key:** `{key}`\n\n"
            f"**Value:** {value}\n\n"
            f"**Confidence:** {confidence:.2f}\n"
        )
        await client.write_note(path, content)
        logger.debug("vault sync: wrote consolidated fact node %s", path)
    except Exception as exc:
        logger.debug("vault on_fact_consolidated silently failed: %s", exc)


async def on_fact_decayed(
    user_id: str,
    key: str,
    old_confidence: float,
    new_confidence: float,
    pruned: bool = False,
) -> None:
    """
    When a profile fact decays, find its vault node (if any) and update the
    confidence score. If the fact was pruned (below floor), mark #deprecated.
    """
    try:
        client = get_client()
        # We store facts by key slug in reasoning/fact-<slug>
        from src.obsidian.nodes import _slug
        slug = _slug(key, 40)

        # Find the most recent vault node for this key
        all_nodes = await client.list_notes("reasoning")
        matches = [p for p in all_nodes if f"fact-{slug}" in p]
        if not matches:
            return

        # Update the latest match
        latest = sorted(matches)[-1]
        content = await client.read_note(latest)
        if not content:
            return

        updated = update_node_confidence(
            content,
            new_confidence=round(new_confidence, 3),
            deprecated=pruned,
        )
        await client.write_note(latest, updated)
        logger.debug("vault sync: updated confidence for %s → %.3f", key, new_confidence)
    except Exception as exc:
        logger.debug("vault on_fact_decayed silently failed: %s", exc)


async def on_emergent_insight_found(
    user_id: str,
    insight: str,
    bridge: str,
    confidence: float,
) -> None:
    """
    When the emergence scanner finds an insight, write it into SQLite.
    (The emergence.py module handles this directly; this is the reverse path
    for anything that starts in SQLite and needs to surface to the vault.)
    """
    try:
        from src.agent.memory_stores import ProfileStore
        from src.obsidian.nodes import _slug
        store = ProfileStore(user_id)
        key = f"vault.emergent.{_slug(bridge, 32)}"
        store.set(
            key=key,
            value=insight,
            category="emergent",
            confidence=confidence,
            source="vault_emergent",
            protected=False,
        )
    except Exception as exc:
        logger.debug("vault on_emergent_insight_found silently failed: %s", exc)
