import React, { useState, useRef, useEffect } from 'react';
import { Send, Terminal, Shield } from 'lucide-react';

const playSoftClick = () => {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    
    osc.type = 'sine';
    // Soft high pitch keyclick sound
    osc.frequency.value = 1600; 
    gain.gain.setValueAtTime(0.003, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.00001, ctx.currentTime + 0.015);
    
    osc.connect(gain);
    gain.connect(ctx.destination);
    
    osc.start();
    osc.stop(ctx.currentTime + 0.015);
  } catch (e) {
    // browser auto-play policy may block audio until user interaction
  }
};

export default function ChatTile() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([
    { sender: 'system', text: 'SYSTEM COMPILER INITIALIZATION SEQUENCE: PASSED' },
    { sender: 'agent', text: 'Greetings, user. I am online and tracking system tasks. How can I assist you with operations today?' }
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const [device, setDevice] = useState('desktop');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { sender: 'user', text: userMessage }]);
    setIsTyping(true);

    try {
      const formData = new FormData();
      formData.append('message', userMessage);
      formData.append('device', device);

      const response = await fetch('/api/chat', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Communication link error');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let agentText = '';

      setMessages(prev => [...prev, { sender: 'agent', text: '' }]);

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
              
              if (parsed.type === 'response' || parsed.type === 'narration') {
                const incomingText = parsed.text;
                agentText += incomingText;
                
                setMessages(prev => {
                  const updated = [...prev];
                  if (updated.length > 0) {
                    updated[updated.length - 1] = { sender: 'agent', text: agentText };
                  }
                  return updated;
                });
                
                playSoftClick();
              }
            } catch (err) {
              // ignore malformed JSON chunk
            }
          }
        }
      }
    } catch (error) {
      setMessages(prev => [...prev, { sender: 'system', text: `ERROR: ${error.message}` }]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="flex flex-col h-[500px] rounded-xl border border-white/[0.07] bg-[#0e121e]/85 backdrop-blur-md shadow-2xl overflow-hidden relative">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/20 border-b border-white/[0.05] text-xs font-semibold tracking-wider text-slate-300">
        <div className="flex items-center space-x-2">
          <Terminal className="w-4 h-4 text-cyan-400" />
          <span>CORE OPERATIONAL TERMINAL</span>
        </div>
        <div className="flex items-center space-x-3 text-[10px]">
          <div className="flex items-center space-x-1">
            <span className="text-slate-400 uppercase tracking-wider font-mono">DEVICE:</span>
            <select
              value={device}
              onChange={(e) => setDevice(e.target.value)}
              className="bg-black/50 border border-white/[0.08] focus:border-cyan-500/50 rounded px-2 py-0.5 text-[10px] text-cyan-400 font-mono focus:outline-none cursor-pointer"
            >
              <option value="desktop" className="bg-[#0e121e]">DESKTOP</option>
              <option value="laptop" className="bg-[#0e121e]">LAPTOP</option>
              <option value="phone" className="bg-[#0e121e]">PHONE</option>
            </select>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
            <span className="text-cyan-400 font-mono">LINK_STABLE</span>
          </div>
        </div>
      </div>

      {/* Message logs */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm leading-relaxed">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
            <div className={`text-[10px] uppercase font-mono tracking-wider mb-1 ${
              msg.sender === 'user' ? 'text-cyan-400/80' : msg.sender === 'system' ? 'text-red-400' : 'text-purple-400/80'
            }`}>
              {msg.sender}
            </div>
            
            {msg.sender === 'agent' ? (
              <div className="border-l-2 border-purple-500/35 pl-3 py-0.5 text-[#e8eaf0] text-[0.9375rem] max-w-full">
                {msg.text}
                {idx === messages.length - 1 && isTyping && (
                  <span className="typing-cursor" />
                )}
              </div>
            ) : msg.sender === 'system' ? (
              <div className="text-red-400 font-mono text-[12px] bg-red-950/20 border border-red-500/10 rounded px-2 py-1 max-w-[90%]">
                {msg.text}
              </div>
            ) : (
              <div className="rounded-xl px-3 py-1.5 bg-[#161c2e] border border-cyan-500/10 text-[#e8eaf0] max-w-[85%] shadow-md">
                {msg.text}
              </div>
            )}
          </div>
        ))}
        {isTyping && messages[messages.length - 1]?.sender !== 'agent' && (
          <div className="flex flex-col items-start">
            <div className="text-[10px] font-mono text-purple-400/80 uppercase tracking-wider mb-1">agent</div>
            <div className="border-l-2 border-purple-500/35 pl-3 py-0.5 text-[#e8eaf0]">
              <span className="typing-cursor" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input row */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-white/[0.05] bg-black/10 flex items-center space-x-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Send prompt or message to agent..."
          disabled={isTyping}
          className="flex-1 bg-black/30 border border-white/[0.08] rounded-xl px-4 py-2.5 text-[15px] text-[#e8eaf0] focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 placeholder:text-slate-500"
        />
        <button
          type="submit"
          disabled={isTyping}
          className="bg-gradient-to-r from-cyan-400 to-[#0090cc] hover:from-cyan-300 hover:to-[#00aade] text-slate-900 font-bold p-2.5 rounded-full flex items-center justify-center transition-all duration-300 shadow-[0_0_12px_rgba(0,212,255,0.25)] disabled:opacity-30 disabled:shadow-none"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
