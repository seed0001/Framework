"""
Tool queue: suggested → approved → implemented.
Agent suggests tools, user approves, agent implements.
"""
import json
import uuid
from pathlib import Path

from config.settings import DATA_DIR

QUEUE_PATH = DATA_DIR / "tool_queue.json"
DYNAMIC_DIR = Path(__file__).resolve().parent / "dynamic"


def _load() -> dict:
    if not QUEUE_PATH.exists():
        return {"suggested": [], "approved": [], "implemented": []}
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_suggested_tools(tools: list[dict]) -> str:
    """Add tool suggestions. Each: {name, description, parameters, reason}"""
    data = _load()
    for t in tools:
        t["id"] = str(uuid.uuid4())[:8]
        t["status"] = "suggested"
        data["suggested"].append(t)
    _save(data)
    return f"Added {len(tools)} suggestion(s). IDs: {', '.join(x['id'] for x in tools)}"


def get_queue() -> dict:
    return _load()


def approve_tool(tool_id: str) -> str:
    """Move tool from suggested to approved."""
    data = _load()
    for i, t in enumerate(data["suggested"]):
        if t.get("id") == tool_id:
            data["suggested"].pop(i)
            t["status"] = "approved"
            data["approved"].append(t)
            _save(data)
            return f"Approved: {t.get('name', tool_id)}"
    return f"Tool {tool_id} not found in suggested"


def reject_tool(tool_id: str) -> str:
    data = _load()
    for i, t in enumerate(data["suggested"]):
        if t.get("id") == tool_id:
            data["suggested"].pop(i)
            _save(data)
            return f"Rejected: {t.get('name', tool_id)}"
    return f"Tool {tool_id} not found"


def mark_implemented(tool_id: str, file_path: str = "") -> str:
    """Move tool from approved to implemented."""
    data = _load()
    for i, t in enumerate(data["approved"]):
        if t.get("id") == tool_id:
            data["approved"].pop(i)
            t["status"] = "implemented"
            t["file_path"] = file_path
            data["implemented"].append(t)
            _save(data)
            return f"Marked implemented: {t.get('name', tool_id)}"
    return f"Tool {tool_id} not found in approved"


def get_next_approved() -> dict | None:
    """Get first approved tool for implementation."""
    data = _load()
    return data["approved"][0] if data["approved"] else None
