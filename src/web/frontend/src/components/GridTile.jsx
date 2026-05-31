import React, { useState } from 'react';

export default function GridTile({ title, type, items, onActionMessage }) {
  const [loadingId, setLoadingId] = useState(null);

  const getBadgeClass = () => {
    switch (type) {
      case 'webpage': return 'text-cyan-400 bg-cyan-950/20 border-cyan-500/20';
      case 'app': return 'text-purple-400 bg-purple-950/20 border-purple-500/20';
      case 'game': return 'text-emerald-400 bg-emerald-950/20 border-emerald-500/20';
      default: return 'text-cyan-400 bg-cyan-950/20 border-cyan-500/20';
    }
  };

  const getButtonClass = () => {
    switch (type) {
      case 'webpage': return 'bg-cyan-500/10 hover:bg-cyan-500/15 border border-cyan-500/25 text-cyan-400';
      case 'app': return 'bg-purple-500/10 hover:bg-purple-500/15 border border-purple-500/25 text-purple-400';
      case 'game': return 'bg-emerald-500/10 hover:bg-emerald-500/15 border border-emerald-500/25 text-emerald-400';
      default: return 'bg-cyan-500/10 hover:bg-cyan-500/15 border border-cyan-500/25 text-cyan-400';
    }
  };

  const handleLaunch = async (item) => {
    setLoadingId({ id: item.id, action: 'launch' });
    try {
      const formData = new FormData();
      formData.append('type', type);
      if (type === 'webpage') {
        formData.append('url', item.url);
      } else {
        formData.append('path', item.path);
      }

      const res = await fetch('/api/launch', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      
      if (res.ok) {
        onActionMessage('LAUNCH', `Executed process: "${item.title}"`);
      } else {
        onActionMessage('ERROR', `Process failed: ${data.error || 'Unknown error'}`);
      }
    } catch (e) {
      onActionMessage('ERROR', `Process failed: ${e.message}`);
    } finally {
      setLoadingId(null);
    }
  };

  const handleInspect = async (item) => {
    setLoadingId({ id: item.id, action: 'inspect' });
    try {
      const formData = new FormData();
      formData.append('metadata', JSON.stringify(item));

      const res = await fetch('/api/ingest', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();

      if (res.ok) {
        onActionMessage('INSPECT', `Telemetry log dispatched: ${item.id}`);
      } else {
        onActionMessage('ERROR', `Audit failure: ${data.error || 'Ingest error'}`);
      }
    } catch (e) {
      onActionMessage('ERROR', `Audit failure: ${e.message}`);
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <div className="flex flex-col border border-white/[0.07] bg-[#0e121e]/85 backdrop-blur-md rounded-xl overflow-hidden shadow-xl">
      {/* Title Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/20 border-b border-white/[0.05] text-[11px] font-semibold tracking-wider text-slate-300">
        <span className="uppercase">{title}</span>
        <span className="text-[9px] font-mono text-slate-500">ENTRIES: {items.length}</span>
      </div>

      {/* Grid Content */}
      <div className="p-3 grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[440px] overflow-y-auto">
        {items.length === 0 ? (
          <div className="col-span-2 flex flex-col items-center justify-center py-10 text-slate-500">
            <span className="text-xs font-medium">NO RECOGNIZED ENTRIES MOUNTED</span>
          </div>
        ) : (
          items.map((item) => (
            <div
              key={item.id}
              className="p-3 rounded-xl border border-white/[0.05] bg-black/15 hover:bg-black/25 transition-all duration-300 flex flex-col justify-between h-[115px] relative overflow-hidden group hover:border-white/[0.12]"
            >
              <div>
                <div className="flex justify-between items-start mb-1">
                  <h3 className="font-semibold text-[13px] text-[#e8eaf0] group-hover:text-cyan-400 transition-colors truncate max-w-[145px]">
                    {item.title}
                  </h3>
                  <span className={`text-[8px] uppercase px-2 py-0.5 rounded-full border font-semibold ${getBadgeClass()}`}>
                    {type === 'game' ? 'utility' : type}
                  </span>
                </div>

                <p className="text-[11px] text-slate-400 leading-snug line-clamp-2">
                  {item.description}
                </p>
              </div>

              {/* Action buttons */}
              <div className="flex space-x-2">
                <button
                  onClick={() => handleLaunch(item)}
                  disabled={loadingId?.id === item.id}
                  className={`flex-1 text-[10px] font-semibold py-1 px-2.5 rounded-lg flex items-center justify-center transition-all duration-200 cursor-pointer ${getButtonClass()}`}
                >
                  <span>{loadingId?.id === item.id && loadingId?.action === 'launch' ? '...' : 'LAUNCH'}</span>
                </button>
                <button
                  onClick={() => handleInspect(item)}
                  disabled={loadingId?.id === item.id}
                  className="bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.08] text-slate-300 text-[10px] py-1 px-2 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
                  title="Inspect"
                >
                  <span>INSPECT</span>
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
