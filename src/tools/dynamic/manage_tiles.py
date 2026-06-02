"""Dynamic tool: manage_tiles."""
from __future__ import annotations

import json
from pathlib import Path
import uuid
from config.settings import DATA_DIR, USER_PROFILES_DIR, DEFAULT_TILES, active_user_id

TOOL_DEF = {
    "name": "manage_tiles",
    "description": (
        "Add, remove, or edit layout tiles (apps or games) on the system hub page. "
        "Each tile configuration is stored in data/tiles.json."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "edit", "remove"],
                "description": "The action to perform on the tiles list."
            },
            "category": {
                "type": "string",
                "enum": ["apps", "games"],
                "description": "Category folder: 'apps' or 'games'."
            },
            "tile_id": {
                "type": "string",
                "description": "The unique ID of the tile to edit or remove. Not needed for 'add'."
            },
            "title": {
                "type": "string",
                "description": "The visual title text of the tile."
            },
            "description": {
                "type": "string",
                "description": "Brief text explanation of the tile."
            },
            "type": {
                "type": "string",
                "enum": ["app", "game", "webpage"],
                "description": "Underlying launch type."
            },
            "path": {
                "type": "string",
                "description": "Local executable or script path (required if type is app or game)."
            },
            "url": {
                "type": "string",
                "description": "Target web link URL (required if type is webpage)."
            }
        },
        "required": ["action", "category"]
    }
}


async def run(
    action: str,
    category: str,
    tile_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    type: str | None = None,
    path: str | None = None,
    url: str | None = None,
) -> str:
    user_id = active_user_id.get()
    user_tiles_path = USER_PROFILES_DIR / user_id / "tiles.json" if user_id and user_id != "default" else DATA_DIR / "tiles.json"
    
    if user_tiles_path.exists():
        tiles_path = user_tiles_path
    else:
        global_tiles_path = DATA_DIR / "tiles.json"
        if global_tiles_path.exists():
            tiles_path = global_tiles_path
        else:
            tiles_path = None

    if tiles_path and tiles_path.exists():
        try:
            with open(tiles_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            import copy
            data = copy.deepcopy(DEFAULT_TILES)
    else:
        import copy
        data = copy.deepcopy(DEFAULT_TILES)

    # Ensure categories exist
    if "apps" not in data:
        data["apps"] = []
    if "games" not in data:
        data["games"] = []

    target_list = data[category]

    if action == "add":
        if not title:
            return "Error: 'title' is required to add a tile."
        if not type:
            return "Error: 'type' is required to add a tile."
        if type in ("app", "game") and not path:
            return f"Error: 'path' is required for {type} tiles."
        if type == "webpage" and not url:
            return "Error: 'url' is required for webpage tiles."

        new_tile = {
            "id": f"tile_{uuid.uuid4().hex[:8]}",
            "title": title,
            "description": description or "",
            "type": type,
        }
        if type in ("app", "game"):
            new_tile["path"] = path
        else:
            new_tile["url"] = url

        target_list.append(new_tile)
        msg = f"Successfully added tile '{title}' to {category}."

    elif action == "edit":
        if not tile_id:
            return "Error: 'tile_id' is required to edit a tile."
        found = None
        for item in target_list:
            if item.get("id") == tile_id:
                found = item
                break
        if not found:
            return f"Error: Tile with ID '{tile_id}' not found in category '{category}'."

        if title is not None:
            found["title"] = title
        if description is not None:
            found["description"] = description
        if type is not None:
            found["type"] = type
        if path is not None:
            found["path"] = path
        if url is not None:
            found["url"] = url

        # Clean fields according to type
        current_type = found.get("type", "app")
        if current_type == "webpage":
            if "path" in found:
                del found["path"]
        else:
            if "url" in found:
                del found["url"]

        msg = f"Successfully edited tile '{found.get('title')}' ({tile_id}) in {category}."

    elif action == "remove":
        if not tile_id:
            return "Error: 'tile_id' is required to remove a tile."
        initial_len = len(target_list)
        data[category] = [item for item in target_list if item.get("id") != tile_id]
        if len(data[category]) == initial_len:
            return f"Error: Tile with ID '{tile_id}' not found in category '{category}'."
        msg = f"Successfully removed tile with ID '{tile_id}' from {category}."

    else:
        return f"Error: Unsupported action '{action}'."

    # Write changes
    user_tiles_path.parent.mkdir(parents=True, exist_ok=True)
    with open(user_tiles_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return msg
