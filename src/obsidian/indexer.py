"""
VaultIndexer — async, fire-and-forget service that writes vault nodes
after every agent turn and tool execution.

Called from core.py:
    asyncio.create_task(vault_indexer.index_turn(...))
    asyncio.create_task(vault_indexer.index_tool(...))

Never raises — all errors are logged and swallowed so a vault outage
can never break an agent turn.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.obsidian.client import VaultClient, get_client
from src.obsidian.nodes import (
    build_conversation_node,
    build_tool_node,
    build_index_node,
    _slug,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Turn indexing
# ------------------------------------------------------------------ #

async def index_turn(
    user_input: str,
    response: str,
    session_id: str,
    source: str = "web_chat",
    tools_used: list[str] | None = None,
    confidence: float = 0.9,
) -> None:
    """Write a conversation node for a completed agent turn."""
    try:
        client = get_client()
        path, content = build_conversation_node(
            user_msg=user_input,
            agent_reply=response,
            session_id=session_id,
            source=source,
            tools_used=tools_used or [],
            confidence=confidence,
        )
        await client.write_note(path, content)
        logger.debug("vault: wrote conversation node %s", path)

        # Update concept index nodes for any tools used
        if tools_used:
            await _update_tool_index_nodes(client, tools_used, path)

    except Exception as exc:
        logger.debug("vault index_turn silently failed: %s", exc)


# ------------------------------------------------------------------ #
# Tool indexing
# ------------------------------------------------------------------ #

async def index_tool(
    tool_name: str,
    args: dict[str, Any],
    result: str,
    session_id: str,
    was_error: bool = False,
) -> None:
    """Write a tool node for a single tool execution."""
    try:
        client = get_client()
        path, content = build_tool_node(
            tool_name=tool_name,
            args=args,
            result=result,
            session_id=session_id,
            was_error=was_error,
            confidence=0.7 if was_error else 0.85,
        )
        await client.write_note(path, content)
        logger.debug("vault: wrote tool node %s", path)
    except Exception as exc:
        logger.debug("vault index_tool silently failed: %s", exc)


# ------------------------------------------------------------------ #
# Index node maintenance
# ------------------------------------------------------------------ #

async def _update_tool_index_nodes(
    client: VaultClient,
    tools_used: list[str],
    referencing_path: str,
) -> None:
    """
    Maintain an index/tool-<name> aggregator node for each tool that was used.
    Adds the conversation path to its references section.
    """
    for tool_name in tools_used:
        slug = _slug(tool_name)
        index_path = f"index/tool-{slug}"
        existing = await client.read_note(index_path)

        if existing is None:
            # Create fresh index node
            _, content = build_index_node(
                concept=tool_name,
                description=f"Aggregated usage log for tool `{tool_name}`.",
                linked_paths=[referencing_path],
            )
            await client.write_note(index_path, content)
        else:
            # Append reference if not already there
            ref = f"- [[{referencing_path}]]"
            if ref not in existing:
                updated = existing.rstrip() + f"\n{ref}\n"
                await client.write_note(index_path, updated)


async def ensure_vault_structure(client: VaultClient) -> None:
    """
    Write placeholder README nodes for each top-level folder so Obsidian
    shows a meaningful graph from the very first turn.
    """
    folders = {
        "conversations": "Timestamped conversation turns between Travis and Andrew.",
        "tools": "Individual tool execution logs — arguments, results, errors.",
        "reasoning": "Extracted reasoning traces and chain-of-thought fragments.",
        "emergent": "Insights discovered by the emergence scanner — unexpected connections.",
        "index": "Concept aggregator nodes — hubs that link related vault entries.",
    }
    for folder, desc in folders.items():
        readme_path = f"{folder}/_index"
        existing = await client.read_note(readme_path)
        if existing is None:
            _, content = build_index_node(
                concept=folder.title(),
                description=desc,
                linked_paths=[],
            )
            await client.write_note(readme_path, content)


# ------------------------------------------------------------------ #
# Module-level singleton and initialisation
# ------------------------------------------------------------------ #

_initialised = False
_init_lock = asyncio.Lock()


async def ensure_initialised() -> None:
    global _initialised
    if _initialised:
        return
    async with _init_lock:
        if _initialised:
            return
        try:
            client = get_client()
            await ensure_vault_structure(client)
            _initialised = True
            logger.info("vault indexer initialised at %s", client.vault_dir)
        except Exception as exc:
            logger.warning("vault indexer init failed (vault offline?): %s", exc)
