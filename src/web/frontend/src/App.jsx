import React, { useState, useEffect } from 'react';
import { HashRouter as Router, Routes, Route, Link } from 'react-router-dom';
import StarfieldBackground from './components/StarfieldBackground';
import GridTile from './components/GridTile';
import WorkshopTile from './components/WorkshopTile';
import { Layout, ArrowLeft, Shield } from 'lucide-react';

function TelemetryHeader({ timeString, cpuLoad, memLoad }) {
  return (
    <header className="relative z-10 w-full mb-6 border border-white/[0.06] bg-[#111520]/80 rounded-xl p-4 flex flex-col md:flex-row justify-between items-center shadow-md backdrop-blur-md">
      <div className="flex items-center space-x-3 mb-4 md:mb-0">
        <div className="p-2 bg-white/[0.04] border border-white/[0.08] rounded-lg">
          <Layout className="w-4 h-4 text-cyan-400" />
        </div>
        <div>
          <h1 className="font-semibold text-sm tracking-wide text-white leading-none">
            WORKSPACE DIRECTORY <span className="text-cyan-500">//</span> HUB
          </h1>
          <p className="text-[9px] font-mono text-slate-400 uppercase mt-1 tracking-wider">
            System Control Panel & Integration Directory
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 w-full md:w-auto font-mono text-[9px] tracking-wider">
        <div className="border border-white/[0.06] bg-black/15 px-2.5 py-1.5 rounded-lg flex items-center justify-between space-x-2">
          <span className="text-slate-400">CPU:</span>
          <span className="text-white font-bold">{cpuLoad}%</span>
        </div>
        <div className="border border-white/[0.06] bg-black/15 px-2.5 py-1.5 rounded-lg flex items-center justify-between space-x-2">
          <span className="text-slate-400">MEM:</span>
          <span className="text-white font-bold">{memLoad}%</span>
        </div>
        <div className="border border-white/[0.06] bg-black/15 px-2.5 py-1.5 rounded-lg flex items-center justify-between space-x-2">
          <span className="text-slate-400">SECURITY:</span>
          <div className="flex items-center text-emerald-400 font-bold space-x-1">
            <Shield className="w-3 h-3" />
            <span>ACTIVE</span>
          </div>
        </div>
        <div className="border border-white/[0.06] bg-black/15 px-2.5 py-1.5 rounded-lg flex items-center justify-between space-x-2">
          <span className="text-slate-400">TIME:</span>
          <span className="text-cyan-400 font-bold">{timeString}</span>
        </div>
      </div>
    </header>
  );
}

function HubHome() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 relative z-10 max-w-3xl mx-auto w-full">
      {/* Chat Tile */}
      <a
        href="/chat"
        className="glass-panel glass-panel-hover p-4 rounded-xl flex flex-col justify-between h-[130px] group cursor-pointer"
      >
        <div className="flex justify-between items-center">
          <h2 className="text-[14px] font-semibold text-white group-hover:text-cyan-400 transition-colors">
            AI CHAT ASSISTANT
          </h2>
          <span className="text-[9px] font-mono text-purple-400 bg-purple-950/20 border border-purple-500/25 px-2 py-0.5 rounded-full font-semibold">
            AGENT_PORTAL
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-normal">
          Launch communications stream to interface with the core lifeform agent.
        </p>
      </a>

      {/* Apps Tile */}
      <Link
        to="/apps"
        className="glass-panel glass-panel-hover p-4 rounded-xl flex flex-col justify-between h-[130px] group cursor-pointer"
      >
        <div className="flex justify-between items-center">
          <h2 className="text-[14px] font-semibold text-white group-hover:text-cyan-400 transition-colors">
            SYSTEM UTILITIES
          </h2>
          <span className="text-[9px] font-mono text-cyan-400 bg-cyan-950/20 border border-cyan-500/25 px-2 py-0.5 rounded-full font-semibold">
            LOCAL_TOOLS
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-normal">
          Execute local administration tools, task managers, and developer command shells.
        </p>
      </Link>

      {/* Games Tile */}
      <Link
        to="/games"
        className="glass-panel glass-panel-hover p-4 rounded-xl flex flex-col justify-between h-[130px] group cursor-pointer"
      >
        <div className="flex justify-between items-center">
          <h2 className="text-[14px] font-semibold text-white group-hover:text-cyan-400 transition-colors">
            CURATED GAMES
          </h2>
          <span className="text-[9px] font-mono text-emerald-400 bg-emerald-950/20 border border-emerald-500/25 px-2 py-0.5 rounded-full font-semibold">
            GAMES_DB
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-normal">
          Launch and manage editor programs and configurations on the local environment.
        </p>
      </Link>

      {/* Workshop Tile */}
      <Link
        to="/workshop"
        className="glass-panel glass-panel-hover p-4 rounded-xl flex flex-col justify-between h-[130px] group cursor-pointer"
      >
        <div className="flex justify-between items-center">
          <h2 className="text-[14px] font-semibold text-white group-hover:text-cyan-400 transition-colors">
            DEVELOPMENT WORKSHOP
          </h2>
          <span className="text-[9px] font-mono text-orange-400 bg-orange-950/20 border border-orange-500/25 px-2 py-0.5 rounded-full font-semibold">
            STAGING
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-normal">
          Access developer integration sandboxes and testing environment models.
        </p>
      </Link>
    </div>
  );
}

