"""Dynamic tool: manage_users."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

TOOL_DEF = {
    "name": "manage_users",
    "description": (
        "Add, edit, remove, or list users and their permission settings for the web hub. "
        "Each user has a username, hashed password, and a list of permissions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "edit", "remove"],
                "description": "Action to perform."
            },
            "username": {
                "type": "string",
                "description": "The target account username."
            },
            "password": {
                "type": "string",
                "description": "Cleartext password (only needed for 'add' or when changing password during 'edit')."
            },
            "permissions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of permission tags: 'admin', 'tiles:view', 'tiles:edit', 'workshop:view', etc."
            }
        },
        "required": ["action"]
    }
}


async def run(
    action: str,
    username: str | None = None,
    password: str | None = None,
    permissions: list[str] | None = None,
) -> str:
    users_path = Path("data/users.json")
    if not users_path.exists():
        users = []
    else:
        try:
            with open(users_path, "r", encoding="utf-8") as f:
                users = json.load(f)
        except Exception:
            users = []

    if action == "list":
        clean_users = []
        for u in users:
            clean_users.append({
                "username": u.get("username"),
                "permissions": u.get("permissions", [])
            })
        return json.dumps(clean_users, indent=2)

    if action == "add":
        if not username:
            return "Error: 'username' is required to add a user."
        if not password:
            return "Error: 'password' is required to add a user."

        # Check if already exists
        for u in users:
            if u.get("username") == username:
                return f"Error: User '{username}' already exists."

        # Hash password
        p_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        new_user = {
            "username": username,
            "password_hash": p_hash,
            "permissions": permissions or ["tiles:view"]
        }
        users.append(new_user)
        msg = f"Successfully added user '{username}'."

    elif action == "edit":
        if not username:
            return "Error: 'username' is required to edit a user."

        found = None
        for u in users:
            if u.get("username") == username:
                found = u
                break

        if not found:
            return f"Error: User '{username}' not found."

        if password:
            p_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
            found["password_hash"] = p_hash
        if permissions is not None:
            found["permissions"] = permissions
        msg = f"Successfully updated user '{username}'."

    elif action == "remove":
        if not username:
            return "Error: 'username' is required to remove a user."

        initial_len = len(users)
        users = [u for u in users if u.get("username") != username]
        if len(users) == initial_len:
            return f"Error: User '{username}' not found."
        msg = f"Successfully removed user '{username}'."

    else:
        return f"Error: Unsupported action '{action}'."

    # Save
    users_path.parent.mkdir(parents=True, exist_ok=True)
    with open(users_path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

    return msg
