"""
Node builders — format raw agent data as Obsidian-compatible markdown nodes.

Each public function returns (vault_relative_path, markdown_content).
Paths never clash because they embed timestamps and session IDs.
"""
from __future__ import annotations

import hashlib
import re
import textwrap
from datetime import datetime, timezone
from typing import Any

# ------------------------------------------------------------------ #
# Slug / id helpers
# ------------------------------------------------------------------ #

def _slug(text: str, maxlen: int = 48) -> str:
    """Turn arbitrary text into a safe filename slug."""
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:maxlen] or "node"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ts_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _short_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]


# ------------------------------------------------------------------ #
# Wikilink extraction
# ------------------------------------------------------------------ #

# Concepts we always link if found in text.
_CORE_CONCEPTS = {
    "memory", "biology", "drives", "soul", "tools", "grok",
    "ollama", "intuition", "existential", "consolidator", "whisper",
    "discord", "workshop", "vault", "obsidian", "swarm", "subagent",
    "schedule", "contacts", "proactive", "outreach", "embedding",
}


def extract_wikilinks(text: str, extra_concepts: set[str] | None = None) -> list[str]:
    """
    Find concepts in *text* that deserve [[wikilinks]].
    Returns a deduplicated list of concept names (not yet wrapped in [[]]).
    """
    concepts = _CORE_CONCEPTS | (extra_concepts or set())
    found: list[str] = []
    lower = text.lower()
    for c in concepts:
        if c in lower:
            found.append(c)

    # Also extract CamelCase and capitalised multi-word phrases that appear
    # to be proper names (at least 2 capital letters, not at sentence start)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", text):
        word = m.group(1)
        if len(word) >= 4:
            found.append(_slug(word))

    return list(dict.fromkeys(found))  # deduplicate, preserve order


def _wikilink_section(links: list[str]) -> str:
    if not links:
        return ""
    lines = "\n".join(f"- [[{lnk}]]" for lnk in links[:12])
    return f"\n## Related\n{lines}\n"


# ------------------------------------------------------------------ #
# Frontmatter
# ------------------------------------------------------------------ #

