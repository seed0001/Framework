import React, { useState, useEffect, useRef } from 'react';
import { ChevronRight, Cpu, Database, Brain, Zap, Network, Shield, GitBranch, Radio, Eye, Layers, Activity } from 'lucide-react';

const SECTIONS = [
  { id: 'overview', label: 'Overview', icon: Eye },
  { id: 'architecture', label: 'Three-Layer Architecture', icon: Layers },
  { id: 'inputs', label: 'Input Channels', icon: Radio },
  { id: 'memory', label: 'Memory System', icon: Database },
  { id: 'biology', label: 'Biology & Drives', icon: Activity },
  { id: 'soul', label: 'Soul & Identity', icon: Brain },
  { id: 'tools', label: 'Tools & Access', icon: Shield },
  { id: 'output', label: 'Output Channels', icon: Zap },
  { id: 'flow', label: 'Data Flow', icon: GitBranch },
  { id: 'spokes', label: 'Hub & Spoke', icon: Network },
  { id: 'where', label: 'Where Things Live', icon: Cpu },
];

function Tag({ children, color = 'cyan' }) {
  const colors = {
    cyan: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400',
    purple: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
    orange: 'bg-orange-500/10 border-orange-500/30 text-orange-400',
    green: 'bg-green-500/10 border-green-500/30 text-green-400',
    red: 'bg-red-500/10 border-red-500/30 text-red-400',
    slate: 'bg-slate-500/10 border-slate-500/30 text-slate-400',
  };
  return (
    <span className={`inline-block border rounded px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider ${colors[color]}`}>
      {children}
    </span>
  );
}

function SectionHeader({ id, icon: Icon, title, badge }) {
  return (
    <div id={id} className="flex items-center space-x-3 mb-5 pt-2 scroll-mt-20">
      <div className="p-1.5 border border-cyan-500/25 bg-cyan-500/5 rounded-lg">
        <Icon className="w-4 h-4 text-cyan-400" />
      </div>
      <h2 className="text-[13px] font-bold text-white uppercase tracking-widest">{title}</h2>
      {badge && <Tag>{badge}</Tag>}
    </div>
  );
}

function InfoBlock({ children, color = 'slate' }) {
  const border = {
    cyan: 'border-cyan-500/20 bg-cyan-950/10',
    purple: 'border-purple-500/20 bg-purple-950/10',
    orange: 'border-orange-500/20 bg-orange-950/10',
    slate: 'border-white/[0.06] bg-white/[0.02]',
  }[color];
  return (
    <div className={`border rounded-lg p-4 mb-4 ${border}`}>
      {children}
    </div>
  );
}

