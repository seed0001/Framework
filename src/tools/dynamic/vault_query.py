"""
vault_query — Obsidian vault interface for Andrew's reasoning loop.

Actions:
  search      — semantic/keyword search across all vault nodes
  get_linked  — BFS from a node up to N hops
  get_clusters— summary of current knowledge graph clusters
  get_bridges — nodes that unexpectedly connect isolated concept clusters
  get_hubs    — highest-degree nodes (most-connected concepts)
  ingest      — write a custom node from runtime data
  stats       — vault graph statistics

Use this when asked about past knowledge, cross-topic connections, or
pattern discovery. Do NOT use it for direct memory retrieval (use
search_knowledge for that) — this is for graph traversal and emergence.
"""
from __future__ import annotations

import json

TOOL_DEF = {
    "name": "vault_query",
    "description": (
        "Query and write to the Obsidian cognitive knowledge graph vault. "
        "Use 'search' to find related past nodes by keyword or concept. "
        "Use 'get_linked' to traverse the knowledge graph from a known node. "
        "Use 'get_clusters' to see what conceptual clusters have formed. "
        "Use 'get_bridges' to discover unexpected cross-domain connections. "
        "Use 'get_hubs' to find the most-connected concepts in the vault. "
        "Use 'ingest' to write a new node from runtime data. "
        "Use 'stats' for a quick graph summary."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "get_linked", "get_clusters", "get_bridges", "get_hubs", "ingest", "stats"],
                "description": "Operation to perform.",
            },
            "query": {
                "type": "string",
                "description": "Search query string. Required for 'search'.",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum results to return for 'search'. Default 8.",
            },
            "node_id": {
                "type": "string",
                "description": "Vault-relative path of the node for 'get_linked'. E.g. 'index/memory'.",
            },
            "depth": {
                "type": "integer",
                "description": "BFS hop depth for 'get_linked'. Default 2, max 4.",
            },
            "data": {
                "type": "string",
                "description": "Content to write for 'ingest'. Plain text or markdown.",
            },
            "source_type": {
                "type": "string",
                "enum": ["reasoning", "observation", "fact", "question"],
                "description": "Node type for 'ingest'. Default 'reasoning'.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional tags for 'ingest'.",
            },
        },
        "required": ["action"],
    },
}


