"""FastAPI app: dashboard, chat, voice, Discord, notifications."""
import asyncio
import base64
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config.settings import WEB_HOST, WEB_PORT, DATA_DIR, USER_PROFILES_DIR, DEFAULT_TILES
from src.agent import core as agent_core
from src.agent.core import AssistiveAgent
from src.tools import tool_queue
from src.voice.stt import transcribe_audio
from src.voice.tts import synthesize

# Global agent instance
agent: AssistiveAgent | None = None
_discord_task = None
_user_discord_tasks: dict[str, asyncio.Task] = {}
_background_thoughts_task: asyncio.Task | None = None
_status_check_task: asyncio.Task | None = None
_consolidator_task: asyncio.Task | None = None
_consolidator_stop: asyncio.Event | None = None
_memory_service_task: asyncio.Task | None = None
_vault_emergence_task: asyncio.Task | None = None

def start_user_discord_bot(username: str):
    global _user_discord_tasks
    from src.user_settings import get_user_discord_config
    token, owner_id = get_user_discord_config(username)
    if not token or not owner_id:
        return
    
    # Cancel existing bot if any
    stop_user_discord_bot(username)
    
    u_agent = get_agent_for_user(username)
    if not u_agent:
        return
        
    try:
        from src.discord_bot import start_discord_task_for_user
        _user_discord_tasks[username] = start_discord_task_for_user(username, token, owner_id, u_agent)
        print(f"Started Discord bot for user '{username}'")
    except Exception as e:
        print(f"Failed to start Discord bot for user '{username}': {e}")

def stop_user_discord_bot(username: str):
    global _user_discord_tasks
    task = _user_discord_tasks.pop(username, None)
    if task and not task.done():
        task.cancel()
        print(f"Stopped Discord bot for user '{username}'")
async def _status_check_loop():
    """Periodic self-diagnostic: sub-agent status. Alert only when issues first appear, not every poll."""
    STATUS_INTERVAL = 600  # 10 min
    _last_had_issues = False
    while True:
        await asyncio.sleep(STATUS_INTERVAL)
        if agent is None:
            continue
        try:
            from src.agent import core as agent_core
            from src.logging_config import log_status_check
            from src import notifications
            mgr = agent_core._get_subagent_manager()
            status = mgr.status()
            issues = "failed" in status.lower() or "error" in status.lower()
            log_status_check(status, issues)
            if issues and not _last_had_issues:
                try:
                    from src.agent import soul
                    s = soul.load_soul()
                    title = (s.get("agent_name") or "Agent").strip() or "Software Lifeform"
                except Exception:
                    title = "Software Lifeform"
                notifications.emit_notification(
                    "status_alert",
                    f"{title} — Status check",
                    f"Sub-agent or tool issue detected: {status[:150]}",
                    {"status": status},
                )
                try:
                    agent.memory.add_short_term(f"[Status alert I sent you]: Sub-agent or tool issue: {status[:200]}")
                except Exception:
                    pass
                _last_had_issues = True
            elif not issues:
                _last_had_issues = False
        except asyncio.CancelledError:
            break
        except Exception as e:
            try:
                from src.logging_config import log_error
                log_error("status_check_loop", e)
            except Exception:
                pass


async def _background_thoughts_loop():
    """Drive-gated background thinking: runs when connection/expression urges exceed threshold."""
    from background_thoughts import run_once

    # Poll interval: check drives every 2 min
    POLL_SEC = 120
    while True:
        await asyncio.sleep(POLL_SEC)
        if agent is None:
            continue
        try:
            if not agent.biology.should_proactive():
                continue
            await run_once()
            agent.biology.record_proactive()
        except asyncio.CancelledError:
            break
        except Exception as e:
            try:
                from src.logging_config import log_error
                log_error("background_thoughts", e)
            except Exception:
                print(f"Background thought error: {e}")


def _build_consolidator_llm():
    """Return an async (system, user) -> str function backed by the active backend.

    The consolidator follows backend_state.json on each call, so background
    memory work cannot keep using an old .env provider after Andrew switches.
    """
    from openai import AsyncOpenAI

    async def _call(system: str, user: str) -> str:
        from src import backend_switching

        active = backend_switching.get_active_backend(user_id="default")
        client = AsyncOpenAI(api_key=active.api_key, base_url=active.base_url)
        resp = await client.chat.completions.create(
            model=active.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        try:
            from src.cost_tracking import record_openai_chat_usage

            record_openai_chat_usage(
                response=resp,
                provider=active.provider,
                model=active.model,
                source_type="background",
                task_label="memory_consolidator",
                fallback_prompt_text=f"{system}\n\n{user}",
                fallback_output_text=(resp.choices[0].message.content or "").strip(),
                user_id="default",
            )
        except Exception:
            pass
        return (resp.choices[0].message.content or "").strip()

    return _call


async def _consolidator_loop(stop_event: asyncio.Event):
    """Stochastic memory consolidator. Runs decay + LLM consolidation passes
    against the live agent's profile."""
    from src.agent.memory_consolidator import ConsolidatorConfig, MemoryConsolidator

    try:
        llm = _build_consolidator_llm()
    except Exception as e:
        try:
            from src.logging_config import log_error
            log_error("consolidator_init", e)
        except Exception:
            print(f"Consolidator LLM init failed; running decay-only: {e}")
        llm = None

    consolidator = MemoryConsolidator(
        user_id="default",
        config=ConsolidatorConfig(),
        llm=llm,
    )
    try:
        await consolidator.run_loop(stop_event)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        try:
            from src.logging_config import log_error
            log_error("consolidator_loop", e)
        except Exception:
            print(f"Consolidator crashed: {e}")


async def _vault_emergence_loop(stop_event: asyncio.Event) -> None:
    """
    Background loop that periodically runs the emergence scanner.
    Runs independently of the consolidator — uses its own cooldown.
    Silently does nothing if the vault isn't set up or is offline.
    """
    import random
    from config.settings import VAULT_EMERGENCE_INTERVAL

    # Initial delay: wait a few minutes for the agent to warm up first
    await asyncio.sleep(120)

    tick = 0
    while not stop_event.is_set():
        tick += 1
        if VAULT_EMERGENCE_INTERVAL <= 0 or tick % max(1, VAULT_EMERGENCE_INTERVAL) == 0:
            try:
                from src.obsidian.emergence import run_scan
                await run_scan(user_id="default")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                try:
                    from src.logging_config import log_error
                    log_error("vault_emergence", exc)
                except Exception:
                    pass

        # Sleep 20–30 min between ticks (jittered)
        wait = random.randint(1200, 1800)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=wait)
            return
        except asyncio.TimeoutError:
            continue


