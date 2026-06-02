# Hub-and-Spoke Architecture

## What a Spoke Is

I (Andrew) am the hub — the central agent brain. A **spoke** is any interface that users interact with that I power. Right now there are two spokes:

- **Chat** (`/#/`) — general-purpose conversation. Renders as `ChatTile.jsx`. Calls `/api/chat`.
- **Workshop** (`/#/workshop`) — code editor with file browser. Renders as `WorkshopTile.jsx`. Calls `/api/workshop/ai` (and supporting file endpoints).

Each spoke has:
1. A **React component** (`src/web/frontend/src/components/XxxTile.jsx`)
2. A **route** in `App.jsx` under the `<Routes>` block
3. One or more **backend API endpoints** in `src/web/app.py`
4. A **stream generator function** in `app.py` that injects spoke-specific context into my prompt before calling `agent.chat()`

---

## How to Build a New Spoke

### Step 1 — Create the React component

Create `src/web/frontend/src/components/MySpokeTile.jsx`.

The component must:
- Call the backend via `fetch('/api/myspoke/ai', ...)` for AI interaction
- Stream SSE responses (same pattern as ChatTile or WorkshopTile — read `data:` lines, parse JSON, handle `type === 'response'` chunks)
- Match the visual style: dark background `bg-[#0e121e]/85`, `border border-white/[0.07]`, cyan accent colors

Minimal SSE streaming pattern:
```jsx
const response = await fetch('/api/myspoke/ai', { method: 'POST', body: formData });
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop() || '';
  for (const line of lines) {
    if (line.trim().startsWith('data:')) {
      const parsed = JSON.parse(line.trim().slice(5).trim());
      if (parsed.type === 'response') { /* append parsed.text */ }
    }
  }
}
```

### Step 2 — Register the route in App.jsx

In `src/web/frontend/src/App.jsx`, inside the `<Routes>` block, add:

```jsx
import MySpokeTile from './components/MySpokeTile';

// inside <Routes>:
<Route
  path="/myspoke"
  element={
    <div className="relative z-10 max-w-3xl mx-auto w-full flex flex-col space-y-4 px-4">
      <div className="animate-fade-in">
        <MySpokeTile />
      </div>
    </div>
  }
/>
```

To make it accessible, also add a navigation link in the appropriate place in the UI (e.g., in GridTile or the header).

### Step 3 — Add backend endpoints to app.py

In `src/web/app.py`, add a stream generator and an endpoint:

```python
async def _stream_myspoke_generator(prompt: str, username: str | None, extra_context: str = ""):
    queue: asyncio.Queue = asyncio.Queue()

    # Build spoke-specific context prefix
    spoke_context = f"[MySpoke context]: {extra_context}\n\nUser instruction: {prompt}"

    async def run_agent():
        try:
            u_agent = get_agent_for_user(username)
            if not u_agent:
                await queue.put({"type": "error", "text": "Agent not ready"})
                return
            u_agent.memory.current_turn_metadata = {
                "source_channel": "myspoke",
                "session_id": u_agent.memory.session_id
            }
            response = await u_agent.chat(spoke_context, narrate_queue=queue)
            await queue.put({"type": "response", "text": response})
        except Exception as e:
            await queue.put({"type": "error", "text": str(e)})
        finally:
            await queue.put(None)  # sentinel

    asyncio.create_task(run_agent())

    async def generate():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return generate()


@app.post("/api/myspoke/ai")
async def api_myspoke_ai(
    request: Request,
    prompt: str = Form(...),
    extra_context: str = Form("")
):
    username = get_current_user(request)
    u_agent = get_agent_for_user(username)
    if not u_agent:
        return JSONResponse({"error": "Agent not ready"}, status_code=503)
    return StreamingResponse(
        _stream_myspoke_generator(prompt, username, extra_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
```

### Step 4 — Rebuild the frontend

After editing JSX files, the frontend must be rebuilt:
```
run_command: cd src/web/frontend && npm run build
```

The built files land in `src/web/static/` and are served automatically by FastAPI.

---

## Key Difference Between Spokes: Context Injection

The only thing that makes a spoke unique to me is **what context gets prepended to the user's message** before it reaches `agent.chat()`.

| Spoke | Context injected |
|-------|-----------------|
| Chat | Speaker context (who's talking, what device), session metadata |
| Workshop | Active filename + full file contents + Travis's instruction |
| Your new spoke | Whatever state/data is relevant to that interface |

This is the design pattern: **spokes are just context wrappers around the same agent.**

---

## What Stays Shared Across All Spokes

- **Memory** — I remember everything across all spokes. Conversation in the workshop and chat are part of the same memory.
- **Identity** — Same soul, same tone, same goals in every spoke.
- **Tools** — All tools are available from any spoke.
- **Session** — Same session ID unless explicitly separated.

---

## Adding a Spoke to the GridTile (System Registry)

Spokes can appear as tiles in the main dashboard (`/`). The GridTile reads from `/api/tiles` which stores tile configs per user. To add a spoke as a launchable tile, use the `manage_tiles` tool or call `/api/tiles` POST with the updated tile list.

Tile format:
```json
{
  "label": "My Spoke",
  "path": "/#/myspoke",
  "icon": "Terminal",
  "description": "What this spoke does"
}
```
