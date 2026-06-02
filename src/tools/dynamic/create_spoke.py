"""
Dynamic tool: scaffold a new spoke (interface tile) into the web app.
Generates the React component, registers the route in App.jsx, and adds
the backend endpoint block to app.py. Travis still needs to npm run build.
"""

import json
import re
from pathlib import Path

TOOL_DEF = {
    "name": "create_spoke",
    "description": (
        "Scaffold a new spoke (interface/tile) into the web app. "
        "Creates the React component file, adds the route to App.jsx, "
        "and appends the backend endpoint + stream generator to app.py. "
        "Use this when Travis wants a new section/tool/interface added to the dashboard. "
        "After running, do `run_build` on the frontend to make it live."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short camelCase name for the spoke, e.g. 'journal', 'taskBoard', 'gallery'. Used to derive file/class names and URL path."
            },
            "label": {
                "type": "string",
                "description": "Human-readable label shown in the UI header, e.g. 'Journal', 'Task Board'."
            },
            "description": {
                "type": "string",
                "description": "One sentence describing what this spoke does. Injected as the assistant welcome message and as context to me on each call."
            },
            "context_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of extra form fields the spoke will POST alongside the user prompt (e.g. ['entry_id', 'filter_tag']). Each becomes a Form(...) param in the endpoint."
            }
        },
        "required": ["name", "label", "description"]
    }
}


def _pascal(name: str) -> str:
    return name[0].upper() + name[1:]


def _kebab(name: str) -> str:
    # camelCase -> kebab-case
    s = re.sub(r'([A-Z])', r'-\1', name).lower().lstrip('-')
    return s