def _fm(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if isinstance(v, list):
            tags_str = ", ".join(str(x) for x in v)
            lines.append(f"{k}: [{tags_str}]")
        elif isinstance(v, str) and "\n" in v:
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# Node builders
# ------------------------------------------------------------------ #

def build_conversation_node(
    user_msg: str,
    agent_reply: str,
    session_id: str,
    source: str = "web_chat",
    tools_used: list[str] | None = None,
    confidence: float = 0.9,
    extra_tags: list[str] | None = None,
) -> tuple[str, str]:
    """Return (vault_path, content) for a single conversation turn."""
    ts = _ts_prefix()
    sid_short = session_id[:8] if session_id else "nosession"
    path = f"conversations/{ts}_{sid_short}"

    tags = ["conversation", source.replace("_", "-")]
    if tools_used:
        tags.append("tool-use")
    if extra_tags:
        tags.extend(extra_tags)

    snippet = _slug(user_msg[:60]) or "turn"
    title = f"Turn: {snippet}"

    fm = _fm({
        "id": f"conv_{ts}_{sid_short}",
        "type": "conversation",
        "session_id": session_id,
        "timestamp": _now_iso(),
        "source": source,
        "confidence": confidence,
        "tags": tags,
    })

    user_block = textwrap.fill(user_msg, 100) if len(user_msg) < 2000 else user_msg[:2000] + "…"
    reply_block = textwrap.fill(agent_reply, 100) if len(agent_reply) < 3000 else agent_reply[:3000] + "…"

    tools_section = ""
    if tools_used:
        tools_section = "\n## Tools used\n" + "\n".join(
            f"- [[tools/{t}|{t}]]" for t in tools_used
        ) + "\n"

    wikilinks = extract_wikilinks(user_msg + " " + agent_reply)
    if tools_used:
        wikilinks += [_slug(t) for t in tools_used]

    content = (
        f"{fm}\n\n"
        f"# {title}\n\n"
        f"## User\n{user_block}\n\n"
        f"## Andrew\n{reply_block}\n"
        f"{tools_section}"
        f"{_wikilink_section(wikilinks)}"
    )
    return path, content


def build_tool_node(
    tool_name: str,
    args: dict[str, Any],
    result: str,
    session_id: str,
    was_error: bool = False,
    confidence: float = 0.85,
) -> tuple[str, str]:
    """Return (vault_path, content) for a single tool execution."""
    ts = _ts_prefix()
    sid_short = session_id[:8] if session_id else "nosession"
    path = f"tools/{ts}_{tool_name}_{sid_short}"

    tags = ["tool", tool_name, "error" if was_error else "success"]

    # Sanitise args — remove potentially large content
    safe_args: dict[str, Any] = {}
    for k, v in args.items():
        sv = str(v)
        safe_args[k] = sv[:300] + "…" if len(sv) > 300 else sv

    result_snippet = result[:1500] + "…" if len(result) > 1500 else result

    fm = _fm({
        "id": f"tool_{ts}_{_short_id(tool_name + str(args))}",
        "type": "tool",
        "tool_name": tool_name,
        "session_id": session_id,
        "timestamp": _now_iso(),
        "was_error": str(was_error).lower(),
        "confidence": confidence,
        "tags": tags,
    })

    import json
    args_str = json.dumps(safe_args, indent=2)
    wikilinks = extract_wikilinks(result_snippet, {tool_name})

    content = (
        f"{fm}\n\n"
        f"# Tool: {tool_name}\n\n"
        f"## Arguments\n```json\n{args_str}\n```\n\n"
        f"## Result\n```\n{result_snippet}\n```\n"
        f"{_wikilink_section(wikilinks)}"
    )
    return path, content


def build_emergent_node(
    insight: str,
    bridge_node: str,
    cluster_a: list[str],
    cluster_b: list[str],
    confidence: float = 0.7,
) -> tuple[str, str]:
    """Return (vault_path, content) for an emergence-scanner insight."""
    ts = _ts_prefix()
    slug = _slug(insight[:50])
    path = f"emergent/{ts}_{slug}"

    tags = ["emergent", "synthesis"]

    fm = _fm({
        "id": f"emergent_{ts}_{_short_id(insight)}",
        "type": "emergent",
        "bridge_node": bridge_node,
        "timestamp": _now_iso(),
        "confidence": confidence,
        "tags": tags,
    })

    ca_links = "\n".join(f"- [[{n}]]" for n in cluster_a[:8])
    cb_links = "\n".join(f"- [[{n}]]" for n in cluster_b[:8])
    wikilinks = extract_wikilinks(insight)
    wikilinks += [_slug(bridge_node)]

    content = (
        f"{fm}\n\n"
        f"# Emergent: {insight}\n\n"
        f"## Bridge node\n[[{_slug(bridge_node)}]]\n\n"
        f"## Cluster A\n{ca_links}\n\n"
        f"## Cluster B\n{cb_links}\n"
        f"{_wikilink_section(wikilinks)}"
    )
    return path, content


def build_index_node(
    concept: str,
    description: str,
    linked_paths: list[str],
    confidence: float = 0.8,
) -> tuple[str, str]:
    """Return (vault_path, content) for a concept index node."""
    slug = _slug(concept)
    path = f"index/{slug}"

    tags = ["index", "concept"]

    fm = _fm({
        "id": f"index_{slug}",
        "type": "index",
        "concept": concept,
        "timestamp": _now_iso(),
        "confidence": confidence,
        "tags": tags,
    })

    refs = "\n".join(f"- [[{p}]]" for p in linked_paths[:30])

    content = (
        f"{fm}\n\n"
        f"# {concept.title()}\n\n"
        f"{description}\n\n"
        f"## References\n{refs}\n"
    )
    return path, content


def update_node_confidence(content: str, new_confidence: float, deprecated: bool = False) -> str:
    """Patch the confidence value in a node's frontmatter. Optionally add #deprecated."""
    content = re.sub(
        r"^confidence:\s*.+$",
        f"confidence: {new_confidence:.3f}",
        content,
        flags=re.MULTILINE,
    )
    if deprecated and "#deprecated" not in content:
        content = re.sub(
            r"^tags:\s*\[(.+)\]$",
            lambda m: f"tags: [{m.group(1)}, deprecated]",
            content,
            flags=re.MULTILINE,
        )
    return content
