"""
Load dynamic tools from src/tools/dynamic/.
Each .py file must define TOOL_DEF and async def run(**kwargs).
"""
import importlib.util
import sys
from pathlib import Path

from src.tools import dynamic_loader as _this

DYNAMIC_DIR = Path(_this.__file__).resolve().parent / "dynamic"


def load_dynamic_tools() -> tuple[list[dict], dict[str, callable]]:
    """
    Load all tools from dynamic/. Returns (tool_definitions, runners).
    runners: {tool_name: async_run_function}
    """
    definitions = []
    runners = {}

    if not DYNAMIC_DIR.exists():
        return definitions, runners

    for path in DYNAMIC_DIR.glob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"dynamic_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)

            if not hasattr(mod, "TOOL_DEF") or not hasattr(mod, "run"):
                continue

            td = mod.TOOL_DEF
            name = td.get("name") or path.stem
            definitions.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": td.get("description", ""),
                    "parameters": td.get("parameters", {"type": "object", "properties": {}}),
                },
            })
            runners[name] = mod.run
        except Exception:
            continue

    return definitions, runners