async def _run_completion_review(aid: str, task: str, status: str):
    """Auto-notify Creator when a background task completes."""
    global agent
    if agent is None:
        return
    try:
        from config.settings import DISCORD_OWNER_ID
        from src import background_completions, contacts, notifications
        from src.outreach import queue_outreach

        def _extract_output_path(text: str) -> str:
            if not text:
                return ""
            patterns = [
                r"Output:\s*([^\r\n]+)",
                r"Saved to:\s*([^\r\n]+)",
            ]
            for pat in patterns:
                m = re.search(pat, text, flags=re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip().strip("'\"")
                    p = Path(candidate).expanduser()
                    if p.exists():
                        return str(p.resolve())
                    if not p.is_absolute():
                        rel = (Path.cwd() / p).resolve()
                        if rel.exists():
                            return str(rel)
            return ""

        def _short_summary(task_name: str, completion_status: str, output: str) -> str:
            output = (output or "").strip()
            if not output:
                return f"Background task '{task_name}' ({completion_status}) finished with no captured output."
            lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
            headline = lines[-1] if lines else output[:180]
            if len(headline) > 200:
                headline = headline[:197] + "..."
            return f"Background task '{task_name}' ({completion_status}) finished. {headline}"

        # Ensure owner is always treated as creator for notification paths.
        owner_id = str(DISCORD_OWNER_ID or "").strip()
        if owner_id:
            try:
                contacts.update_contact(
                    "",
                    discord_id=owner_id,
                    name="Creator",
                    tier="creator",
                    preferred_channel="discord",
                )
            except Exception:
                pass

        mgr = agent_core._get_subagent_manager()
        output = mgr.get_output(aid)
        out_path = _extract_output_path(output)
        summary = _short_summary(task, status, output)

        body = summary
        if out_path:
            body += f" Full output: {out_path}"
        elif output:
            preview = output.replace("\r", " ").replace("\n", " ")
            if len(preview) > 260:
                preview = preview[:257] + "..."
            body += f" Output preview: {preview}"

        notifications.emit_notification(
            "task_complete",
            f"Background task complete: {aid}",
            body,
            {"aid": aid, "task": task, "status": status, "output_path": out_path},
        )
        notifications.show_desktop_notification(
            f"Task complete: {aid}",
            body[:200],
        )

        delivered = False
        if owner_id:
            try:
                queue_outreach(
                    "discord",
                    f"[Task complete] {aid}: {body}",
                    target_user_id=owner_id,
                    source="background_completion",
                    trigger_key=f"background_complete:{aid}",
                    event_id=f"background_complete:{aid}",
                    is_direct=True,
                )
                delivered = True
            except Exception:
                delivered = False

        if not delivered:
            notifications.emit_notification(
                "proactive",
                "Background task complete",
                body,
                {"aid": aid, "task": task, "status": status, "output_path": out_path},
            )

        try:
            agent.memory.add_short_term(f"[Background task completion sent] {aid} ({task}): {body}")
        except Exception:
            pass
        background_completions.acknowledge(aid, user_id="default")
    except Exception as e:
        try:
            from src.logging_config import log_error
            log_error("completion_review", e)
        except Exception:
            pass


def _on_subagent_complete(aid: str, task: str, status: str):
    """Called when a subagent finishes. Persists completion and triggers Nova review."""
    from src import background_completions
    background_completions.add(aid, task, status, user_id="default")
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_run_completion_review(aid, task, status))
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, _discord_task, _background_thoughts_task, _status_check_task
    global _consolidator_task, _consolidator_stop, _memory_service_task
    global _vault_emergence_task
    agent = AssistiveAgent(user_id="default")
    from src.tools import subagents
    subagents.set_completion_callback(_on_subagent_complete)
    _background_thoughts_task = asyncio.create_task(_background_thoughts_loop())
    _status_check_task = asyncio.create_task(_status_check_loop())
    _consolidator_stop = asyncio.Event()
    _consolidator_task = asyncio.create_task(_consolidator_loop(_consolidator_stop))
    _vault_emergence_task = asyncio.create_task(_vault_emergence_loop(_consolidator_stop))
    try:
        from src.memory_service.service import MemoryService
        _memory_service_task = asyncio.create_task(MemoryService().run(integrated=True))
    except Exception as e:
        print(f"Memory service not started: {e}")
    # Start Discord bots for all configured profiles
    try:
        from src.discord_bot import set_agent
        set_agent(agent)
        
        # Start bot for default profile
        start_user_discord_bot("default")
        
        # Scan profiles
        if USER_PROFILES_DIR.exists():
            for p in USER_PROFILES_DIR.iterdir():
                if p.is_dir():
                    start_user_discord_bot(p.name)
    except Exception as e:
        print(f"Error starting Discord bots on lifespan startup: {e}")
    yield
    # Stop all user Discord tasks
    global _user_discord_tasks
    for username in list(_user_discord_tasks.keys()):
        stop_user_discord_bot(username)
    if _background_thoughts_task and not _background_thoughts_task.done():
        _background_thoughts_task.cancel()
        try:
            await _background_thoughts_task
        except asyncio.CancelledError:
            pass
    if _status_check_task and not _status_check_task.done():
        _status_check_task.cancel()
        try:
            await _status_check_task
        except asyncio.CancelledError:
            pass
    if _consolidator_task and not _consolidator_task.done():
        if _consolidator_stop:
            _consolidator_stop.set()
        _consolidator_task.cancel()
        try:
            await _consolidator_task
        except asyncio.CancelledError:
            pass
    if _discord_task and not _discord_task.done():
        _discord_task.cancel()
        try:
            await _discord_task
        except asyncio.CancelledError:
            pass
    if _memory_service_task and not _memory_service_task.done():
        _memory_service_task.cancel()
        try:
            await _memory_service_task
        except asyncio.CancelledError:
            pass
    agent = None
    try:
        from src.audit_log import flush_audit_log
        flush_audit_log()
    except Exception:
        pass


