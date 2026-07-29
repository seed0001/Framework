# Artifact Memory

Solen tracks saved files/documents as durable artifacts in:

`data/profiles/default/artifacts.json`

This fixes the old pattern where a file was mentioned in chat but Solen could
not later find it or verify where it lived.

## Automatic Tracking

When `write_file` returns:

`Written and verified: <ABSOLUTE_PATH> (<N> bytes)`

Solen records that path in artifact memory with title, category, byte size,
existence status, and verification timestamp.

## Tools

- `list_artifacts(category?, include_missing?)`
  - List saved files Solen knows about.
- `get_artifact(identifier)`
  - Find one file by artifact ID, title, or path substring.
- `search_memory(query)`
  - Searches schedules, artifacts, contacts, profile facts, and episodic memory.

## Categories

Categories are inferred from path/title:

- `schedule`
- `journal`
- `build_prompt`
- `ideas`
- `contacts`
- `story`
- `document`

## Seeded Artifacts

Current Solen project files have been seeded, including:

- `My_Ideas.txt`
- `Andrews_Journal.txt`
- `outreach_log.txt`
- `Travis_Morning_Schedule_May_8_2026.txt`
