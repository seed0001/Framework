import React, { useState, useEffect } from 'react';
import { Save, Volume2, ShieldAlert, Check, Loader2, Key, User, Trash2 } from 'lucide-react';

export default function SettingsTile() {
  const [voices, setVoices] = useState([]);
  const [selectedVoice, setSelectedVoice] = useState('');
  const [discordToken, setDiscordToken] = useState('');
  const [discordOwnerId, setDiscordOwnerId] = useState('');
  const [isTokenSet, setIsTokenSet] = useState(false);
  const [botStatus, setBotStatus] = useState('Stopped');
  
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [statusMsg, setStatusMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setFetching(true);
    try {
      // 1. Fetch available voices
      const voicesRes = await fetch('/api/voices');
      if (voicesRes.ok) {
        const data = await voicesRes.json();
        setVoices(data.voices || []);
      }

      // 2. Fetch current settings
      const settingsRes = await fetch('/api/settings');
      if (settingsRes.ok) {
        const data = await settingsRes.json();
        setSelectedVoice(data.tts_voice || '');
        setIsTokenSet(data.discord_token_set || false);
        setDiscordOwnerId(data.discord_owner_id || '');
        setBotStatus(data.discord_status || 'Stopped');
      }
    } catch (e) {
      setErrorMsg('Failed to load system settings');
    } finally {
      setFetching(false);
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatusMsg('');
    setErrorMsg('');

    try {
      const formData = new FormData();
      if (selectedVoice) formData.append('tts_voice', selectedVoice);
      if (discordToken.trim()) formData.append('discord_token', discordToken.trim());
      if (discordOwnerId.trim()) formData.append('discord_owner_id', discordOwnerId.trim());

      const res = await fetch('/api/settings', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        setStatusMsg('System settings persisted successfully!');
        setDiscordToken(''); // clear token input
        fetchSettings(); // reload updated status
      } else {
        const err = await res.json();
        setErrorMsg(err.error || 'Failed to save settings');
      }
    } catch (err) {
      setErrorMsg(`Save Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveDiscord = async () => {
    if (!window.confirm('Are you sure you want to stop the Discord bot and remove the token?')) return;
    setLoading(true);
    setStatusMsg('');
    setErrorMsg('');

    try {
      const formData = new FormData();
      formData.append('discord_token', '__REMOVE__');

      const res = await fetch('/api/settings', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        setStatusMsg('Discord bot stopped and token configuration removed.');
        setDiscordToken('');
        setDiscordOwnerId('');
        setIsTokenSet(false);
        setBotStatus('Stopped');
      } else {
        const err = await res.json();
        setErrorMsg(err.error || 'Failed to remove bot configuration');
      }
    } catch (err) {
      setErrorMsg(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (fetching) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-500">
        <Loader2 className="w-10 h-10 animate-spin text-cyan-400 mb-4" />
        <span className="text-xs font-mono tracking-widest uppercase">Syncing Registry Settings...</span>
      </div>
    );
  }

  return (
    <div className="glass-panel p-6 rounded-xl border border-white/[0.08] bg-[#0c0f1d]/90 backdrop-blur-md shadow-2xl flex flex-col space-y-5 max-w-lg mx-auto animate-fade-in font-sans">
      <div className="text-center pb-2 border-b border-white/[0.06]">
        <h2 className="text-[14px] font-bold text-cyan-400 uppercase tracking-widest">SYSTEM SETTINGS MANAGER</h2>
        <p className="text-[9px] font-mono text-slate-400 uppercase mt-1">Configure voices and agent access credentials</p>
      </div>

      {statusMsg && (
        <div className="p-3 border border-emerald-500/25 bg-emerald-950/20 rounded text-[11px] text-emerald-400 font-medium flex items-center space-x-1.5 animate-fade-in">
          <Check className="w-4 h-4 flex-shrink-0" />
          <span>{statusMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="p-3 border border-red-500/25 bg-red-950/20 rounded text-[11px] text-red-400 font-medium flex items-center space-x-1.5 animate-pulse">
          <ShieldAlert className="w-4 h-4 flex-shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSaveSettings} className="space-y-4">
        {/* TTS Voice Field */}
        <div className="flex flex-col space-y-1.5">
          <label className="text-[9px] font-mono text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
            <Volume2 className="w-3.5 h-3.5 text-cyan-400" />
            <span>TTS NARRATION VOICE</span>
          </label>
          <select
            value={selectedVoice}
            onChange={(e) => setSelectedVoice(e.target.value)}
            className="w-full bg-black/45 border border-white/[0.08] focus:border-cyan-500/50 rounded-lg px-3 py-2 text-[12px] text-slate-200 focus:outline-none cursor-pointer"
          >
            <option value="" className="bg-[#0c0e17] text-slate-500">Select shortname voice reference...</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id} className="bg-[#0c0e17] text-slate-300">
                {v.name} ({v.locale} - {v.gender})
              </option>
            ))}
          </select>
        </div>

        {/* Divider */}
        <div className="h-px bg-white/[0.06] my-4" />

        {/* Discord Bot Configuration Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-purple-400 uppercase tracking-widest">DISCORD INTEGRATION GATE</span>
            <span className={`text-[8px] font-mono font-bold uppercase tracking-wider border px-2 py-0.5 rounded-full ${
              botStatus === 'Running' ? 'text-emerald-400 bg-emerald-950/20 border-emerald-500/30 animate-pulse' : 'text-slate-500 bg-black/35 border-white/[0.08]'
            }`}>
              STATUS: {botStatus}
            </span>
          </div>

          {/* Discord Bot Token */}
          <div className="flex flex-col space-y-1.5">
            <label className="text-[9px] font-mono text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
              <Key className="w-3.5 h-3.5 text-purple-400" />
              <span>DISCORD BOT TOKEN</span>
            </label>
            <div className="relative flex items-center">
              <input
                type="password"
                value={discordToken}
                onChange={(e) => setDiscordToken(e.target.value)}
                placeholder={isTokenSet ? "••••••••••••••••••••••••••••••••" : "Paste bot auth token..."}
                className="w-full bg-black/35 border border-white/[0.08] focus:border-purple-500/50 rounded-lg px-3 py-2 text-[12px] text-white focus:outline-none font-mono"
              />
              {isTokenSet && (
                <button
                  type="button"
                  onClick={handleRemoveDiscord}
                  className="absolute right-2 text-[9px] font-mono bg-red-500/10 hover:bg-red-500/25 border border-red-500/30 text-red-400 px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center space-x-1"
                  title="Stop bot and delete configuration"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>REMOVE</span>
                </button>
              )}
            </div>
            <p className="text-[8px] text-slate-500 font-mono">Token is masked for secure delivery. Re-paste token to overwrite.</p>
          </div>

          {/* Discord Owner ID */}
          <div className="flex flex-col space-y-1.5">
            <label className="text-[9px] font-mono text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
              <User className="w-3.5 h-3.5 text-purple-400" />
              <span>DISCORD OWNER USER ID</span>
            </label>
            <input
              type="text"
              value={discordOwnerId}
              onChange={(e) => setDiscordOwnerId(e.target.value)}
              placeholder="e.g. 182736459281726354"
              className="bg-black/35 border border-white/[0.08] focus:border-purple-500/50 rounded-lg px-3 py-2 text-[12px] text-white focus:outline-none font-mono"
            />
            <p className="text-[8px] text-slate-500 font-mono">User ID of the system owner/creator for DMs and alerts.</p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-2 pt-3 border-t border-white/[0.06] justify-end">
          <button
            type="submit"
            disabled={loading}
            className="bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 text-black font-semibold text-[11px] py-2 px-5 rounded-lg flex items-center space-x-1.5 cursor-pointer transition-colors"
          >
            {loading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>SAVING...</span>
              </>
            ) : (
              <>
                <Save className="w-3.5 h-3.5" />
                <span>SAVE SETTINGS</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