app = FastAPI(title="Software Lifeform", lifespan=lifespan)

_agents: dict[str, AssistiveAgent] = {}

def get_agent_for_user(username: str | None) -> AssistiveAgent | None:
    global agent, _agents
    if not agent:
        return None
    from src.agent.soul import get_owner_name
    owner_name = get_owner_name()
    key = "default"
    if username:
        if not owner_name or username.lower() != owner_name.lower():
            key = username
    
    if key == "default":
        return agent
        
    if key not in _agents:
        try:
            _agents[key] = AssistiveAgent(user_id=key)
        except Exception as e:
            print(f"Failed to instantiate agent for user {key}: {e}")
            return None
    return _agents[key]

def get_agent_for_request(request: Request) -> AssistiveAgent | None:
    username = get_current_user(request)
    return get_agent_for_user(username)


# Paths
_WEB_DIR = Path(__file__).resolve().parent
_STATIC = _WEB_DIR / "static"
_TEMPLATES = _WEB_DIR / "templates"

if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    from fastapi import Response
    import time
    html_path = _TEMPLATES / "index.html"
    with open(html_path, encoding="utf-8") as f:
        content = f.read()
    ts = int(time.time())
    content = content.replace("main.js", f"main.js?t={ts}").replace("main.css", f"main.css?t={ts}")
    return Response(
        content=content,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@app.get("/chat", response_class=HTMLResponse)
async def chat():
    html_path = _TEMPLATES / "chat.html"
    with open(html_path, encoding="utf-8") as f:
        return f.read()


@app.get("/workshop")
async def workshop_redirect():
    return RedirectResponse(url="/#/workshop")


async def _stream_chat_generator(message: str, username: str | None, device: str = "desktop_chat"):
    """Stream narration events then final response as SSE."""
    queue: asyncio.Queue = asyncio.Queue()

    async def run_agent():
        try:
            u_agent = get_agent_for_user(username)
            if not u_agent:
                await queue.put({"type": "error", "text": "Agent not ready"})
                return
            u_agent.memory.set_working("current_speaker_discord_id", None)
            
            # Setup device and location context tags in memory
            u_agent.memory.current_turn_metadata = {
                "source_device": device,
                "source_channel": "web_chat",
                "session_id": u_agent.memory.session_id
            }
            
            from src.agent.soul import get_context_for_speaker
            ctx = get_context_for_speaker(is_web=True, username=username)
            tagged_message = f"[device={device}] {message}"
            result = await u_agent.chat(
                ctx + tagged_message,
                narrate_queue=queue,
                speaker_discord_id=None,
            )
            await queue.put({"type": "response", "text": result})
        except Exception as e:
            await queue.put({"type": "error", "text": str(e)})
        finally:
            u_agent = get_agent_for_user(username)
            if u_agent:
                u_agent.memory.current_turn_metadata = {}
            await queue.put(None)

    asyncio.create_task(run_agent())

    while True:
        item = await queue.get()
        if item is None:
            break
        yield f"data: {json.dumps(item)}\n\n"


@app.post("/api/chat")
async def api_chat(
    request: Request,
    message: str = Form(...),
    device: str = Form(None)
):
    if not agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    
    if not device:
        # Auto-detect if device is mobile or desktop chat
        ua = request.headers.get("user-agent", "").lower()
        device = "phone" if any(mob in ua for mob in ("iphone", "android", "mobile", "phone")) else "desktop"
    
    username = get_current_user(request)
    return StreamingResponse(
        _stream_chat_generator(message, username, device),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/transcribe")
async def api_transcribe(audio: UploadFile = File(...)):
    """Transcribe uploaded audio (from Record -> Stop -> Send flow)."""
    import asyncio
    try:
        data = await audio.read()
        text = await asyncio.to_thread(transcribe_audio, data)
        return {"text": text}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/tool-queue")
async def api_tool_queue():
    return tool_queue.get_queue()


@app.get("/api/memory-view")
async def api_memory_view(request: Request):
    """Return profile, episodic memories, working memory, and biology state."""
    u_agent = get_agent_for_request(request)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    from src.tools import image_gen
    m = u_agent.memory
    return {
        "profile": m.get_profile_view(),
        "episodic": m.get_episodic_view(),
        "working": m.get_working_view(),
        "thoughts": m.get_thoughts_view(),
        "biology": u_agent.biology.get_view(),
        "existential": u_agent.existential.get_view(),
        "values_vault": __import__("src.values_vault", fromlist=["get_view"]).get_view(),
        "presence": __import__("src.presence", fromlist=["get_view"]).get_view(),
        "image_usage": image_gen.get_usage_data(),
        "subagents": agent_core._get_subagent_manager().status(),
    }


@app.post("/api/memory/remember")
async def api_memory_remember(
    request: Request,
    category: str = Form(""),
    fact: str = Form(""),
    key: str = Form(""),
):
    """Manually store a profile fact (always protected)."""
    u_agent = get_agent_for_request(request)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    fact = (fact or "").strip()
    if not fact:
        return JSONResponse({"error": "fact is required"}, status_code=400)
    try:
        if key:
            u_agent.memory.profile.set(
                key.strip(), fact,
                category=(category or "general").strip(),
                source="user", protected=True,
            )
            msg = f"remembered (key='{key.strip()}', protected)."
        else:
            msg = u_agent.memory.add_profile_fact(category or "other", fact)
        return {"ok": True, "message": msg}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/memory/forget")
async def api_memory_forget(request: Request, key: str = Form(...)):
    """Soft-delete a profile fact by exact key."""
    u_agent = get_agent_for_request(request)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    ok = u_agent.memory.profile.delete(key.strip())
    return {"ok": ok}


@app.post("/api/memory/protect")
async def api_memory_protect(request: Request, key: str = Form(...), protected: int = Form(1)):
    """Toggle the protected flag on a profile fact by exact key."""
    u_agent = get_agent_for_request(request)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    ok = u_agent.memory.profile.protect(key.strip(), protected=bool(int(protected)))
    return {"ok": ok}


@app.post("/api/memory/decay-config")
async def api_memory_decay_config(
    request: Request,
    half_life_days: float = Form(...),
    min_confidence: float = Form(...),
):
    """Persist decay tuning for the consolidator to pick up next tick."""
    u_agent = get_agent_for_request(request)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    if half_life_days <= 0 or not (0 <= min_confidence <= 1):
        return JSONResponse(
            {"error": "half_life_days > 0 and 0 <= min_confidence <= 1"}, status_code=400
        )
    u_agent.memory.state.set("memory.config.half_life_days", half_life_days)
    u_agent.memory.state.set("memory.config.min_confidence", min_confidence)
    return {"ok": True}


@app.post("/api/memory/forget-all")
async def api_memory_forget_all(request: Request, confirm: str = Form("")):
    """Wipe ALL profile facts. Requires confirm=yes-i-am-sure."""
    u_agent = get_agent_for_request(request)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    if confirm != "yes-i-am-sure":
        return JSONResponse({"error": "missing confirm token"}, status_code=400)
    facts = u_agent.memory.profile.get_all()
    n = 0
    for f in facts:
        if u_agent.memory.profile.delete(f.key):
            n += 1
    return {"ok": True, "deleted": n}


@app.post("/api/tool-approve")
async def api_tool_approve(tool_id: str = Form(...)):
    return {"result": tool_queue.approve_tool(tool_id)}


@app.post("/api/tool-reject")
async def api_tool_reject(tool_id: str = Form(...)):
    return {"result": tool_queue.reject_tool(tool_id)}


@app.post("/api/tool-reload")
async def api_tool_reload(request: Request):
    u_agent = get_agent_for_request(request)
    if u_agent:
        u_agent._reload_dynamic()
    return {"result": "Tools reloaded"}


@app.post("/api/subagents-stop-all")
async def api_subagents_stop_all():
    """Stop all running sub-agents."""
    mgr = agent_core._get_subagent_manager()
    n = mgr.stop_all()
    return {"result": f"Stopped {n} sub-agent(s)"}


async def _notification_sse_generator():
    """SSE stream for notifications (Discord messages, proactive outreach)."""
    from src.notifications import get_notification_queue, NotificationEvent

    q = get_notification_queue()
    while True:
        try:
            ev = await asyncio.wait_for(q.get(), timeout=30.0)
            if isinstance(ev, NotificationEvent):
                payload = {
                    "type": ev.type,
                    "title": ev.title,
                    "body": ev.body,
                    "meta": ev.meta or {},
                    "ts": ev.created_at,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.TimeoutError:
            yield "data: {\"type\":\"ping\"}\n\n"


@app.get("/api/notifications/stream")
async def api_notifications_stream():
    """SSE stream: Discord messages, proactive messages, etc."""
    return StreamingResponse(
        _notification_sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/artifacts")
async def api_get_artifacts(category: str = "", include_missing: int = 1):
    """Retrieve list of all registered artifacts."""
    from src.artifact_memory import list_artifacts
    artifacts = list_artifacts(category=category, include_missing=bool(include_missing))
    return {"artifacts": [a.to_dict() for a in artifacts]}


@app.get("/api/artifacts/{identifier}")
async def api_get_single_artifact(identifier: str):
    """Retrieve a single artifact's metadata, sections, and history by ID or name."""
    from src.artifact_memory import get_artifact
    artifact = get_artifact(identifier)
    if not artifact:
        return JSONResponse({"error": f"Artifact '{identifier}' not found"}, status_code=404)
    return {"artifact": artifact.to_dict()}


@app.post("/api/artifacts/search")
async def api_search_artifacts(query: str = Form(...), limit: int = Form(10)):
    """Search artifacts by content, metadata, or sections."""
    from src.artifact_memory import search_artifacts
    results = search_artifacts(query, limit=limit)
    return {"results": [r.to_dict() for r in results]}


@app.post("/api/artifacts/edit-section")
async def api_edit_artifact_section(
    identifier: str = Form(...),
    section_id: str = Form(...),
    content: str = Form(...),
):
    """Edit a specific section of an artifact independently."""
    from src.artifact_memory import update_artifact_section
    msg = update_artifact_section(identifier, section_id, content)
    if msg.startswith("Error"):
        return JSONResponse({"error": msg}, status_code=400)
    return {"ok": True, "message": msg}


@app.get("/api/contacts")
async def api_contacts():
    """Get all contacts (friends, Discord users)."""
    from src import contacts

    return {"contacts": contacts.get_all_contacts()}


@app.get("/api/access-policy")
async def api_get_access_policy():
    """Get access policy (tools per tier). Edit data/profiles/default/access_policy.json to change."""
    from config.access_policy import _load_policy, DEFAULT_POLICY, CONTACT_TIERS

    policy = _load_policy()
    return {"policy": policy, "tiers": list(CONTACT_TIERS)}


@app.get("/api/voices")
async def api_voices():
    """List available Edge TTS voices for voice selector."""
    try:
        import edge_tts
        voices = await edge_tts.list_voices()
        return {
            "voices": [
                {"id": v.get("ShortName", ""), "name": v.get("FriendlyName", ""), "gender": v.get("Gender", ""), "locale": v.get("Locale", "")}
                for v in (voices or []) if v.get("ShortName")
            ]
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/settings")
async def api_get_settings(request: Request):
    """Get user settings (tts_voice, discord configuration, etc.)."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from src.user_settings import get_settings
    settings = get_settings(username)
    token = settings.get("discord_token")
    return {
        "tts_voice": settings.get("tts_voice", ""),
        "discord_token_set": bool(token),
        "discord_owner_id": settings.get("discord_owner_id", ""),
        "discord_status": "Running" if username in _user_discord_tasks else "Stopped"
    }


@app.post("/api/settings")
async def api_set_settings(
    request: Request,
    tts_voice: str = Form(None),
    discord_token: str = Form(None),
    discord_owner_id: str = Form(None),
):
    """Update user settings and hot-reload Discord bot client if changed."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from src.user_settings import set_setting
    if isinstance(tts_voice, str):
        set_setting("tts_voice", tts_voice, username)
        
    config_changed = False
    if isinstance(discord_owner_id, str):
        set_setting("discord_owner_id", discord_owner_id.strip(), username)
        config_changed = True
        
    if isinstance(discord_token, str):
        token_str = discord_token.strip()
        if token_str == "__REMOVE__":
            set_setting("discord_token", None, username)
            set_setting("discord_owner_id", None, username)
            stop_user_discord_bot(username)
            config_changed = False
        elif token_str:
            set_setting("discord_token", token_str, username)
            config_changed = True
            
    if config_changed:
        start_user_discord_bot(username)
        
    return {"ok": True}


@app.get("/api/cost/snapshot")
async def api_cost_snapshot(
    period: str = "today",
    include_free: int = 1,
    group_by: str = "provider",
):
    """Live API/token cost snapshot."""
    from src.cost_tracking import get_cost_snapshot

    return get_cost_snapshot(
        period=period,
        include_free=bool(int(include_free)),
        group_by=group_by,
        user_id="default",
    )


@app.get("/api/cost/events")
async def api_cost_events(limit: int = 100):
    """Recent usage/cost events."""
    from src.cost_tracking import get_recent_events

    return {"events": get_recent_events(limit=limit, user_id="default")}


@app.post("/api/cost/pricing")
async def api_set_cost_pricing(
    provider: str = Form(...),
    model: str = Form(...),
    input_per_million: float = Form(None),
    output_per_million: float = Form(None),
    input_per_token: float = Form(None),
    output_per_token: float = Form(None),
    cached_input_per_million: float = Form(None),
    reasoning_per_million: float = Form(None),
    local: int = Form(0),
    currency: str = Form("USD"),
    notes: str = Form(""),
):
    """Create/update model pricing."""
    from src.cost_tracking import set_model_pricing

    msg = set_model_pricing(
        provider=provider,
        model=model,
        input_per_million=input_per_million,
        output_per_million=output_per_million,
        input_per_token=input_per_token,
        output_per_token=output_per_token,
        cached_input_per_million=cached_input_per_million,
        reasoning_per_million=reasoning_per_million,
        local=bool(int(local)),
        currency=currency,
        notes=notes,
        user_id="default",
    )
    return {"ok": not msg.lower().startswith("error"), "message": msg}


@app.post("/api/cost/budget")
async def api_set_cost_budget(
    daily_limit: float = Form(None),
    weekly_limit: float = Form(None),
    monthly_limit: float = Form(None),
    warning_threshold_percent: float = Form(None),
    hard_stop_threshold_percent: float = Form(None),
    require_confirmation_over_amount: float = Form(None),
    currency: str = Form(None),
):
    """Update cost budget/threshold settings."""
    from src.cost_tracking import set_budget_limits, get_budget_settings

    msg = set_budget_limits(
        daily_limit=daily_limit,
        weekly_limit=weekly_limit,
        monthly_limit=monthly_limit,
        warning_threshold_percent=warning_threshold_percent,
        hard_stop_threshold_percent=hard_stop_threshold_percent,
        require_confirmation_over_amount=require_confirmation_over_amount,
        currency=currency,
        user_id="default",
    )
    return {"ok": True, "message": msg, "budget": get_budget_settings(user_id="default")}


@app.get("/api/backend/status")
async def api_backend_status():
    """Current backend/fallback status."""
    from src.backend_switching import get_backend_status

    try:
        return get_backend_status(user_id="default")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/backend/switch")
async def api_backend_switch(
    target: str = Form(...),
    reason: str = Form("creator_requested"),
    dry_run: int = Form(0),
    force: int = Form(0),
):
    """Creator-initiated backend switch with health-check fallback."""
    from src.backend_switching import switch_backend_provider

    try:
        result = await switch_backend_provider(
            target=target,
            reason=reason,
            dry_run=bool(int(dry_run)),
            force=bool(int(force)),
            requested_by="creator",
            user_id="default",
        )
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Reflex Gate API
# ---------------------------------------------------------------------------

@app.post("/api/reflex/respond")
async def api_reflex_respond(
    gate_id: str = Form(...),
    decision: str = Form(...),
    redirect_text: str = Form(""),
):
    """Resolve a pending approval gate.

    decision must be one of: approve | deny | redirect
    redirect_text is required when decision == redirect.
    """
    from src import reflex_gate
    if decision not in ("approve", "deny", "redirect"):
        return JSONResponse({"error": "decision must be approve|deny|redirect"}, status_code=400)
    ok = reflex_gate.resolve_gate(gate_id, decision, redirect_text=redirect_text)
    if not ok:
        return JSONResponse({"error": f"gate '{gate_id}' not found or already resolved"}, status_code=404)
    return {"ok": True, "gate_id": gate_id, "decision": decision}


@app.post("/api/reflex/interrupt")
async def api_reflex_interrupt(text: str = Form("")):
    """Trigger a mid-process interrupt.  The agent will halt at the next gate
    check and feed `text` back into its context as a redirect note."""
    from src import reflex_gate
    reflex_gate.trigger_interrupt(text)
    return {"ok": True, "interrupt_text": text}


@app.get("/api/reflex/pending")
async def api_reflex_pending():
    """List gate IDs currently waiting for a decision."""
    from src import reflex_gate
    return {"pending": reflex_gate.get_pending_gates()}


@app.get("/api/reflex/history")
async def api_reflex_history(limit: int = 50):
    """Return recent gate decisions."""
    from src.reflex_memory import get_recent_decisions
    return {"decisions": get_recent_decisions(limit=limit)}


@app.get("/api/reflex/patterns")
async def api_reflex_patterns():
    """Return all learned reflex patterns."""
    from src.reflex_memory import get_all_patterns
    return {"patterns": get_all_patterns()}


@app.post("/api/reflex/pattern/reset")
async def api_reflex_pattern_reset(pattern_key: str = Form(...)):
    """Delete a learned pattern so it reverts to first-time behaviour."""
    from src.reflex_memory import reset_pattern
    ok = reset_pattern(pattern_key)
    return {"ok": ok}


@app.post("/api/speak")
async def api_speak(request: Request, text: str = Form(...), voice: str = Form(None)):
    """Convert text to speech, return base64 mp3."""
    try:
        from src.user_settings import get_tts_voice
        username = get_current_user(request) or "default"
        voice_id = voice or get_tts_voice(username)
        audio_bytes = await synthesize(text, voice=voice_id)
        b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio": f"data:audio/mp3;base64,{b64}"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def get_current_user(request: Request) -> str | None:
    return request.cookies.get("session_user")


@app.get("/api/me")
async def api_me(request: Request):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    users_path = DATA_DIR / "users.json"
    permissions = ["tiles:view"]
    if users_path.exists():
        try:
            with open(users_path, encoding="utf-8") as f:
                users = json.load(f)
                for u in users:
                    if u.get("username") == username:
                        permissions = u.get("permissions", [])
                        break
        except Exception:
            pass
            
    return {"username": username, "permissions": permissions}


@app.post("/api/login")
async def api_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    import hashlib
    username = username.strip()
    users_path = DATA_DIR / "users.json"
    if not users_path.exists():
        return JSONResponse({"error": "No users registered"}, status_code=400)
        
    try:
        with open(users_path, encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        return JSONResponse({"error": "Failed to read users database"}, status_code=500)
        
    p_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    found = None
    for u in users:
        if u.get("username") == username and u.get("password_hash") == p_hash:
            found = u
            break
            
    if not found:
        return JSONResponse({"error": "Invalid username or password"}, status_code=401)
        
    response = JSONResponse({
        "ok": True, 
        "username": username, 
        "permissions": found.get("permissions", [])
    })
    response.set_cookie(
        key="session_user",
        value=username,
        httponly=True,
        max_age=3600 * 24 * 7,  # 7 days
        samesite="lax",
        secure=False,
    )
    return response


@app.post("/api/register")
async def api_register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    import hashlib
    username = username.strip()
    if not username:
        return JSONResponse({"error": "Username is required"}, status_code=400)
    if not password:
        return JSONResponse({"error": "Password is required"}, status_code=400)
        
    users_path = DATA_DIR / "users.json"
    users = []
    if users_path.exists():
        try:
            with open(users_path, encoding="utf-8") as f:
                users = json.load(f)
        except Exception:
            return JSONResponse({"error": "Failed to read users database"}, status_code=500)
            
    # Check if already exists
    for u in users:
        if u.get("username") == username:
            return JSONResponse({"error": "Username already exists"}, status_code=400)
            
    p_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    new_user = {
        "username": username,
        "password_hash": p_hash,
        "permissions": ["tiles:view"]  # Default permissions
    }
    users.append(new_user)
    
    try:
        with open(users_path, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except Exception:
        return JSONResponse({"error": "Failed to write user data"}, status_code=500)
        
    # Log this action to Andrew's unified memory database
    if agent:
        try:
            agent.memory.add_short_term(
                f"[System notification]: New user account '{username}' registered.",
                source_device="web_hub",
                source_channel="hub_activity",
                activity_type="user_registration",
                session_id=agent.memory.session_id
            )
        except Exception:
            pass
            
    # Auto log them in
    response = JSONResponse({
        "ok": True, 
        "username": username, 
        "permissions": new_user["permissions"]
    })
    response.set_cookie(
        key="session_user",
        value=username,
        httponly=True,
        max_age=3600 * 24 * 7,  # 7 days
        samesite="lax",
        secure=False,
    )
    return response


@app.post("/api/logout")
async def api_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("session_user")
    return response


@app.get("/api/tiles")
async def api_tiles(request: Request):
    """Retrieve webpage, app, and game tile configurations for the logged-in user."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    # Ensure global default tiles file exists
    global_tiles_path = DATA_DIR / "tiles.json"
    if not global_tiles_path.exists():
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(global_tiles_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_TILES, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    user_tiles_path = USER_PROFILES_DIR / username / "tiles.json"
    
    # Initialize from default tiles.json if not present
    if not user_tiles_path.exists():
        user_tiles_path.parent.mkdir(parents=True, exist_ok=True)
        if global_tiles_path.exists():
            import shutil
            try:
                shutil.copy(global_tiles_path, user_tiles_path)
            except Exception:
                pass
                
    if not user_tiles_path.exists():
        try:
            with open(user_tiles_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_TILES, f, indent=2, ensure_ascii=False)
        except Exception:
            return DEFAULT_TILES
        
    try:
        with open(user_tiles_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/tiles")
async def api_save_tiles(request: Request):
    """Save updated webpage, app, and game tile configurations for the logged-in user."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    try:
        body = await request.json()
        user_tiles_path = USER_PROFILES_DIR / username / "tiles.json"
        user_tiles_path.parent.mkdir(parents=True, exist_ok=True)
        with open(user_tiles_path, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)
            
        # Log this edit action to Andrew's unified memory database
        u_agent = get_agent_for_request(request)
        if u_agent:
            try:
                u_agent.memory.add_short_term(
                    f"[System notification]: Tiles configuration for user '{username}' was updated on the hub page.",
                    source_device="web_hub",
                    source_channel="hub_activity",
                    activity_type="tiles_update",
                    session_id=u_agent.memory.session_id
                )
            except Exception:
                pass
        return {"ok": True, "message": "Tiles saved successfully"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ingest")
async def api_ingest(metadata: str = Form(...)):
    """Ingest metadata from the Inspect buttons for debugging or auditing."""
    print(f"[TELEMETRY INGEST] Inspect info: {metadata}")
    return {"ok": True, "metadata": metadata}


@app.post("/api/launch")
async def api_launch(
    type: str = Form(...),
    path: str = Form(None),
    url: str = Form(None)
):
    """Launch local executables (apps/games) or open URLs (webpages)."""
    import subprocess
    import webbrowser
    try:
        if type == "webpage":
            if url:
                webbrowser.open(url)
                return {"ok": True, "message": f"Opened webpage: {url}"}
            return JSONResponse({"error": "url is required for webpage launch"}, status_code=400)
        elif type in ("app", "game"):
            if path:
                subprocess.Popen(path, shell=True)
                return {"ok": True, "message": f"Launched process: {path}"}
            return JSONResponse({"error": "path is required for app/game launch"}, status_code=400)
        else:
            return JSONResponse({"error": "invalid launch type"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/workshop/workspaces")
async def api_workshop_workspaces(request: Request):
    """List the user's sandbox directory and any subdirectories as selectable workspaces."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    sandbox_dir = (USER_PROFILES_DIR / username / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    candidates = [str(sandbox_dir).replace("\\", "/")]
    try:
        for p in sandbox_dir.rglob("*"):
            if p.is_dir() and not any(part.startswith('.') for part in p.parts):
                candidates.append(str(p.resolve()).replace("\\", "/"))
    except Exception:
        pass
        
    return {"workspaces": candidates}


@app.get("/api/workshop/files")
async def api_workshop_files(request: Request, workspace: str = None):
    """List all workspace files recursively inside the user's sandbox folder."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    sandbox_dir = (USER_PROFILES_DIR / username / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    if not workspace:
        root = sandbox_dir
    else:
        root = Path(workspace).resolve()
        # Enforce sandbox boundary check
        if not str(root).startswith(str(sandbox_dir)):
            return JSONResponse({"error": "Access Denied: Path outside sandbox"}, status_code=403)
            
    if not root.exists() or not root.is_dir():
        root = sandbox_dir
        
    files = []
    exclude_dirs = {".git", "node_modules", "__pycache__", ".gemini", "static", "templates", "src/web/frontend", "build", "dist"}
    exclude_exts = {".pyc", ".png", ".jpg", ".zip", ".exe", ".lnk", ".mp3", ".mp4", ".pdf", ".gz", ".db", ".sqlite"}
    
    def scan(directory):
        for path in directory.iterdir():
            try:
                if path.is_dir() and path.name not in exclude_dirs:
                    scan(path)
                elif path.is_file() and path.suffix not in exclude_exts:
                    files.append(str(path.resolve()).replace("\\", "/"))
            except Exception:
                continue
                
    scan(root)
    return {
        "workspace": str(root).replace("\\", "/"),
        "files": sorted(files)
    }


@app.get("/api/workshop/read")
async def api_workshop_read(request: Request, path: str):
    """Read a specific file's content, restricted to the user's sandbox directory."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    sandbox_dir = (USER_PROFILES_DIR / username / "sandbox").resolve()
    p = Path(path).resolve()
    
    # Enforce boundary check
    if not str(p).startswith(str(sandbox_dir)):
        return JSONResponse({"error": "Access Denied: Path outside sandbox"}, status_code=403)
        
    try:
        if not p.exists() or p.is_dir():
            return JSONResponse({"error": "File not found"}, status_code=404)
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Log this file-open action to Andrew's unified memory database
        u_agent = get_agent_for_request(request)
        if u_agent:
            try:
                u_agent.memory.add_short_term(
                    f"[System notification]: Travis opened/reviewed the file '{path}' in the workshop.",
                    source_device="workshop",
                    source_channel="workshop_activity",
                    activity_type="file_read",
                    file_path=path,
                    session_id=u_agent.memory.session_id
                )
            except Exception:
                pass
                
        return {"content": content}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/workshop/write")
async def api_workshop_write(request: Request, path: str = Form(...), content: str = Form(...)):
    """Overwrite/save a specific file's content, restricted to the user's sandbox directory."""
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    sandbox_dir = (USER_PROFILES_DIR / username / "sandbox").resolve()
    p = Path(path).resolve()
    
    # Enforce boundary check
    if not str(p).startswith(str(sandbox_dir)):
        return JSONResponse({"error": "Access Denied: Path outside sandbox"}, status_code=403)
        
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
            
        # Log this file-edit action to Andrew's unified memory database
        u_agent = get_agent_for_request(request)
        if u_agent:
            try:
                u_agent.memory.add_short_term(
                    f"[System notification]: Travis edited and saved the file '{path}' in the workshop.",
                    source_device="workshop",
                    source_channel="workshop_activity",
                    activity_type="file_write",
                    file_path=path,
                    session_id=u_agent.memory.session_id
                )
            except Exception:
                pass
                
        return {"ok": True, "message": f"Saved {path}"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/workshop/package")
async def api_workshop_package(request: Request):
    """Zips the user's sandbox directory and returns it as a downloadable ZIP file with run script launcher helpers."""
    import zipfile
    import io
    from fastapi.responses import StreamingResponse
    
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    sandbox_dir = (USER_PROFILES_DIR / username / "sandbox").resolve()
    if not sandbox_dir.exists() or not sandbox_dir.is_dir():
        return JSONResponse({"error": "No files found to package"}, status_code=404)
        
    zip_buffer = io.BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            has_files = False
            for file_path in sandbox_dir.rglob("*"):
                if file_path.is_file():
                    has_files = True
                    relative_path = file_path.relative_to(sandbox_dir)
                    zip_file.write(file_path, arcname=relative_path)
            
            if not has_files:
                return JSONResponse({"error": "No files found to package"}, status_code=404)
                
            # Add helper runner scripts if not present
            if not (sandbox_dir / "run.bat").exists():
                bat_content = "@echo off\necho Starting local web server for your project...\nstart http://localhost:8000\npython -m http.server 8000\n"
                zip_file.writestr("run.bat", bat_content)
            if not (sandbox_dir / "run.sh").exists():
                sh_content = "#!/bin/bash\necho \"Starting local web server for your project...\"\npython3 -m http.server 8000 &\nsleep 1\nopen http://localhost:8000 || xdg-open http://localhost:8000\n"
                zip_file.writestr("run.sh", sh_content)
                    
        zip_buffer.seek(0)
        
        headers = {
            "Content-Disposition": f'attachment; filename="{username}_project.zip"'
        }
        return StreamingResponse(
            zip_buffer,
            media_type="application/x-zip-compressed",
            headers=headers
        )
    except Exception as e:
        return JSONResponse({"error": f"Failed to package app: {str(e)}"}, status_code=500)


async def _stream_workshop_generator(prompt: str, file_content: str, filename: str, username: str | None):
    """Stream narration events, tool runs, file writes, and final responses as SSE."""
    queue: asyncio.Queue = asyncio.Queue()

    # Prevent context token length overflow (400 errors)
    max_chars = 30000
    if len(file_content) > max_chars:
        file_content = (
            file_content[:max_chars] +
            "\n\n... [Code truncated here to prevent context token overflow 400 errors] ..."
        )
        
    message_with_context = (
        f"Active Workspace File: {filename}\n\n"
        f"Code Contents:\n```\n{file_content}\n```\n\n"
        f"Travis's Instruction: {prompt}"
    )

    async def run_agent():
        try:
            from config.settings import in_workshop_mode
            in_workshop_mode.set(True)
            u_agent = get_agent_for_user(username)
            if not u_agent:
                await queue.put({"type": "error", "text": "Agent not ready"})
                return
            u_agent.memory.set_working("current_speaker_discord_id", None)
            
            # Setup device and location context tags in memory
            u_agent.memory.current_turn_metadata = {
                "source_device": "workshop",
                "source_channel": "workshop_chat",
                "session_id": u_agent.memory.session_id
            }
            
            result = await u_agent.chat(
                user_input=message_with_context,
                narrate_queue=queue,
                speaker_discord_id=None,
            )
            
            # Synthesize reply to Edge TTS base64 audio
            audio_base64 = None
            try:
                from src.user_settings import get_tts_voice
                voice_id = get_tts_voice(username or "default")
                audio_bytes = await synthesize(result, voice=voice_id)
                if audio_bytes:
                    audio_base64 = f"data:audio/mp3;base64,{base64.b64encode(audio_bytes).decode('utf-8')}"
            except Exception:
                pass
                
            await queue.put({"type": "response", "text": result, "audio": audio_base64})
        except Exception as e:
            await queue.put({"type": "error", "text": str(e)})
        finally:
            u_agent = get_agent_for_user(username)
            if u_agent:
                u_agent.memory.current_turn_metadata = {}
            await queue.put(None)

    asyncio.create_task(run_agent())

    while True:
        item = await queue.get()
        if item is None:
            break
        yield f"data: {json.dumps(item)}\n\n"


@app.post("/api/workshop/ai")
async def api_workshop_ai(
    request: Request,
    prompt: str = Form(...),
    file_content: str = Form(""),
    filename: str = Form("")
):
    """Call the agent's core chat pipeline and stream narration and updates back as SSE."""
    username = get_current_user(request)
    u_agent = get_agent_for_user(username)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
        
    # Enforce boundary check on filename if it is provided
    if filename and filename != "untitled":
        sandbox_dir = (USER_PROFILES_DIR / username / "sandbox").resolve()
        p = Path(filename)
        if not p.is_absolute():
            p = (sandbox_dir / p).resolve()
        else:
            p = p.resolve()
        if not str(p).startswith(str(sandbox_dir)):
            return JSONResponse({"error": "Access Denied: Path outside sandbox"}, status_code=403)
        
    return StreamingResponse(
        _stream_workshop_generator(prompt, file_content, filename, username),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



def run():
    import socket
    import uvicorn
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"\n  Mobile: http://{local_ip}:{WEB_PORT}\n")
    except Exception:
        pass
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)


if __name__ == "__main__":
    run()
