"""
Emergence scanner — finds unexpected connections in the vault graph.

Algorithm:
  1. Build (or reuse) the in-memory VaultGraph.
  2. Find bridge nodes — nodes that link clusters which share no other connection.
  3. For each bridge, generate a human-readable insight string.
  4. Write emergent/ nodes back into the vault.
  5. Mirror the top insights back into the agent's SQLite profile as
     source="vault_emergent" facts so they appear in Andrew's context.

The scanner is intentionally lightweight — no external LLM call for pattern
detection. Insight prose is generated from the graph topology alone.
The SQLite mirror is what makes emergence "visible" to Andrew during reasoning.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from src.obsidian.client import get_client
from src.obsidian.graph import VaultGraph, get_graph
from src.obsidian.nodes import build_emergent_node, _slug

logger = logging.getLogger(__name__)

# Minimum cluster size to count as "substantial" for bridge detection
_MIN_CLUSTER_SIZE = 3
# Maximum bridge insights written per scan
_MAX_INSIGHTS = 5
# Seconds between emergence scans (independent of consolidator interval)
_SCAN_COOLDOWN = 1800  # 30 min


@dataclass
class EmergentInsight:
    bridge_node: str
    bridge_title: str
    cluster_a_tags: list[str]
    cluster_b_tags: list[str]
    cluster_a_hubs: list[str]
    cluster_b_hubs: list[str]
    insight_text: str
    score: int


_last_scan: float = 0.0
_scan_lock = asyncio.Lock()


async def run_scan(user_id: str = "default", force: bool = False) -> list[EmergentInsight]:
    """
    Run an emergence scan. Returns the insights found.
    Throttled to _SCAN_COOLDOWN unless *force=True*.
    """
    global _last_scan
    now = time.monotonic()
    if not force and (now - _last_scan) < _SCAN_COOLDOWN:
        logger.debug("emergence scan skipped (cooldown)")
        return []

    async with _scan_lock:
        now = time.monotonic()
        if not force and (now - _last_scan) < _SCAN_COOLDOWN:
            return []

        logger.info("emergence scan starting for user=%s", user_id)
        try:
            insights = await _do_scan(user_id)
            _last_scan = time.monotonic()
            return insights
        except Exception as exc:
            logger.warning("emergence scan failed: %s", exc)
            return []


async def _do_scan(user_id: str) -> list[EmergentInsight]:
    client = get_client()
    graph = await get_graph(client, max_age_seconds=60)  # force fresh build for scan

    bridges = graph.get_bridges()
    if not bridges:
        logger.info("emergence: no bridges found")
        return []

    clusters = {c.id: c for c in graph.get_clusters()}
    insights: list[EmergentInsight] = []

    for bridge in bridges[:_MAX_INSIGHTS * 2]:  # over-fetch, filter below
        ca = clusters.get(bridge["cluster_a"])
        cb = clusters.get(bridge["cluster_b"])
        if not ca or not cb:
            continue
        if len(ca.members) < _MIN_CLUSTER_SIZE or len(cb.members) < _MIN_CLUSTER_SIZE:
            continue

        insight_text = _generate_insight(bridge["title"], ca, cb, bridge["score"])
        insights.append(EmergentInsight(
            bridge_node=bridge["node"],
            bridge_title=bridge["title"],
            cluster_a_tags=ca.tags,
            cluster_b_tags=cb.tags,
            cluster_a_hubs=ca.hubs[:3],
            cluster_b_hubs=cb.hubs[:3],
            insight_text=insight_text,
            score=bridge["score"],
        ))
        if len(insights) >= _MAX_INSIGHTS:
            break

    # Write nodes and SQLite mirror
    for ins in insights:
        await _write_insight(client, ins)
        await _mirror_to_sqlite(user_id, ins)

    if insights:
        logger.info("emergence: discovered %d insights", len(insights))

    return insights


def _generate_insight(bridge: str, ca, cb, score: int) -> str:
    """
    Generate a plain-English insight string from graph topology.
    Deliberately avoids LLM calls — topology speaks for itself.
    """
    a_theme = ca.tags[0] if ca.tags else "unknown"
    b_theme = cb.tags[0] if cb.tags else "unknown"
    a_size = len(ca.members)
    b_size = len(cb.members)

    if a_theme == b_theme:
        return (
            f"'{bridge}' bridges two separate {a_theme} clusters "
            f"({a_size} and {b_size} nodes) that otherwise have no connection. "
            "This may indicate an implicit relationship worth exploring."
        )
    return (
        f"'{bridge}' unexpectedly connects a {a_theme} cluster ({a_size} nodes) "
        f"to a {b_theme} cluster ({b_size} nodes). "
        "Cross-domain bridge — potential emergent pattern."
    )


async def _write_insight(client, ins: EmergentInsight) -> None:
    try:
        path, content = build_emergent_node(
            insight=ins.insight_text,
            bridge_node=ins.bridge_title,
            cluster_a=ins.cluster_a_hubs,
            cluster_b=ins.cluster_b_hubs,
            confidence=_score_to_confidence(ins.score),
        )
        await client.write_note(path, content)
        logger.debug("vault: wrote emergent node %s", path)
    except Exception as exc:
        logger.warning("vault write emergent node failed: %s", exc)


async def _mirror_to_sqlite(user_id: str, ins: EmergentInsight) -> None:
    """
    Write the insight into Andrew's profile facts so it appears in context.
    Key format:  vault.emergent.<bridge_slug>
    """
    try:
        from src.agent.memory_stores import ProfileStore
        store = ProfileStore(user_id)
        key = f"vault.emergent.{_slug(ins.bridge_node, 32)}"
        store.set(
            key=key,
            value=ins.insight_text,
            category="emergent",
            confidence=_score_to_confidence(ins.score),
            source="vault_emergent",
            protected=False,
        )
        logger.debug("vault: mirrored emergent insight → sqlite key=%s", key)
    except Exception as exc:
        logger.warning("vault sqlite mirror failed: %s", exc)


def _score_to_confidence(score: int) -> float:
    # score = sum of two cluster sizes; cap at 1.0
    return min(0.95, 0.5 + score * 0.01)