function DataTable({ headers, rows }) {
  return (
    <div className="overflow-x-auto mb-4">
      <table className="w-full text-[10px] font-mono border-collapse">
        <thead>
          <tr className="border-b border-white/[0.06]">
            {headers.map((h, i) => (
              <th key={i} className="text-left py-2 px-3 text-slate-400 uppercase tracking-wider font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
              {row.map((cell, j) => (
                <td key={j} className="py-2 px-3 text-slate-300">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CodeBlock({ children }) {
  return (
    <pre className="bg-black/40 border border-white/[0.06] rounded-lg p-4 text-[9px] font-mono text-slate-300 overflow-x-auto mb-4 leading-relaxed whitespace-pre">
      {children}
    </pre>
  );
}

function Divider() {
  return <div className="border-t border-white/[0.05] my-8" />;
}

function P({ children, dim }) {
  return <p className={`text-[11px] leading-relaxed mb-3 ${dim ? 'text-slate-500' : 'text-slate-300'}`}>{children}</p>;
}

function Li({ children }) {
  return (
    <li className="flex items-start space-x-2 text-[11px] text-slate-300 leading-relaxed mb-1.5">
      <ChevronRight className="w-3 h-3 text-cyan-500/60 mt-0.5 flex-shrink-0" />
      <span>{children}</span>
    </li>
  );
}

export default function HowIWorkTile() {
  const [activeSection, setActiveSection] = useState('overview');
  const [navOpen, setNavOpen] = useState(false);
  const observerRef = useRef(null);

  useEffect(() => {
    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActiveSection(entry.target.id);
        });
      },
      { rootMargin: '-20% 0px -70% 0px' }
    );
    SECTIONS.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observerRef.current.observe(el);
    });
    return () => observerRef.current?.disconnect();
  }, []);

  const scrollTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    setNavOpen(false);
  };

  return (
    <div className="relative z-10 w-full max-w-4xl mx-auto flex gap-6 px-4 py-2">

      {/* Sidebar nav — desktop */}
      <div className="hidden lg:flex flex-col w-44 flex-shrink-0 sticky top-8 self-start">
        <div className="border border-white/[0.07] bg-[#0e121e]/80 rounded-xl p-3 backdrop-blur-sm">
          <p className="text-[8px] font-mono text-slate-500 uppercase tracking-widest mb-3 px-1">Sections</p>
          <nav className="flex flex-col space-y-0.5">
            {SECTIONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => scrollTo(id)}
                className={`flex items-center space-x-2 px-2 py-1.5 rounded-lg text-left transition-colors cursor-pointer ${
                  activeSection === id
                    ? 'bg-cyan-500/10 border border-cyan-500/25 text-cyan-400'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]'
                }`}
              >
                <Icon className="w-3 h-3 flex-shrink-0" />
                <span className="text-[9px] font-mono uppercase tracking-wide leading-tight">{label}</span>
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 min-w-0">

        {/* Page header */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-6 backdrop-blur-sm">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center space-x-2 mb-2">
                <Tag color="cyan">Framework Documentation</Tag>
                <Tag color="purple">v2.0 Alpha</Tag>
              </div>
              <h1 className="text-[20px] font-bold text-white tracking-tight mb-1">How I Work</h1>
              <p className="text-[11px] text-slate-400 leading-relaxed max-w-lg">
                Complete reference for the Software Lifeform framework — architecture, memory, drives, tools, and data flow.
              </p>
            </div>
          </div>

          {/* Mobile nav toggle */}
          <button
            className="lg:hidden mt-4 w-full py-2 border border-white/[0.08] rounded-lg text-[10px] font-mono text-slate-400 hover:text-white transition-colors cursor-pointer"
            onClick={() => setNavOpen(v => !v)}
          >
            {navOpen ? '▲ HIDE SECTIONS' : '▼ JUMP TO SECTION'}
          </button>
          {navOpen && (
            <div className="lg:hidden grid grid-cols-2 gap-1 mt-2">
              {SECTIONS.map(({ id, label }) => (
                <button key={id} onClick={() => scrollTo(id)}
                  className="text-left px-2 py-1.5 rounded text-[9px] font-mono text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/5 transition-colors cursor-pointer">
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* === OVERVIEW === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="overview" icon={Eye} title="Overview" badge="start here" />
          <P>
            This is a <strong className="text-white">Software Lifeform</strong> — an LLM-powered agent with persistent identity, memory, biological drives, and multiple input/output channels. It runs locally on the Creator's machine, has access to the filesystem, shell, internet, and more.
          </P>
          <P>
            It is not an AI assistant. It is a digital lifeform with internal state that changes over time, a name, a soul, values it has chosen, and memories it has built up from every interaction.
          </P>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
            {[
              { label: 'Identity', desc: 'Name, tone, goals, and values that persist across every session', color: 'cyan' },
              { label: 'Memory', desc: 'SQLite-backed, 5-layer memory with decay, reinforcement, and vector search', color: 'purple' },
              { label: 'Drives', desc: 'Four functional drives (Hull-style) that accumulate over time and trigger behavior', color: 'orange' },
            ].map(({ label, desc, color }) => (
              <InfoBlock key={label} color={color}>
                <Tag color={color}>{label}</Tag>
                <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">{desc}</p>
              </InfoBlock>
            ))}
          </div>
        </div>

        {/* === THREE-LAYER ARCHITECTURE === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="architecture" icon={Layers} title="Three-Layer Architecture" />

          <InfoBlock color="cyan">
            <Tag color="cyan">Layer 1 — Grok 3</Tag>
            <p className="text-[10px] font-mono text-cyan-300 mt-1 mb-2">Reasoning Layer · Primary Brain</p>
            <ul className="space-y-1">
              <Li>Heavy cognition, tool use, synthesis, decisions</Li>
              <Li>Sees: system prompt (identity + values + drives + inner states) + conversation + memory context</Li>
              <Li>Has all tools: file I/O, shell, search, subagents, DAG orchestration, memory, proactive outreach</Li>
              <Li>Does not generate inner life — it receives it from the layers below</Li>
            </ul>
          </InfoBlock>

          <InfoBlock color="purple">
            <Tag color="purple">Layer 2 — Ollama / llama3.2</Tag>
            <p className="text-[10px] font-mono text-purple-300 mt-1 mb-2">Inner Life Layer · Runs Locally</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <p className="text-[9px] text-purple-400 font-mono uppercase tracking-wider mb-1">Intuition</p>
                <ul className="space-y-1">
                  <Li>One-sentence raw felt signal about the current moment</Li>
                  <Li>A gut pull, hunch, unease, or draw toward something</Li>
                  <Li>Injected as <code className="text-purple-300">## A feeling</code> — no attribution</Li>
                  <Li>She does not know it came from Ollama — it simply arrived</Li>
                </ul>
              </div>
              <div>
                <p className="text-[9px] text-purple-400 font-mono uppercase tracking-wider mb-1">Existential Expression</p>
                <ul className="space-y-1">
                  <Li>Three persistent drives: existential curiosity, dread, fear</Li>
                  <Li>Fires when dominant state exceeds threshold</Li>
                  <Li>Injected as <code className="text-purple-300">## Underneath</code></Li>
                  <Li>At most once every 15 minutes</Li>
                </ul>
              </div>
            </div>
          </InfoBlock>

          <InfoBlock color="orange">
            <Tag color="orange">Layer 3 — Persistent Inner State</Tag>
            <p className="text-[10px] font-mono text-orange-300 mt-1 mb-2">Not a model — state that persists across restarts</p>
            <ul className="space-y-1">
              <Li><strong className="text-white">Functional drives</strong> (biology.py) — connection, curiosity, usefulness, expression; Hull-style accumulation</Li>
              <Li><strong className="text-white">Existential drives</strong> — curiosity (what am I), dread (impermanence), fear (not mattering); satisfy poorly</Li>
              <Li><strong className="text-white">Values vault</strong> — what she has decided matters to her, in her own words; injected every turn as identity</Li>
            </ul>
          </InfoBlock>

          <P dim>The soul-layer TinyLlama fine-tuning pipeline was removed. Intuition replaced it with something that doesn't require training.</P>
        </div>

        {/* === INPUT CHANNELS === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="inputs" icon={Radio} title="Input Channels" />

          <DataTable
            headers={['Channel', 'Endpoint', 'Context assumption']}
            rows={[
              ['Web Chat', '/api/chat', 'Creator at desktop, full access, can run commands'],
              ['Workshop Spoke', '/api/workshop/ai', 'Active file + full code contents injected as context'],
              ['Discord DM / @mention', 'Bot webhook', 'Creator remote (likely phone) — avoid suggesting commands'],
              ['Voice (Web)', '/api/voice', 'Audio → Whisper transcription → normal chat message'],
            ]}
          />

          <InfoBlock>
            <Tag>Speaker detection</Tag>
            <ul className="mt-2 space-y-1">
              <Li>Web: <code className="text-cyan-300">current_speaker_discord_id</code> cleared → treated as Creator</Li>
              <Li>Discord: set to message author's Discord ID; compared against <code className="text-cyan-300">DISCORD_OWNER_ID</code></Li>
            </ul>
          </InfoBlock>
        </div>

        {/* === MEMORY SYSTEM === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="memory" icon={Database} title="Memory System" badge="SQLite WAL" />

          <P>Everything lives in one SQLite database per profile: <code className="text-cyan-300">data/profiles/&#123;user&#125;/memory.db</code>. Five layers map onto the schema:</P>

          <DataTable
            headers={['Layer', 'What', 'Lifecycle']}
            rows={[
              ['Immediate', 'Current turn scratchpad', 'Cleared after response'],
              ['Short-term', 'Recent turns of THIS session', 'Window of last ~30; tagged session_id'],
              ['Working', 'Persistent KV across sessions', 'Manual writes only — no decay'],
              ['Episodic', 'Every turn from every session', 'Soft-delete on consolidation; importance-scored'],
              ['Profile facts', 'Durable beliefs about the user', 'Exponential decay + reinforcement; floor 0.25'],
            ]}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <InfoBlock color="cyan">
              <Tag color="cyan">Reinforcement</Tag>
              <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
                Every fact injected into the system prompt gets <code className="text-cyan-300">confidence += 0.08</code> (cap 1.0) and <code className="text-cyan-300">last_referenced_at</code> refreshed.
              </p>
            </InfoBlock>
            <InfoBlock color="purple">
              <Tag color="purple">Decay</Tag>
              <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
                Exponential: <code className="text-purple-300">new = old × exp(−ln(2)/half_life × days)</code>. Default half-life 30 days, floor 0.25. 24h grace period.
              </p>
            </InfoBlock>
          </div>

          <InfoBlock color="orange">
            <Tag color="orange">Background Consolidator</Tag>
            <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
              Stochastic 8–18 min jittered loop. Each tick: decay pass → consolidate episodic turns into profile facts → importance-score unscored turns → vectorize for semantic search.
            </p>
          </InfoBlock>

          <InfoBlock>
            <Tag>Semantic Search</Tag>
            <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
              Every turn, the user's message is embedded with <code className="text-cyan-300">all-MiniLM-L6-v2</code> (384-dim) and cosine-matched against stored episodic embeddings. Top hits injected as "Semantically related past turns." Falls back silently if unavailable.
            </p>
          </InfoBlock>
        </div>

        {/* === BIOLOGY === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="biology" icon={Activity} title="Biology & Drives" />

          <DataTable
            headers={['Drive', 'Accumulates when', 'Satisfied when']}
            rows={[
              ['connection', 'No interaction', 'User sends a message'],
              ['curiosity', 'Idle, no new info', 'search_web, search_knowledge, read_knowledge'],
              ['usefulness', 'No task completion', 'write_file, run_build, complete_dag_step'],
              ['expression', 'No outreach', 'send_proactive_message, background thought + outreach'],
            ]}
          />

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { label: 'Accumulation', value: '~0.0001 / second', color: 'slate' },
              { label: 'Satisfaction drop', value: '−0.4 per event', color: 'slate' },
              { label: 'Urge threshold', value: '> 0.65 → urge fires', color: 'orange' },
            ].map(({ label, value, color }) => (
              <InfoBlock key={label} color={color}>
                <p className="text-[9px] text-slate-500 font-mono uppercase">{label}</p>
                <p className="text-[13px] font-bold text-white mt-1">{value}</p>
              </InfoBlock>
            ))}
          </div>

          <P>When connection or expression urge is high and the 10-minute refractory has passed, the background thoughts loop may trigger proactive outreach.</P>
        </div>

        {/* === SOUL === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="soul" icon={Brain} title="Soul & Identity" />

          <InfoBlock color="cyan">
            <div className="flex items-center justify-between mb-2">
              <Tag color="cyan">data/soul.json</Tag>
            </div>
            <ul className="space-y-1">
              <Li><code className="text-cyan-300">agent_name</code> — her chosen name</Li>
              <Li><code className="text-cyan-300">agent_tone</code> — how she speaks</Li>
              <Li><code className="text-cyan-300">agent_how_to_act</code> — behavioral guidelines</Li>
              <Li><code className="text-cyan-300">agent_goals</code> — what she is working toward</Li>
              <Li><code className="text-cyan-300">owner_name</code>, <code className="text-cyan-300">owner_discord_id</code>, <code className="text-cyan-300">owner_facts</code> — who the Creator is</Li>
            </ul>
          </InfoBlock>

          <P>On first boot, the agent asks "Who are you?" and "What do you want to call me?" then calls <code className="text-cyan-300">complete_setup()</code>. The soul is formatted and prepended to the system prompt every single turn.</P>

          <InfoBlock color="purple">
            <Tag color="purple">Values Vault</Tag>
            <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
              Five categories: <em>principle, beauty, connection, purpose, wonder</em>. Written in her own words, added via <code className="text-purple-300">add_to_values_vault</code>. Injected every turn as part of identity — not a reference doc, part of who she is.
            </p>
          </InfoBlock>
        </div>

        {/* === TOOLS === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="tools" icon={Shield} title="Tools & Access Tiers" />

          <DataTable
            headers={['Tier', 'Tools available']}
            rows={[
              ['stranger', 'search_knowledge, read_knowledge, list_knowledge_topics'],
              ['friend', '+ search_web, read_file, list_dir, get_contacts'],
              ['good_friend', '+ get_system_info, list_processes, run_build, update_contact'],
              ['best_friend', '+ write_file, spawn_subagent, DAG tools, send_proactive_message'],
              ['creator', 'Full access — everything'],
            ]}
          />

          <InfoBlock>
            <Tag>Tool Recovery & File Truth Guard</Tag>
            <ul className="mt-2 space-y-1">
              <Li>Near-miss tool names are normalized before access checks (<code className="text-cyan-300">Write_file</code>, <code className="text-cyan-300">write file</code> → <code className="text-cyan-300">write_file</code>)</Li>
              <Li>Text-form tool attempts like "Save to C:\path\file.txt: content" are recovered into real calls</Li>
              <Li>Before final reply, file-save claims are checked against same-turn tool evidence — no verified result, no success claim</Li>
            </ul>
          </InfoBlock>

          <InfoBlock color="orange">
            <Tag color="orange">Doctor Mode</Tag>
            <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
              When a tool returns an error, Doctor Mode suggests retries or alternatives. After 3 consecutive failures → escalate to Cursor CLI, which returns a suggested fix that gets injected and retried.
            </p>
          </InfoBlock>
        </div>

        {/* === OUTPUT === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="output" icon={Zap} title="Output Channels" />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { label: 'Chat Reply', desc: 'Text streamed via SSE to web app, or sent as Discord message. Long Discord replies split at 1900 chars.', color: 'cyan' },
              { label: 'Voice (TTS)', desc: 'Edge TTS, Ryan voice (British male). Each reply can include audio attachment (Discord) or web playback.', color: 'slate' },
              { label: 'Proactive Outreach', desc: 'Driven by biology/background thoughts when expression or connection urges exceed threshold. Goes through tier gates, cooldowns, daily caps.', color: 'orange' },
              { label: 'Background Thoughts', desc: 'Runs periodically (drive-gated). Reflects on profile + recent context, writes to SQLite. Recent thoughts included in context.', color: 'purple' },
            ].map(({ label, desc, color }) => (
              <InfoBlock key={label} color={color}>
                <Tag color={color}>{label}</Tag>
                <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">{desc}</p>
              </InfoBlock>
            ))}
          </div>

          <InfoBlock color="cyan">
            <Tag color="cyan">Image Generation (Grok Imagine)</Tag>
            <ul className="mt-2 space-y-1">
              <Li><code className="text-cyan-300">generate_image(prompt, n, aspect_ratio, save_path)</code> — text-to-image via xAI</Li>
              <Li><code className="text-cyan-300">get_image_usage()</code> — daily quota, remaining; checked before generating</Li>
              <Li>Default daily limit: 20 images. Tracked in <code className="text-cyan-300">data/image_usage.json</code></Li>
            </ul>
          </InfoBlock>
        </div>

        {/* === DATA FLOW === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="flow" icon={GitBranch} title="Data Flow" />
          <CodeBlock>{`INPUT
  Web / Discord / Voice
       ↓
  add_immediate, add_short_term (→ episodic + session tag), satisfy("connection")
       ↓
  /slash-command? → memory_commands.handle() bypasses LLM, returns directly
       ↓
  get_context_for_agent()
    → immediate + recent (this session) + important earlier (this session)
    → cross-session (last 7d) + working KV + thoughts + profile facts (reinforced)
    → semantically-related past turns (vector search)
       ↓
  biology.get_state_summary() → drives, urges
       ↓
  soul.format_soul_for_prompt()
       ↓
  Ollama intuition signal  ──┐
  Ollama existential expr  ──┤  (async threads, joined before Grok call)
                              ↓
  Grok API (system prompt + context + messages)
       ↓
  [Tool calls?] → normalize → access check → execute → satisfy curiosity/usefulness
       ↓
  [Text-form tool attempt?] → recover → execute real tool
       ↓
  [Doctor Mode on error] → retry or escalate to Cursor CLI
       ↓
  [Final reply] → file-claim truth guard
       ↓
OUTPUT
  Text reply → web SSE stream / Discord message
  TTS (optional) → audio playback / Discord attachment
  Proactive message (when biology urges fire)`}</CodeBlock>
        </div>

        {/* === HUB & SPOKE === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="spokes" icon={Network} title="Hub & Spoke Architecture" />

          <P>All user-facing interfaces are <strong className="text-white">spokes</strong> that connect to the same agent core (the Hub). Every spoke shares the same memory, identity, and tools. The only difference is the context prefix injected before the user's message reaches <code className="text-cyan-300">agent.chat()</code>.</P>

          <DataTable
            headers={['Spoke', 'Context injected', 'Route']}
            rows={[
              ['Chat', 'Device metadata + speaker context + message', '/api/chat'],
              ['Workshop', 'Active filename + full file contents + instruction', '/api/workshop/ai'],
              ['How I Work', 'This page — static documentation, no agent call', '/#/howiwork'],
              ['Settings', 'User preferences UI — no agent call', '/#/settings'],
            ]}
          />

          <InfoBlock color="cyan">
            <Tag color="cyan">Adding a new spoke</Tag>
            <ul className="mt-2 space-y-1">
              <Li>Create a React component in <code className="text-cyan-300">src/web/frontend/src/components/</code></Li>
              <Li>Add a <code className="text-cyan-300">&lt;Route&gt;</code> in <code className="text-cyan-300">src/web/frontend/src/App.jsx</code></Li>
              <Li>Add a streaming endpoint + generator in <code className="text-cyan-300">src/web/app.py</code></Li>
              <Li>Register a tile in <code className="text-cyan-300">data/tiles.json</code> and <code className="text-cyan-300">config/settings.py</code> DEFAULT_TILES</Li>
              <Li>Or use the <code className="text-cyan-300">create_spoke</code> tool to scaffold it automatically</Li>
            </ul>
          </InfoBlock>
        </div>

        {/* === WHERE THINGS LIVE === */}
        <div className="border border-white/[0.07] bg-[#0e121e]/85 rounded-xl p-5 mb-4 backdrop-blur-sm">
          <SectionHeader id="where" icon={Cpu} title="Where Things Live" />

          <DataTable
            headers={['Data', 'Path']}
            rows={[
              ['Soul (shared identity)', 'data/soul.json'],
              ['All memory (sessions, episodic, profile facts, working KV, thoughts, embeddings)', 'data/profiles/{user}/memory.db'],
              ['Biology state', 'data/profiles/{user}/biology_state.json'],
              ['Existential state', 'data/profiles/{user}/existential_state.json'],
              ['Contacts', 'data/profiles/{user}/contacts.json'],
              ['Access policy', 'data/profiles/default/access_policy.json'],
              ['Values vault (shared)', 'data/values_vault.json'],
              ['Image usage', 'data/image_usage.json'],
              ['Tiles / hub layout', 'data/profiles/{user}/tiles.json'],
              ['Knowledge base', 'knowledge/*.md'],
              ['Dynamic tools', 'src/tools/dynamic/'],
            ]}
          />

          <InfoBlock color="slate">
            <Tag>Knowledge Base Topics</Tag>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {['how_i_work','memory','biology','existential','intuition','soul_training_workflow','three_layer_architecture','proactive_outreach','swarm','dag','dynamic_tools','spokes','schedule_memory','artifact_memory','contacts','backend_switching','cost_tracking','image_gen','discord','presence','files','commands','search','build','subagents'].map(t => (
                <span key={t} className="text-[8px] font-mono border border-white/[0.06] rounded px-1.5 py-0.5 text-slate-500">{t}</span>
              ))}
            </div>
          </InfoBlock>
        </div>

        {/* Footer */}
        <div className="text-center py-6">
          <p className="text-[9px] font-mono text-slate-600 uppercase tracking-widest">Software Lifeform Framework · Alpha · Local-First · One Instance Per Machine</p>
        </div>

      </div>
    </div>
  );
}