async def run(name: str, label: str, description: str, context_fields: list = None) -> str:
    context_fields = context_fields or []
    pascal = _pascal(name)
    kebab = _kebab(name)
    route_path = f"/{kebab}"
    api_path = f"/api/{kebab}/ai"
    component_name = f"{pascal}Tile"
    component_file = f"{component_name}.jsx"

    root = Path(__file__).resolve().parents[3]  # Framework-main/
    frontend_components = root / "src" / "web" / "frontend" / "src" / "components"
    app_jsx = root / "src" / "web" / "frontend" / "src" / "App.jsx"
    app_py = root / "src" / "web" / "app.py"

    results = []

    # ── 1. React component ────────────────────────────────────────────────────
    component_path = frontend_components / component_file
    if component_path.exists():
        results.append(f"SKIP: {component_file} already exists — not overwritten.")
    else:
        extra_fields_state = "\n".join(
            f"  const [{f}, set{_pascal(f)}] = useState('');" for f in context_fields
        )
        extra_fields_form = "\n".join(
            f"        formData.append('{f}', {f});" for f in context_fields
        )
        extra_inputs = "\n".join(
            f"""        <input
          type="text"
          placeholder="{f}"
          value={{{f}}}
          onChange={{(e) => set{_pascal(f)}(e.target.value)}}
          className="bg-black/30 border border-white/[0.08] rounded-xl px-4 py-2.5 text-[15px] text-[#e8eaf0] focus:outline-none focus:border-cyan-500/50 placeholder:text-slate-500"
        />"""
            for f in context_fields
        )

        jsx = f"""import React, {{ useState, useRef, useEffect }} from 'react';
import {{ Send }} from 'lucide-react';

export default function {component_name}() {{
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([
    {{ role: 'assistant', text: '{description}' }}
  ]);
  const [loading, setLoading] = useState(false);
{extra_fields_state}
  const endRef = useRef(null);

  useEffect(() => {{
    endRef.current?.scrollIntoView({{ behavior: 'smooth' }});
  }}, [messages, loading]);

  const handleSubmit = async (e) => {{
    e.preventDefault();
    if (!input.trim() || loading) return;
    const userText = input.trim();
    setInput('');
    setMessages(prev => [...prev, {{ role: 'user', text: userText }}]);
    setLoading(true);

    try {{
      const formData = new FormData();
      formData.append('prompt', userText);
{extra_fields_form}

      const response = await fetch('{api_path}', {{ method: 'POST', body: formData }});
      if (!response.ok) throw new Error('Request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let agentText = '';

      setMessages(prev => [...prev, {{ role: 'assistant', text: '' }}]);

      while (true) {{
        const {{ value, done }} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {{ stream: true }});
        const lines = buffer.split('\\n');
        buffer = lines.pop() || '';
        for (const line of lines) {{
          const trimmed = line.trim();
          if (trimmed.startsWith('data:')) {{
            try {{
              const parsed = JSON.parse(trimmed.slice(5).trim());
              if (parsed.type === 'response' || parsed.type === 'narration') {{
                agentText += parsed.text;
                setMessages(prev => {{
                  const updated = [...prev];
                  updated[updated.length - 1] = {{ role: 'assistant', text: agentText }};
                  return updated;
                }});
              }}
            }} catch (_) {{}}
          }}
        }}
      }}
    }} catch (err) {{
      setMessages(prev => [...prev, {{ role: 'system', text: `ERROR: ${{err.message}}` }}]);
    }} finally {{
      setLoading(false);
    }}
  }};

  return (
    <div className="flex flex-col h-[500px] rounded-xl border border-white/[0.07] bg-[#0e121e]/85 backdrop-blur-md shadow-2xl overflow-hidden">
      {{/* Header */}}
      <div className="flex items-center px-4 py-3 bg-black/20 border-b border-white/[0.05] text-xs font-semibold tracking-wider text-cyan-400 uppercase">
        {label}
      </div>

      {{/* Messages */}}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm leading-relaxed">
        {{messages.map((msg, idx) => (
          <div key={{idx}} className={{`flex flex-col ${{msg.role === 'user' ? 'items-end' : 'items-start'}}`}}>
            <div className={{`text-[10px] uppercase font-mono tracking-wider mb-1 ${{
              msg.role === 'user' ? 'text-cyan-400/80' : msg.role === 'system' ? 'text-red-400' : 'text-purple-400/80'
            }}`}}>
              {{msg.role}}
            </div>
            <div className={{`${{msg.role === 'assistant'
              ? 'border-l-2 border-purple-500/35 pl-3 py-0.5 text-[#e8eaf0] max-w-full'
              : msg.role === 'system'
              ? 'text-red-400 font-mono text-[12px] bg-red-950/20 border border-red-500/10 rounded px-2 py-1'
              : 'rounded-xl px-3 py-1.5 bg-[#161c2e] border border-cyan-500/10 text-[#e8eaf0] max-w-[85%]'
            }}`}}>
              {{msg.text}}
            </div>
          </div>
        ))}}
        {{loading && (
          <div className="flex flex-col items-start">
            <div className="text-[10px] font-mono text-purple-400/80 uppercase tracking-wider mb-1">assistant</div>
            <div className="border-l-2 border-purple-500/35 pl-3 py-0.5 text-[#e8eaf0]">
              <span className="typing-cursor" />
            </div>
          </div>
        )}}
        <div ref={{endRef}} />
      </div>

      {{/* Input */}}
      <form onSubmit={{handleSubmit}} className="p-3 border-t border-white/[0.05] bg-black/10 flex flex-col space-y-2">
{extra_inputs}
        <div className="flex items-center space-x-2">
          <input
            type="text"
            value={{input}}
            onChange={{(e) => setInput(e.target.value)}}
            placeholder="Send a message..."
            disabled={{loading}}
            className="flex-1 bg-black/30 border border-white/[0.08] rounded-xl px-4 py-2.5 text-[15px] text-[#e8eaf0] focus:outline-none focus:border-cyan-500/50 placeholder:text-slate-500"
          />
          <button
            type="submit"
            disabled={{loading}}
            className="bg-gradient-to-r from-cyan-400 to-[#0090cc] text-slate-900 font-bold p-2.5 rounded-full flex items-center justify-center transition-all shadow-[0_0_12px_rgba(0,212,255,0.25)] disabled:opacity-30"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
}}
"""
        component_path.write_text(jsx, encoding="utf-8")
        results.append(f"CREATED: {component_file}")

    # ── 2. Route in App.jsx ───────────────────────────────────────────────────
    app_jsx_text = app_jsx.read_text(encoding="utf-8")

    import_line = f"import {component_name} from './components/{component_file}';"
    if import_line not in app_jsx_text:
        # Insert after last existing import
        last_import_match = list(re.finditer(r"^import .+from '.+';$", app_jsx_text, re.MULTILINE))
        if last_import_match:
            insert_pos = last_import_match[-1].end()
            app_jsx_text = app_jsx_text[:insert_pos] + "\n" + import_line + app_jsx_text[insert_pos:]
            results.append(f"ADDED import for {component_name} in App.jsx")
        else:
            results.append("WARN: could not find import block in App.jsx — add import manually.")

    route_snippet = f'path="{route_path}"'
    if route_snippet not in app_jsx_text:
        # Insert before closing </Routes>
        routes_close = app_jsx_text.rfind("</Routes>")
        if routes_close != -1:
            new_route = f"""          <Route
            path="{route_path}"
            element={{
              <div className="relative z-10 max-w-3xl mx-auto w-full flex flex-col space-y-4 px-4">
                <div className="animate-fade-in">
                  <{component_name} />
                </div>
              </div>
            }}
          />
"""
            app_jsx_text = app_jsx_text[:routes_close] + new_route + "        " + app_jsx_text[routes_close:]
            results.append(f"ADDED route {route_path} in App.jsx")
        else:
            results.append("WARN: could not find </Routes> in App.jsx — add route manually.")
    else:
        results.append(f"SKIP: route {route_path} already exists in App.jsx")

    app_jsx.write_text(app_jsx_text, encoding="utf-8")

    # ── 3. Backend endpoint in app.py ─────────────────────────────────────────
    app_py_text = app_py.read_text(encoding="utf-8")

    endpoint_marker = f'"/api/{kebab}/ai"'
    if endpoint_marker in app_py_text:
        results.append(f"SKIP: endpoint /api/{kebab}/ai already exists in app.py")
    else:
        extra_form_params = "\n".join(
            f"    {f}: str = Form(\"\")," for f in context_fields
        )
        extra_context_build = "\n".join(
            f'    spoke_context += f"\\n{f}: {{{f}}}"' for f in context_fields
        )
        extra_fn_args = ", ".join(f"{f}: str = Form(\"\")" for f in context_fields)
        extra_pass_args = ", ".join(f"{f}={f}" for f in context_fields)

        generator_fn = f'''

async def _stream_{name}_generator(prompt: str, username: str | None{", " + ", ".join(f"{f}: str" for f in context_fields) if context_fields else ""}):
    """Stream responses for the {label} spoke."""
    queue: asyncio.Queue = asyncio.Queue()
    spoke_context = "[{label} spoke] {description}\\n\\nUser: " + prompt
{extra_context_build}

    async def run_agent():
        try:
            u_agent = get_agent_for_user(username)
            if not u_agent:
                await queue.put({{"type": "error", "text": "Agent not ready"}})
                return
            u_agent.memory.current_turn_metadata = {{
                "source_channel": "{kebab}",
                "session_id": u_agent.memory.session_id
            }}
            response = await u_agent.chat(spoke_context, narrate_queue=queue)
            await queue.put({{"type": "response", "text": response}})
        except Exception as e:
            await queue.put({{"type": "error", "text": str(e)}})
        finally:
            await queue.put(None)

    asyncio.create_task(run_agent())

    async def generate():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {{json.dumps(item)}}\\n\\n"

    return generate()


@app.post("/api/{kebab}/ai")
async def api_{name}_ai(
    request: Request,
    prompt: str = Form(...),
{extra_form_params}
):
    username = get_current_user(request)
    u_agent = get_agent_for_user(username)
    if not u_agent:
        return JSONResponse({{"error": "Agent not ready"}}, status_code=503)
    return StreamingResponse(
        _stream_{name}_generator(prompt, username{", " + extra_pass_args if context_fields else ""}),
        media_type="text/event-stream",
        headers={{"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}},
    )
'''

        # Insert before the final run() function
        insert_before = "\ndef run():"
        insert_pos = app_py_text.rfind(insert_before)
        if insert_pos != -1:
            app_py_text = app_py_text[:insert_pos] + generator_fn + app_py_text[insert_pos:]
            app_py.write_text(app_py_text, encoding="utf-8")
            results.append(f"ADDED endpoint /api/{kebab}/ai and generator to app.py")
        else:
            results.append("WARN: could not find run() in app.py — add endpoint manually.")

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = "\n".join(results)
    next_steps = (
        f"\nNext steps:\n"
        f"1. Review the generated files (they may need customization for the spoke's specific UI).\n"
        f"2. Run: cd src/web/frontend && npm run build\n"
        f"3. Restart the server or the build will be picked up on next start.\n"
        f"4. Navigate to /#/{kebab} to see the new spoke.\n"
        f"5. Optionally add a tile entry in the System Registry via manage_tiles."
    )
    return summary + next_steps
