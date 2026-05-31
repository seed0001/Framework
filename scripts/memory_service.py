#!/usr/bin/env python
"""Convenience launcher — equivalent to: python -m src.memory_service <cmd>

Usage:
    python scripts/memory_service.py start
    python scripts/memory_service.py stop
    python scripts/memory_service.py restart
    python scripts/memory_service.py status
    python scripts/memory_service.py compile
    python scripts/memory_service.py get-hourly <id>
    python scripts/memory_service.py get-daily  <YYYY-MM-DD>
    python scripts/memory_service.py get-weekly <year> <week>
"""
import sys
from pathlib import Path

# Ensure project root is on the path when called directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory_service.__main__ import main

if __name__ == "__main__":
    main()
