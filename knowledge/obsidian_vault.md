# Obsidian Vault — Cognitive Knowledge Graph

The vault is an Obsidian markdown graph that runs alongside the SQLite memory
system. It is NOT a documentation store. It is an **emergent pattern discovery
layer** that Andrew actively queries during reasoning.

---

## What it is

Every conversation turn, tool execution, and consolidated memory fact is written
as an atomic markdown node into the vault. Nodes contain `[[wikilinks]]` to
related concepts. Over time, a navigable knowledge graph grows — and the
emergence scanner finds unexpected connections between otherwise isolated topics.

---

## Vault structure

| Folder | Contents |
|--------|----------|
| `conversations/` | One node per agent turn — user message + Andrew's reply + tools used |
| `tools/` | One node per tool execution — name, args, result, error status |
| `reasoning/` | Consolidated profile facts extracted from episodic memory |
| `emergent/` | Bridge nodes discovered by the emergence scanner |
| `index/` | Concept aggregator nodes — hub pages that collect links to related entries |

---

## How to use it (during reasoning)

Use `vault_query` tool. Actions:

| Action | What it does |
|--------|-------------|
| `search` | Full-text + keyword search across all vault nodes |
| `get_linked` | BFS from a known node up to N hops — "what connects to this?" |
| `get_clusters` | Show current conceptual clusters in the graph |
| `get_bridges` | Find nodes that connect otherwise isolated clusters — emergence |
| `get_hubs` | Most-connected concept nodes |
| `ingest` | Write a custom node (reasoning trace, observation, question) |
| `stats` | Quick graph summary |

### Example calls

"What do I know about memory decay?"
→ `vault_query(action="search", query="memory decay confidence", top_k=5)`

"What connects to the 'consolidator' concept?"
→ `vault_query(action="get_linked", node_id="index/consolidator", depth=2)`

"Show me unexpected cross-topic connections"
→ `vault_query(action="get_bridges")`

"What's the current state of the graph?"
→ `vault_query(action="stats")`

---

## Emergence scanner

Runs every 20–30 minutes as a background task. Finds **bridge nodes** — vault
nodes that link two otherwise isolated clusters with 3+ members each. Writes
the discovered connection as an `emergent/` node and mirrors it into the SQLite
profile as `source="vault_emergent"` so it surfaces in context automatically.

The scanner uses graph topology only — no LLM call — so it runs cheaply and
continuously.

---

## Configuration (`.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OBSIDIAN_VAULT_DIR` | `<project>/vault` | Path to the vault folder on disk |
| `OBSIDIAN_URL` | `http://localhost:27123` | Obsidian Local REST API URL (optional) |
| `OBSIDIAN_API_KEY` | _(blank)_ | API key for REST plugin (optional) |
| `VAULT_EMERGENCE_INTERVAL` | `10` | Consolidator ticks between emergence scans |

The vault works without the REST API — files are written directly to disk and
Obsidian picks them up automatically. Set `OBSIDIAN_API_KEY` only if you have
the Local REST API plugin installed for richer search.

---

## SQLite ↔ vault sync

| Event | Vault action |
|-------|-------------|
| Consolidator extracts a new profile fact | New `reasoning/` node created |
| Profile fact decays | Confidence in existing vault node updated |
| Profile fact pruned below floor | Node gets `#deprecated` tag |
| Emergence scanner finds a bridge | `emergent/` node created + SQLite fact written |

---

## When to use vault_query vs search_knowledge

- **search_knowledge** — retrieve specific knowledge guide files (architecture docs)
- **vault_query** — retrieve live experience nodes, find cross-topic patterns,
  explore the graph of what has actually happened in conversations and tool runs