function PageWrapper({ children, title }) {
  return (
    <div className="relative z-10 max-w-3xl mx-auto w-full flex flex-col space-y-4">
      <div className="flex items-center justify-between border-b border-white/[0.05] pb-3">
        <Link
          to="/"
          className="flex items-center space-x-2 text-[11px] font-semibold text-slate-400 hover:text-white transition-colors cursor-pointer bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.05] px-2.5 py-1.5 rounded-lg"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>RETURN TO DIRECTORY</span>
        </Link>
        <span className="text-[10px] font-mono text-cyan-400/80 uppercase tracking-widest">{title}</span>
      </div>
      <div className="animate-fade-in">
        {children}
      </div>
    </div>
  );
}

export default function App() {
  const [tiles, setTiles] = useState({ apps: [], games: [] });
  const [timeString, setTimeString] = useState('');
  const [systemAlerts, setSystemAlerts] = useState([
    { id: 1, text: 'DIRECTORY CONTROLLER CORE LOADED', type: 'info' }
  ]);

  const [cpuLoad, setCpuLoad] = useState(4.2);
  const [memLoad, setMemLoad] = useState(32.4);

  useEffect(() => {
    const updateTime = () => {
      const d = new Date();
      setTimeString(d.toLocaleTimeString());
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const telemetryInterval = setInterval(() => {
      setCpuLoad(prev => Math.max(1.0, Math.min(99.0, +(prev + (Math.random() - 0.5) * 1.5).toFixed(1))));
      setMemLoad(prev => Math.max(10.0, Math.min(99.0, +(prev + (Math.random() - 0.5) * 0.5).toFixed(1))));
    }, 3000);
    return () => clearInterval(telemetryInterval);
  }, []);

  useEffect(() => {
    const fetchTiles = async () => {
      try {
        const res = await fetch('/api/tiles');
        if (res.ok) {
          const data = await res.json();
          setTiles(data);
        }
      } catch (err) {
        addSystemLog('ERROR', 'COULD NOT RETRIEVE TILES CONFIG');
      }
    };
    fetchTiles();
  }, []);

  const addSystemLog = (sender, text) => {
    setSystemAlerts(prev => [
      { id: Date.now(), text: `[${sender}] ${text}` },
      ...prev.slice(0, 4)
    ]);
  };

  return (
    <Router>
      <div className="relative min-h-screen text-[#e8eaf0] flex flex-col p-4 md:p-6 bg-[#0a0c12]">
        <StarfieldBackground />

        <TelemetryHeader timeString={timeString} cpuLoad={cpuLoad} memLoad={memLoad} />

        <div className="flex-1 flex flex-col justify-start">
          <Routes>
            <Route path="/" element={<HubHome />} />
            <Route
              path="/apps"
              element={
                <PageWrapper title="Local Utilities">
                  <GridTile
                    title="Administrative Tools"
                    type="app"
                    items={tiles.apps}
                    onActionMessage={addSystemLog}
                  />
                </PageWrapper>
              }
            />
            <Route
              path="/games"
              element={
                <PageWrapper title="Curated Games">
                  <GridTile
                    title="Games Directory"
                    type="game"
                    items={tiles.games}
                    onActionMessage={addSystemLog}
                  />
                </PageWrapper>
              }
            />
            <Route
              path="/workshop"
              element={
                <div className="relative z-10 max-w-6xl mx-auto w-full flex flex-col space-y-4 px-4">
                  <div className="flex items-center justify-between border-b border-white/[0.05] pb-3">
                    <Link
                      to="/"
                      className="flex items-center space-x-2 text-[11px] font-semibold text-slate-400 hover:text-white transition-colors cursor-pointer bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.05] px-2.5 py-1.5 rounded-lg"
                    >
                      <ArrowLeft className="w-3.5 h-3.5" />
                      <span>RETURN TO DIRECTORY</span>
                    </Link>
                    <span className="text-[10px] font-mono text-cyan-400/80 uppercase tracking-widest font-bold">DEVELOPMENT WORKSHOP</span>
                  </div>
                  <div className="animate-fade-in">
                    <WorkshopTile />
                  </div>
                </div>
              }
            />
          </Routes>
        </div>

        <footer className="relative z-10 w-full mt-8 border-t border-white/[0.05] pt-4 flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="w-full md:w-[450px] border border-white/[0.06] bg-black/15 rounded-lg p-2.5 font-mono text-[9px] text-slate-400 h-[65px] overflow-y-auto">
            {systemAlerts.map((alert) => (
              <div key={alert.id} className="truncate">
                &gt; {alert.text}
              </div>
            ))}
          </div>
          <div className="flex flex-col items-end text-[10px] font-mono text-slate-500 tracking-wider">
            <span>SECURE SYSTEM MODULES: ACTIVE</span>
            <span>HUB ACCESS CONTROL &copy; 2026</span>
          </div>
        </footer>
      </div>
    </Router>
  );
}
