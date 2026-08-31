# Framework

**Tags:** `ai-agent` `llm` `python` `fastapi` `discord-bot` `memory` `multi-provider` `local-first` `alpha`

A self-hosted, persistent AI agent framework. It runs on your own machine, keeps long-term memory across sessions, and works across multiple LLM providers with a decision layer that governs how and when it acts.

This repository is the **Alpha release** of the core foundation. It is deliberately minimal, with the architecture designed to grow through use rather than ship with a fixed personality or use case baked in.

---

## Features

- **Multi-provider LLM support** — OpenRouter, Mistral, Gemini, Anthropic, or local Ollama, switchable via config or at runtime.
- **Persistent memory** — long-term memory storage and recall that survives across sessions.
- **Decision layer** — a reflex/gating layer that governs tool use, proactive outreach, and autonomous actions.
- **Web dashboard** — a FastAPI backend with a React frontend for chat, monitoring, and settings.
- **Discord integration** — an optional bot for interacting with the agent from Discord.
- **Voice support** — speech-to-text (faster-whisper) and text-to-speech (edge-tts).
- **Cost tracking** — per-request token/cost logging with configurable budgets and pricing.
- **Runtime backend switching** — swap LLM providers/backends without restarting, with health checks and audit logging.
- **Obsidian vault integration** — optional sync with a local Obsidian vault for notes and knowledge.

---

## Quick Start

1. Configure `.env` with a provider:
   - OpenRouter (default): `LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY`
   - Mistral: `LLM_PROVIDER=mistral` + `MISTRAL_API_KEY`
   - Anthropic: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`
   - Gemini: `LLM_PROVIDER=gemini` + `GEMINI_API_KEY`
   - Ollama (local, free): `LLM_PROVIDER=ollama` (no key needed; run `ollama serve` locally)
   - Optionally set model vars (`OPENROUTER_MODEL`, `MISTRAL_MODEL`, `OLLAMA_MODEL`, etc.)
2. `pip install -r requirements.txt`
3. `python main.py`

Web dashboard runs at http://127.0.0.1:8765 (or your local IP for mobile).

Optional: Install Ollama + `llama3.2` for the intuition and existential layers.

---

## Support / Installation Help

Need help getting the framework running?

Join the public support and onboarding Discord server:

**https://discord.gg/QmUvhGSrt4**

Support flow:

1. Join the server.
2. Read `#welcome` and check `#resources` first.
3. If you get stuck, post in `#help-desk`.
4. Include:
   - your operating system
   - Python version
   - which provider/model you are trying to use
   - the exact error message or screenshot
   - what step you were on when it failed

The goal is simple: help people install the framework, ask questions, report bugs, and get support without being left alone with confusing setup errors.

This is an Alpha project, so rough edges are expected. Clear bug reports and install notes help improve the framework for everyone.

---

## Cost Tracking

- Token/cost tracking is persisted in `data/profiles/default/cost_tracking.db`.
- Configure pricing with `POST /api/cost/pricing`.
- Configure budget thresholds with `POST /api/cost/budget`.
- Read live usage with `GET /api/cost/snapshot` and `GET /api/cost/events`.

---

## Backend Switching

- Switch backend/provider at runtime using `switch_backend_provider`.
- Query active backend and fallback health with `get_backend_status`.
- API endpoints:
  - `GET /api/backend/status`
  - `POST /api/backend/switch`
- Backend registry/state/audit live in `data/profiles/default/`:
  - `backend_registry.json`
  - `backend_state.json`
  - `backend_switch_log.jsonl`

---

## Design Principles

- Stay minimal — avoid anything that gets in the way of extending the core.
- Memory that consolidates and survives across sessions.
- Proactive outreach only when there's a real observation or question worth surfacing.
- Full visibility and control over the systems the agent runs on.
- An architecture that adapts to how it's used, rather than a fixed identity or preset use case.

This is v0.1 Alpha. The project is under active iteration.
