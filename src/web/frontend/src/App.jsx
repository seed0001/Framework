import React, { useState, useEffect } from 'react';
import { HashRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import StarfieldBackground from './components/StarfieldBackground';
import GridTile from './components/GridTile';
import WorkshopTile from './components/WorkshopTile';
import SettingsTile from './components/SettingsTile';
import HowIWorkTile from './components/HowIWorkTile';
import { LogOut } from 'lucide-react';

function PageWrapper({ children }) {
  return (
    <div className="relative z-10 max-w-3xl mx-auto w-full flex flex-col">
      <div className="animate-fade-in">
        {children}
      </div>
    </div>
  );
}

function Login({ onLoginSuccess }) {
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Username and password are required');
      return;
    }
    if (isRegisterMode && password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setError('');
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('username', username.trim());
      formData.append('password', password);

      const endpoint = isRegisterMode ? '/api/register' : '/api/login';
      const res = await fetch(endpoint, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        onLoginSuccess(data);
      } else {
        setError(data.error || 'Authentication failed');
      }
    } catch (err) {
      setError('Connection failure. Try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative z-10 max-w-sm w-full mx-auto animate-fade-in">
      <form
        onSubmit={handleSubmit}
        className="glass-panel p-6 rounded-xl border border-white/[0.08] bg-[#0c0f1d]/90 backdrop-blur-md shadow-2xl flex flex-col space-y-4"
      >
        <div className="text-center pb-2 border-b border-white/[0.06] mb-2">
          <h2 className="text-[14px] font-bold text-cyan-400 uppercase tracking-widest">
            {isRegisterMode ? 'CREATE NEW ACCOUNT' : 'AUTHENTICATION REQUIRED'}
          </h2>
          <p className="text-[9px] font-mono text-slate-400 uppercase mt-1">
            {isRegisterMode ? 'User Registration Gate' : 'Access Control Gate'}
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex border border-white/[0.06] bg-black/20 rounded-lg p-0.5 w-full text-[10px] font-mono mb-2">
          <button
            type="button"
            onClick={() => {
              setIsRegisterMode(false);
              setError('');
            }}
            className={`flex-1 py-1.5 rounded-md text-center transition-colors cursor-pointer ${
              !isRegisterMode
                ? 'bg-cyan-500/10 border border-cyan-500/25 text-cyan-400 font-bold'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            SIGN IN
          </button>
          <button
            type="button"
            onClick={() => {
              setIsRegisterMode(true);
              setError('');
            }}
            className={`flex-1 py-1.5 rounded-md text-center transition-colors cursor-pointer ${
              isRegisterMode
                ? 'bg-cyan-500/10 border border-cyan-500/25 text-cyan-400 font-bold'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            REGISTER
          </button>
        </div>

        {error && (
          <div className="p-2.5 border border-red-500/25 bg-red-950/20 rounded text-[10px] text-red-400 font-mono text-center">
            {error}
          </div>
        )}

        <div className="flex flex-col space-y-1.5">
          <label className="text-[9px] font-mono text-slate-400 uppercase tracking-wider">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="bg-black/35 border border-white/[0.08] focus:border-cyan-500/50 rounded-lg px-3 py-2 text-[12px] text-white focus:outline-none placeholder:text-slate-600"
            placeholder="Identity handle..."
          />
        </div>

        <div className="flex flex-col space-y-1.5">
          <label className="text-[9px] font-mono text-slate-400 uppercase tracking-wider">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="bg-black/35 border border-white/[0.08] focus:border-cyan-500/50 rounded-lg px-3 py-2 text-[12px] text-white focus:outline-none placeholder:text-slate-600"
            placeholder="••••••••"
          />
        </div>

        {isRegisterMode && (
          <div className="flex flex-col space-y-1.5">
            <label className="text-[9px] font-mono text-slate-400 uppercase tracking-wider">Confirm Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="bg-black/35 border border-white/[0.08] focus:border-cyan-500/50 rounded-lg px-3 py-2 text-[12px] text-white focus:outline-none placeholder:text-slate-600"
              placeholder="••••••••"
            />
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 text-black font-semibold text-[11px] rounded-lg tracking-wider transition-colors cursor-pointer mt-2"
        >
          {loading ? 'VALIDATING...' : isRegisterMode ? 'CREATE ACCOUNT' : 'ENTER SYSTEM'}
        </button>
      </form>
    </div>
  );
}

function AppContent({
  tiles,
  currentUser,
  addSystemLog,
  handleUpdateTiles,
  onLoginSuccess,
  handleLogout
}) {
  if (!currentUser) {
    return (
      <div className="relative min-h-screen text-[#e8eaf0] flex flex-col p-4 bg-[#0a0c12] justify-center items-center">
        <StarfieldBackground />
        <Login onLoginSuccess={onLoginSuccess} />
      </div>
    );
  }

  const location = useLocation();
  const isWorkshop = location.pathname === '/workshop';
  const isHowIWork = location.pathname === '/howiwork';

  return (
    <div className="relative min-h-screen text-[#e8eaf0] flex flex-col p-4 md:p-6 bg-[#0a0c12] justify-center items-center">
      <StarfieldBackground />

      {/* Floating Logout Button */}
      <button
        onClick={handleLogout}
        className="absolute top-4 right-4 text-[9px] font-mono border border-white/[0.08] hover:border-red-500/40 hover:text-red-400 bg-white/[0.01] hover:bg-red-950/10 px-2.5 py-1.5 rounded-lg transition-all cursor-pointer z-30 flex items-center space-x-1 opacity-20 hover:opacity-100"
        title="Logout"
      >
        <LogOut className="w-3.5 h-3.5" />
        <span>LOGOUT</span>
      </button>

      <div className={`w-full flex-1 flex flex-col justify-center py-6 transition-all duration-300 ${isWorkshop ? 'max-w-[1400px] px-2 md:px-4' : isHowIWork ? 'max-w-5xl px-2 md:px-4' : 'max-w-3xl px-4'}`}>
        <Routes>
          <Route
            path="/"
            element={
              <div className="w-full">
                <GridTile
                  title="System Registry"
                  type="app"
                  items={tiles.apps || []}
                  allTiles={tiles}
                  onUpdateTiles={handleUpdateTiles}
                  onActionMessage={addSystemLog}
                />
              </div>
            }
          />
          <Route
            path="/workshop"
            element={
              <div className="relative z-10 max-w-6xl mx-auto w-full flex flex-col space-y-4 px-4">
                <div className="animate-fade-in">
                  <WorkshopTile />
                </div>
              </div>
            }
          />
          <Route
            path="/settings"
            element={
              <div className="relative z-10 max-w-xl mx-auto w-full flex flex-col space-y-4 px-4">
                <div className="animate-fade-in">
                  <SettingsTile />
                </div>
              </div>
            }
          />
          <Route
            path="/howiwork"
            element={
              <div className="animate-fade-in w-full">
                <HowIWorkTile />
              </div>
            }
          />
        </Routes>
      </div>
    </div>
  );
}

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [tiles, setTiles] = useState({ apps: [], games: [] });
  const [systemAlerts, setSystemAlerts] = useState([
    { id: 1, text: 'DIRECTORY CONTROLLER CORE LOADED', type: 'info' }
  ]);

  // Check auth session on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch('/api/me');
        if (res.ok) {
          const user = await res.json();
          setCurrentUser(user);
        } else {
          setCurrentUser(null);
        }
      } catch (err) {
        setCurrentUser(null);
      }
    };
    checkAuth();
  }, []);

  // Fetch user tiles once authenticated
  useEffect(() => {
    if (!currentUser) {
      setTiles({ apps: [], games: [] });
      return;
    }

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
  }, [currentUser]);

  const handleUpdateTiles = async (updatedTiles) => {
    setTiles(updatedTiles);
    try {
      const res = await fetch('/api/tiles', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updatedTiles),
      });
      if (res.ok) {
        addSystemLog('SYSTEM', 'TILES CONFIGURATION PERSISTED');
      } else {
        addSystemLog('ERROR', 'FAILED TO SAVE TILES CONFIG');
      }
    } catch (err) {
      addSystemLog('ERROR', `Save error: ${err.message}`);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/logout', { method: 'POST' });
      setCurrentUser(null);
      addSystemLog('SYSTEM', 'USER LOGGED OUT');
    } catch (err) {
      addSystemLog('ERROR', 'LOGOUT FAILED');
    }
  };

  const addSystemLog = (sender, text) => {
    setSystemAlerts(prev => [
      { id: Date.now(), text: `[${sender}] ${text}` },
      ...prev.slice(0, 4)
    ]);
  };

  const onLoginSuccess = (user) => {
    setCurrentUser(user);
    addSystemLog('AUTH', `USER '${user.username}' CONNECTED`);
  };

  return (
    <Router>
      <AppContent
        tiles={tiles}
        currentUser={currentUser}
        addSystemLog={addSystemLog}
        handleUpdateTiles={handleUpdateTiles}
        onLoginSuccess={onLoginSuccess}
        handleLogout={handleLogout}
      />
    </Router>
  );
}
