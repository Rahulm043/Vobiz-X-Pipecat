import React from 'react';
import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom';
import {
  LayoutDashboard, Phone, Megaphone, Plus, Settings, Activity, LogOut, User,
} from 'lucide-react';
import Dashboard from './pages/Dashboard.jsx';
import SingleCall from './pages/SingleCall.jsx';
import CampaignList from './pages/CampaignList.jsx';
import NewCampaign from './pages/NewCampaign.jsx';
import CampaignDetail from './pages/CampaignDetail.jsx';
import LoginPage from './pages/LoginPage.jsx';
import { AuthProvider, useAuth } from './components/AuthProvider.jsx';
import './index.css';

const NAV_ITEMS = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/call', icon: Phone, label: 'Single Call' },
  { path: '/campaigns', icon: Megaphone, label: 'Campaigns', end: true },
  { path: '/campaigns/new', icon: Plus, label: 'New Campaign' },
];

function ConfirmationModal({ isOpen, onClose, onConfirm, title, message }) {
  if (!isOpen) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <p>{message}</p>
        </div>
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" style={{ background: 'var(--error)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }} onClick={onConfirm}>
            <LogOut size={16} />
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}

function Sidebar({ onLogoutRequest }) {
  const location = useLocation();
  const { user } = useAuth();
  const [showMenu, setShowMenu] = React.useState(false);
  
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img src="/logo2.png" alt="Provaani" className="brand-icon" />
        <div className="brand-text-container">
          <h2 className="brand-title">Provaani</h2>
          <span className="brand-sub">Voice AI Call Manager</span>
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
        <div 
            className="user-profile interactive logout-trigger" 
            onClick={onLogoutRequest}
            title="Sign Out"
        >
            <div className="logout-content">
                <LogOut size={18} />
                <span>Logout</span>
            </div>
        </div>
      </div>
    </aside>
  );
}

function MobileHeader() {
  return (
    <header className="mobile-header">
      <div className="mobile-brand">
        <img src="/logo2.png" alt="Provaani" className="mobile-logo" />
        <div className="mobile-brand-text">
          <h2 className="mobile-title">Provaani</h2>
          <span className="mobile-sub">Voice AI Call Manager</span>
        </div>
      </div>
    </header>
  );
}

function AppContent() {
  const { session, loading, signOut } = useAuth();
  const [showLogoutConfirm, setShowLogoutConfirm] = React.useState(false);

  if (loading) {
    return (
        <div className="flex-center" style={{ height: '100vh', flexDirection: 'column', gap: '1rem' }}>
            <div className="spinner-lg" />
            <span style={{ color: 'var(--text-dim)' }}>Loading session...</span>
        </div>
    );
  }

  if (!session) {
    return <LoginPage />;
  }

  return (
    <div className="app-layout">
      <MobileHeader />
      <Sidebar onLogoutRequest={() => setShowLogoutConfirm(true)} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/call" element={<SingleCall />} />
          <Route path="/single-call" element={<Navigate to="/call" replace />} />
          <Route path="/campaigns" element={<CampaignList />} />
          <Route path="/campaigns/new" element={<NewCampaign />} />
          <Route path="/campaigns/:id" element={<CampaignDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <ConfirmationModal 
        isOpen={showLogoutConfirm}
        onClose={() => setShowLogoutConfirm(false)}
        onConfirm={signOut}
        title="Sign Out?"
        message="Are you sure you want to log out of Provaani?"
      />
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
