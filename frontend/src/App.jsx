import React from 'react';
import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom';
import {
  LayoutDashboard, Phone, Megaphone, Plus, Settings, Activity,
} from 'lucide-react';
import Dashboard from './pages/Dashboard.jsx';
import SingleCall from './pages/SingleCall.jsx';
import CampaignList from './pages/CampaignList.jsx';
import NewCampaign from './pages/NewCampaign.jsx';
import CampaignDetail from './pages/CampaignDetail.jsx';
import './index.css';

const NAV_ITEMS = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/call', icon: Phone, label: 'Single Call' },
  { path: '/campaigns', icon: Megaphone, label: 'Campaigns', end: true },
  { path: '/campaigns/new', icon: Plus, label: 'New Campaign' },
];

function Sidebar() {
  const location = useLocation();
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Activity size={24} className="brand-icon" />
        <div>
          <h2 className="brand-title">BotLive</h2>
          <span className="brand-sub">Call Manager</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ path, icon: Icon, label, end }) => (
          <NavLink
            key={path}
            to={path}
            end={end || path === '/'}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="sidebar-agent-badge">
          <div className="agent-dot online" />
          <span>bot_live.py</span>
        </div>
      </div>
    </aside>
  );
}

function App() {
  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/call" element={<SingleCall />} />
          <Route path="/single-call" element={<Navigate to="/call" replace />} />
          <Route path="/campaigns" element={<CampaignList />} />
          <Route path="/campaigns/new" element={<NewCampaign />} />
          <Route path="/campaigns/:id" element={<CampaignDetail />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
