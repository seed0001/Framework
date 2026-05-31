import React, { useState, useEffect, useRef } from 'react';
import { Save, Sparkles, FileText, ArrowRight, Folder } from 'lucide-react';

export default function WorkshopTile() {
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState('');
  const [code, setCode] = useState('');
  const [aiPrompt, setAiPrompt] = useState('');
  const [chatHistory, setChatHistory] = useState([
    { role: 'assistant', text: 'Welcome to your Development Workshop. Select a workspace folder from the dropdown, choose any file, and ask me to help you debug, refactor, or explain the code.' }
  ]);
  const [status, setStatus] = useState('Ready');
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  
  // Workspace selection state
  const [workspaceOptions, setWorkspaceOptions] = useState([]);
  const [currentWorkspace, setCurrentWorkspace] = useState('');

  const responseEndRef = useRef(null);
  const lineRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    fetchWorkspaces();
    fetchFiles();
  }, []);

  useEffect(() => {
    responseEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, aiLoading]);

  const fetchWorkspaces = async () => {
    try {
      const res = await fetch('/api/workshop/workspaces');
      if (res.ok) {
        const data = await res.json();
        setWorkspaceOptions(data.workspaces || []);
      }
    } catch (e) {
      console.error('Failed to retrieve workspaces list:', e);
    }
  };

  const fetchFiles = async (targetPath = '') => {
    try {
      const url = targetPath ? `/api/workshop/files?workspace=${encodeURIComponent(targetPath)}` : '/api/workshop/files';
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setFiles(data.files || []);
        setCurrentWorkspace(data.workspace || '');
        setStatus(`Loaded workspace: ${data.workspace}`);
      } else {
        const errData = await res.json();
        setStatus(`Failed: ${errData.error || 'Failed to load file explorer'}`);
      }
    } catch (e) {
      setStatus(`Explorer Error: ${e.message}`);
    }
  };

  const handleSelectFile = async (filePath) => {
    setSelectedFile(filePath);
    setStatus(`Loading ${filePath}...`);
    try {
      const res = await fetch(`/api/workshop/read?path=${encodeURIComponent(filePath)}`);
      if (res.ok) {
        const data = await res.json();
        setCode(data.content || '');
        setStatus(`Active: ${filePath}`);
        // Reset chat with context of the file
        setChatHistory([
          { role: 'assistant', text: `Loaded file: ${filePath.split('/').pop()}. Ask me anything about this file, or request edits.` }
        ]);
      } else {
        setStatus('Error reading file');
      }
    } catch (e) {
      setStatus(`Read Error: ${e.message}`);
    }
  };

  const handleSave = async () => {
    if (!selectedFile) return;
    setLoading(true);
    setStatus('Saving changes...');
    try {
      const formData = new FormData();
      formData.append('path', selectedFile);
      formData.append('content', code);

      const res = await fetch('/api/workshop/write', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setStatus(`Saved: ${selectedFile}`);
      } else {
        setStatus(`Save Error: ${data.error || 'Failed'}`);
      }
    } catch (e) {
      setStatus(`Save Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleScroll = () => {
    if (lineRef.current && textareaRef.current) {
      lineRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  const handleAiRequest = async (e) => {
    e.preventDefault();
    if (!aiPrompt.trim() || aiLoading) return;

    const userMessageText = aiPrompt;
    setChatHistory(prev => [...prev, { role: 'user', text: userMessageText }]);
    setAiPrompt('');
    setAiLoading(true);

    try {
      const formData = new FormData();
      formData.append('prompt', userMessageText);
      formData.append('file_content', code);
      formData.append('filename', selectedFile || 'untitled');

      const res = await fetch('/api/workshop/ai', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        throw new Error('Could not communicate with the LLM API.');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let assistantText = '';

      // Initialize the assistant turn placeholder in the chat panel
      setChatHistory(prev => [...prev, { role: 'assistant', text: '' }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data:')) {
            try {
              const rawData = trimmed.slice(5).trim();
              const parsed = JSON.parse(rawData);

              if (parsed.type === 'narrate') {
                setStatus(`AI: ${parsed.text}`);
              } else if (parsed.type === 'response') {
                assistantText += parsed.text || '';
                setChatHistory(prev => {
                  const updated = [...prev];
                  if (updated.length > 0) {
                    updated[updated.length - 1] = { role: 'assistant', text: assistantText };
                  }
                  return updated;
                });
                if (parsed.audio) {
                  const audio = new Audio(parsed.audio);
                  audio.play().catch(err => console.error('TTS Play Error:', err));
                }
              } else if (parsed.type === 'file_update') {
                // Normalize paths to ensure they match selectedFile format
                const normPath = parsed.path.replace(/\\/g, '/').toLowerCase();
                const normSelected = (selectedFile || '').replace(/\\/g, '/').toLowerCase();
                if (normPath === normSelected) {
                  setCode(parsed.content);
                  setStatus(`Auto-loaded edits for ${parsed.path.split('/').pop()}`);
                }
              } else if (parsed.type === 'error') {
                setChatHistory(prev => [...prev, { role: 'assistant', text: `AI Error: ${parsed.text}` }]);
              }
            } catch (err) {
              // ignore malformed JSON chunk
            }
          }
        }
      }
    } catch (error) {
      setChatHistory(prev => [...prev, { role: 'assistant', text: `Connection Error: ${error.message}` }]);
    } finally {
      setAiLoading(false);
    }
  };

  // Split lines for IDE line numbers
  const lines = code.split('\n');
  const lineCount = Math.max(lines.length, 1);

  return (
    <div className="flex flex-col border border-white/[0.08] bg-[#0c0e17]/90 backdrop-blur-md rounded-xl overflow-hidden shadow-2xl h-[680px] font-sans">
      {/* Title Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/30 border-b border-white/[0.06] text-[11px] font-bold tracking-wider text-slate-300">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-cyan-500 animate-pulse"></div>
          <span className="uppercase">WORKSPACE EDITOR (CURSOR CLONE)</span>
        </div>
        <span className="text-[9px] font-mono text-cyan-400 bg-cyan-950/30 border border-cyan-500/30 px-2.5 py-0.5 rounded-full uppercase">
          CONNECTED TO API KEY
        </span>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Explorer Sidebar */}
        <div className="w-[220px] border-r border-white/[0.06] bg-black/20 flex flex-col">
          {/* Workspace Path Dropdown Selection */}
          <div className="p-2.5 border-b border-white/[0.06] bg-black/10 flex flex-col space-y-1.5">
            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">SELECT WORKSPACE</span>
            <select
              value={currentWorkspace}
              onChange={(e) => {
                const newWorkspace = e.target.value;
                fetchFiles(newWorkspace);
              }}
              className="w-full bg-black/45 border border-white/[0.08] focus:border-cyan-500/50 rounded px-2.5 py-1.5 text-[10px] text-slate-300 font-mono focus:outline-none cursor-pointer"
            >
              {workspaceOptions.length === 0 ? (
                <option value="">Loading workspaces...</option>
              ) : (
                workspaceOptions.map((opt) => {
                  const parts = opt.split('/');
                  const displayName = parts.length > 2 
                    ? `${parts[parts.length - 2]}/${parts[parts.length - 1]}` 
                    : opt;
                  return (
                    <option key={opt} value={opt} className="bg-[#0c0e17] text-slate-300 text-[10px] font-mono">
                      {displayName}
                    </option>
                  );
                })
              )}
            </select>
          </div>

          <div className="px-3 py-2 border-b border-white/[0.06] text-[10px] font-bold tracking-wider text-slate-400 uppercase flex items-center space-x-1">
            <Folder className="w-3.5 h-3.5 text-cyan-400" />
            <span>Files</span>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
            {files.length === 0 ? (
              <div className="text-[10px] text-slate-600 p-2 italic">No files in directory</div>
            ) : (
              files.map((file) => {
                // Determine clean relative path representation
                const relativePath = file.startsWith(currentWorkspace)
                  ? file.substring(currentWorkspace.length).replace(/^\//, '')
                  : file;
                
                return (
                  <button
                    key={file}
                    onClick={() => handleSelectFile(file)}
                    className={`w-full text-left truncate text-[11px] font-mono px-2 py-1 rounded transition-all cursor-pointer flex items-center space-x-1.5 ${
                      selectedFile === file
                        ? 'bg-cyan-500/10 text-cyan-400 border-l-2 border-cyan-400 pl-1.5'
                        : 'text-slate-400 hover:bg-white/[0.03] hover:text-slate-200'
                    }`}
                    title={file}
                  >
                    <FileText className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="truncate">{relativePath}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Center Panel Code Editor */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#06080d]">
          {/* File Tab Bar */}
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/[0.06] bg-black/15">
            <div className="flex items-center space-x-2">
              {selectedFile ? (
                <div className="flex items-center space-x-2 bg-[#0c0e17] px-3 py-1 rounded-t-lg border-t-2 border-cyan-500 text-[11px] font-mono text-cyan-400">
                  <span>{selectedFile.split('/').pop()}</span>
                </div>
              ) : (
                <span className="text-[11px] font-mono text-slate-500 italic px-2">No active tab</span>
              )}
            </div>
            {selectedFile && (
              <button
                onClick={handleSave}
                disabled={loading}
                className="bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-400 text-[10px] font-bold py-1 px-3 rounded-lg transition-all flex items-center space-x-1.5 cursor-pointer disabled:opacity-40"
              >
                <Save className="w-3.5 h-3.5" />
                <span>SAVE</span>
              </button>
            )}
          </div>

          {/* Editor Body with line numbers */}
          <div className="flex-1 flex overflow-hidden relative">
            {selectedFile ? (
              <>
                {/* Line Numbers Column */}
                <div
                  ref={lineRef}
                  className="w-10 bg-black/15 text-right font-mono text-[12px] text-slate-600 select-none py-4 pr-2 border-r border-white/[0.03] overflow-hidden leading-relaxed"
                >
                  {Array.from({ length: lineCount }).map((_, i) => (
                    <div key={i}>{i + 1}</div>
                  ))}
                </div>

                {/* Textarea Editor */}
                <textarea
                  ref={textareaRef}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  onScroll={handleScroll}
                  placeholder="// Code editor active..."
                  className="flex-1 p-4 font-mono text-[12px] bg-transparent text-[#e8eaf0] focus:outline-none resize-none overflow-y-auto leading-relaxed placeholder:text-slate-600 custom-scrollbar whitespace-pre"
                />
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-slate-500">
                <FileText className="w-10 h-10 mb-2.5 text-slate-600 animate-pulse" />
                <p className="text-[12px] font-medium font-mono text-slate-400">SELECT A FILE FROM EXPLORER TO EDIT</p>
                <p className="text-[10px] text-slate-600 mt-1 max-w-[280px]">Your workspace directory is scanned recursively to show edit-compatible files.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Sidebar AI Chat */}
        <div className="w-[300px] border-l border-white/[0.06] bg-black/20 flex flex-col">
          <div className="px-3 py-2 border-b border-white/[0.06] text-[10px] font-bold tracking-wider text-slate-400 uppercase flex items-center justify-between">
            <span>AI Assist Panel</span>
            <Sparkles className="w-3.5 h-3.5 text-purple-400" />
          </div>

          {/* AI Chat History */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar bg-black/10">
            {chatHistory.map((msg, i) => (
              <div
                key={i}
                className={`flex flex-col space-y-1 p-2.5 rounded-lg border text-[11px] leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-cyan-950/20 border-cyan-500/20 text-[#e8eaf0]'
                    : 'bg-purple-950/15 border-purple-500/15 text-slate-300'
                }`}
              >
                <span className={`text-[8px] font-mono font-bold uppercase tracking-wider ${
                  msg.role === 'user' ? 'text-cyan-400' : 'text-purple-400'
                }`}>
                  {msg.role === 'user' ? 'USER' : 'ASSISTANT'}
                </span>
                <div className="whitespace-pre-wrap font-sans">{msg.text}</div>
              </div>
            ))}
            
            {aiLoading && (
              <div className="flex flex-col space-y-1.5 p-2.5 rounded-lg border bg-purple-950/15 border-purple-500/15 text-slate-300 animate-pulse">
                <span className="text-[8px] font-mono font-bold uppercase tracking-wider text-purple-400 flex items-center space-x-1">
                  <span>AI COMPILED AGENT IS GENERATING SUGGESTIONS</span>
                </span>
                <div className="text-[11px] font-sans italic">Synthesizing file context and computing modifications...</div>
              </div>
            )}
            <div ref={responseEndRef} />
          </div>

          {/* AI Prompt Input Form */}
          <form onSubmit={handleAiRequest} className="p-3 border-t border-white/[0.06] bg-black/20">
            <div className="relative flex items-center">
              <input
                type="text"
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="Ask AI about this file or edits..."
                disabled={aiLoading}
                className="w-full bg-black/45 border border-white/[0.08] focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 rounded-lg pl-3 pr-8 py-2 text-[11px] text-[#e8eaf0] focus:outline-none placeholder:text-slate-600 font-sans"
              />
              <button
                type="submit"
                disabled={aiLoading || !aiPrompt.trim()}
                className="absolute right-1 bg-gradient-to-r from-purple-500 to-[#a855f7] hover:from-purple-400 hover:to-[#b966ff] disabled:opacity-40 border-none text-[#0a0c12] p-1.5 rounded-md cursor-pointer flex items-center justify-center transition-all"
              >
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Footer Status Log */}
      <div className="px-4 py-2 border-t border-white/[0.06] bg-black/35 flex items-center justify-between text-[10px] font-mono text-slate-500">
        <span className="truncate max-w-[450px]">LOG: {status}</span>
        <span className="uppercase text-[9px]">WORKSPACE SYNCED</span>
      </div>
    </div>
  );
}
