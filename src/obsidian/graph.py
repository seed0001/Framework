"""
In-memory vault graph — built from [[wikilinks]] in all markdown nodes.

Provides:
  VaultGraph.build()          — scan vault, build adjacency list
  VaultGraph.get_linked()     — BFS to N hops
  VaultGraph.get_clusters()   — connected-component summaries
  VaultGraph.get_bridges()    — nodes that connect otherwise isolated clusters
  VaultGraph.get_hubs()       — highest-degree nodes
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.obsidian.client import VaultClient

logger = logging.getLogger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(?:\|[^\]]+)?\]\]")


@dataclass
class Cluster:
    id: int
    members: list[str]
    hubs: list[str]          # highest-degree nodes in this cluster
    tags: list[str]          # union of tags found in member frontmatter


@dataclass
class VaultGraph:
    # path → set of linked paths (directed, but queried as undirected)
    edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # path → tags extracted from frontmatter
    node_tags: dict[str, list[str]] = field(default_factory=dict)
    # path → short title (first H1)
    node_titles: dict[str, str] = field(default_factory=dict)
    # timestamp of last build
    built_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #

    async def build(self, client: "VaultClient") -> None:
        """Scan all vault notes and rebuild the in-memory graph."""
        t0 = time.monotonic()
        new_edges: dict[str, set[str]] = defaultdict(set)
        new_tags: dict[str, list[str]] = {}
        new_titles: dict[str, str] = {}

        notes = await client.list_notes()
        for path in notes:
            content = await client.read_note(path)
            if not content:
                continue
            links = _WIKILINK_RE.findall(content)
            for lnk in links:
                target = lnk.strip().lower().replace(" ", "-")
                new_edges[path].add(target)

            new_tags[path] = _extract_tags(content)
            new_titles[path] = _extract_title(content, path)

        self.edges = new_edges
        self.node_tags = new_tags
        self.node_titles = new_titles
        self.built_at = time.monotonic()
        logger.info("vault graph built: %d nodes, %.1fs", len(notes), time.monotonic() - t0)

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    def get_linked(self, node_id: str, depth: int = 2) -> list[dict]:
        """
        BFS from *node_id* up to *depth* hops. Returns list of
        {path, distance, title, tags}.
        """
        node_id = node_id.lower()
        visited: dict[str, int] = {}  # path → distance
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        # Build undirected adjacency for traversal
        undirected: dict[str, set[str]] = defaultdict(set)
        for src, targets in self.edges.items():
            for tgt in targets:
                undirected[src].add(tgt)
                undirected[tgt].add(src)

        while queue:
            current, dist = queue.popleft()
            if current in visited:
                continue
            visited[current] = dist
            if dist < depth:
                for neighbor in undirected.get(current, set()):
                    if neighbor not in visited:
                        queue.append((neighbor, dist + 1))

        return [
            {
                "path": p,
                "distance": d,
                "title": self.node_titles.get(p, p.split("/")[-1]),
                "tags": self.node_tags.get(p, []),
            }
            for p, d in sorted(visited.items(), key=lambda x: x[1])
            if p != node_id
        ]

    def get_clusters(self) -> list[Cluster]:
        """
        Find connected components. Returns Cluster objects sorted by size desc.
        """
        # Build undirected adjacency
        undirected: dict[str, set[str]] = defaultdict(set)
        all_nodes: set[str] = set(self.edges.keys()) | {
            t for targets in self.edges.values() for t in targets
        }
        for src, targets in self.edges.items():
            for tgt in targets:
                undirected[src].add(tgt)
                undirected[tgt].add(src)

        visited: set[str] = set()
        clusters: list[Cluster] = []
        cluster_id = 0

        for start in all_nodes:
            if start in visited:
                continue
            # BFS
            component: list[str] = []
            q: deque[str] = deque([start])
            visited.add(start)
            while q:
                node = q.popleft()
                component.append(node)
                for neighbor in undirected.get(node, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        q.append(neighbor)

            # Score nodes by degree within component
            degree = {n: len(undirected.get(n, set()) & set(component)) for n in component}
            hubs = sorted(component, key=lambda n: degree[n], reverse=True)[:3]

            # Collect tags
            all_tags: list[str] = []
            for n in component:
                all_tags.extend(self.node_tags.get(n, []))
            tag_counts: dict[str, int] = {}
            for t in all_tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
            top_tags = sorted(tag_counts, key=tag_counts.get, reverse=True)[:5]  # type: ignore[arg-type]

            clusters.append(Cluster(
                id=cluster_id,
                members=sorted(component),
                hubs=hubs,
                tags=top_tags,
            ))
            cluster_id += 1

        return sorted(clusters, key=lambda c: len(c.members), reverse=True)

    def get_bridges(self) -> list[dict]:
        """
        Find nodes that connect clusters with 3+ members — emergent bridges.
        Returns [{node, cluster_a_size, cluster_b_size, title}] sorted by
        bridge importance.
        """
        clusters = self.get_clusters()
        # Only care about substantial clusters
        big = [c for c in clusters if len(c.members) >= 3]
        if len(big) < 2:
            return []

        # Map node → cluster id
        node_to_cluster: dict[str, int] = {}
        for c in big:
            for m in c.members:
                node_to_cluster[m] = c.id

        cluster_sizes: dict[int, int] = {c.id: len(c.members) for c in big}

        bridges: list[dict] = []
        for node, targets in self.edges.items():
            node_c = node_to_cluster.get(node)
            if node_c is None:
                continue
            connected_clusters: set[int] = {node_c}
            for t in targets:
                tc = node_to_cluster.get(t)
                if tc is not None:
                    connected_clusters.add(tc)
            if len(connected_clusters) >= 2:
                other_clusters = connected_clusters - {node_c}
                for oc in other_clusters:
                    bridges.append({
                        "node": node,
                        "cluster_a": node_c,
                        "cluster_b": oc,
                        "cluster_a_size": cluster_sizes.get(node_c, 0),
                        "cluster_b_size": cluster_sizes.get(oc, 0),
                        "title": self.node_titles.get(node, node.split("/")[-1]),
                        "score": cluster_sizes.get(node_c, 0) + cluster_sizes.get(oc, 0),
                    })

        return sorted(bridges, key=lambda b: b["score"], reverse=True)[:20]

    def get_hubs(self, top_n: int = 10) -> list[dict]:
        """Return the highest-degree nodes (most connections)."""
        degree: dict[str, int] = defaultdict(int)
        for src, targets in self.edges.items():
            degree[src] += len(targets)
            for t in targets:
                degree[t] += 1

        return [
            {
                "path": p,
                "degree": d,
                "title": self.node_titles.get(p, p.split("/")[-1]),
                "tags": self.node_tags.get(p, []),
            }
            for p, d in sorted(degree.items(), key=lambda x: x[1], reverse=True)[:top_n]
        ]

    def stats(self) -> dict:
        """Quick summary for the vault_query tool."""
        clusters = self.get_clusters()
        return {
            "total_nodes": len(self.node_titles),
            "total_edges": sum(len(v) for v in self.edges.values()),
            "clusters": len(clusters),
            "largest_cluster": len(clusters[0].members) if clusters else 0,
            "built_ago_seconds": int(time.monotonic() - self.built_at) if self.built_at else None,
        }


# ------------------------------------------------------------------ #
# Module-level singleton
# ------------------------------------------------------------------ #

_graph: VaultGraph = VaultGraph()
_build_lock = asyncio.Lock()


async def get_graph(client: "VaultClient", max_age_seconds: float = 300) -> VaultGraph:
    """
    Return the module-level graph, rebuilding it if stale.
    """
    age = time.monotonic() - _graph.built_at
    if age > max_age_seconds:
        async with _build_lock:
            age2 = time.monotonic() - _graph.built_at
            if age2 > max_age_seconds:
                try:
                    await _graph.build(client)
                except Exception as exc:
                    logger.warning("vault graph build failed: %s", exc)
    return _graph


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

_TAG_RE = re.compile(r"^tags:\s*\[(.+)\]", re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _extract_tags(content: str) -> list[str]:
    m = _TAG_RE.search(content)
    if not m:
        return []
    return [t.strip().strip("\"'") for t in m.group(1).split(",")]


def _extract_title(content: str, fallback: str) -> str:
    m = _H1_RE.search(content)
    if m:
        return m.group(1).strip()
    return fallback.split("/")[-1]