async def run(**kwargs) -> str:
    action = (kwargs.get("action") or "search").lower().strip()

    try:
        from src.obsidian.client import get_client
        from src.obsidian.graph import get_graph
        client = get_client()

        # ── SEARCH ──────────────────────────────────────────────────
        if action == "search":
            query = kwargs.get("query", "").strip()
            if not query:
                return "ERROR: 'query' is required for search."
            top_k = min(int(kwargs.get("top_k") or 8), 20)
            results = await client.search(query, limit=top_k)
            if not results:
                return "No vault nodes matched your query."
            lines = [f"Vault search: '{query}' — {len(results)} results\n"]
            for r in results:
                title = r["path"].split("/")[-1]
                excerpt = r.get("excerpt", "")[:120]
                lines.append(f"• [{title}]({r['path']})  score={r['score']}")
                if excerpt:
                    lines.append(f"  > {excerpt}")
            return "\n".join(lines)

        # ── GET_LINKED ───────────────────────────────────────────────
        if action == "get_linked":
            node_id = (kwargs.get("node_id") or "").strip()
            if not node_id:
                return "ERROR: 'node_id' is required for get_linked."
            depth = max(1, min(int(kwargs.get("depth") or 2), 4))
            graph = await get_graph(client)
            linked = graph.get_linked(node_id, depth=depth)
            if not linked:
                return f"No linked nodes found for '{node_id}' within {depth} hops."
            lines = [f"Linked nodes from '{node_id}' (depth={depth}):\n"]
            for n in linked[:25]:
                lines.append(
                    f"  {'·' * n['distance']} [{n['title']}]({n['path']}) "
                    f"(hop {n['distance']}, tags: {', '.join(n['tags'][:3])})"
                )
            return "\n".join(lines)

        # ── GET_CLUSTERS ─────────────────────────────────────────────
        if action == "get_clusters":
            graph = await get_graph(client)
            clusters = graph.get_clusters()
            if not clusters:
                return "Vault graph has no clusters yet (too few nodes)."
            lines = [f"Knowledge graph: {len(clusters)} clusters\n"]
            for c in clusters[:10]:
                hub_names = ", ".join(n.split("/")[-1] for n in c.hubs[:3])
                lines.append(
                    f"  Cluster {c.id}: {len(c.members)} nodes | "
                    f"hubs=[{hub_names}] | tags={c.tags[:3]}"
                )
            return "\n".join(lines)

        # ── GET_BRIDGES ──────────────────────────────────────────────
        if action == "get_bridges":
            graph = await get_graph(client)
            bridges = graph.get_bridges()
            if not bridges:
                return "No bridge nodes found. Vault may not have enough clusters yet."
            lines = [f"Bridge nodes (cross-cluster connectors): {len(bridges)} found\n"]
            for b in bridges[:8]:
                lines.append(
                    f"  [{b['title']}]({b['node']}) — "
                    f"connects cluster {b['cluster_a']} ({b['cluster_a_size']} nodes) ↔ "
                    f"cluster {b['cluster_b']} ({b['cluster_b_size']} nodes)"
                )
            return "\n".join(lines)

        # ── GET_HUBS ─────────────────────────────────────────────────
        if action == "get_hubs":
            graph = await get_graph(client)
            hubs = graph.get_hubs(top_n=10)
            if not hubs:
                return "No hub nodes found yet."
            lines = ["Top hub nodes (most-connected concepts):\n"]
            for h in hubs:
                lines.append(
                    f"  [{h['title']}]({h['path']}) — degree {h['degree']}, "
                    f"tags: {', '.join(h['tags'][:3])}"
                )
            return "\n".join(lines)

        # ── INGEST ───────────────────────────────────────────────────
        if action == "ingest":
            data = (kwargs.get("data") or "").strip()
            if not data:
                return "ERROR: 'data' is required for ingest."
            source_type = (kwargs.get("source_type") or "reasoning").strip()
            extra_tags = list(kwargs.get("tags") or [])

            from src.obsidian.nodes import _ts_prefix, _fm, _now_iso, extract_wikilinks, _wikilink_section
            from config.settings import active_user_id

            ts = _ts_prefix()
            user_id = active_user_id.get("default")
            sid = f"manual-{user_id}"
            path = f"reasoning/{ts}_ingest-{source_type}"

            tags = [source_type, "manual-ingest"] + extra_tags
            fm = _fm({
                "id": f"ingest_{ts}",
                "type": source_type,
                "timestamp": _now_iso(),
                "source": "vault_query_tool",
                "confidence": 0.9,
                "tags": tags,
            })
            wikilinks = extract_wikilinks(data)
            content = (
                f"{fm}\n\n"
                f"# Ingested: {source_type}\n\n"
                f"{data}\n"
                f"{_wikilink_section(wikilinks)}"
            )
            ok = await client.write_note(path, content)
            return f"Ingested node written: {path}" if ok else "ERROR: Failed to write vault node."

        # ── STATS ────────────────────────────────────────────────────
        if action == "stats":
            graph = await get_graph(client)
            s = graph.stats()
            return (
                f"Vault graph stats:\n"
                f"  Nodes:           {s['total_nodes']}\n"
                f"  Edges:           {s['total_edges']}\n"
                f"  Clusters:        {s['clusters']}\n"
                f"  Largest cluster: {s['largest_cluster']} nodes\n"
                f"  Graph age:       {s['built_ago_seconds']}s\n"
                f"  Vault dir:       {client.vault_dir}"
            )

        return f"ERROR: Unknown action '{action}'."

    except Exception as exc:
        return f"ERROR: vault_query failed — {exc}"
