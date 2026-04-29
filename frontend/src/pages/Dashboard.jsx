import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Phone, Clock, CheckCircle, XCircle, Activity, PhoneCall,
    BarChart3, ArrowUpRight, RefreshCw, Eye, Megaphone,
} from 'lucide-react';
import CallInspector from '../components/CallInspector.jsx';

const API = '';

function formatDuration(seconds) {
    if (!seconds) return '0s';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const RANGE_OPTIONS = [
    { label: 'Today', value: 'today' },
    { label: '7D', value: '7d' },
    { label: '30D', value: '30d' },
    { label: '90D', value: '90d' },
    { label: 'All', value: 'all' },
];

export default function Dashboard() {
    const navigate = useNavigate();
    const [agentStatus, setAgentStatus] = useState({ status: 'idle' });
    const [stats, setStats] = useState({});
    const [calls, setCalls] = useState([]);
    const [inspectorCallId, setInspectorCallId] = useState(null);
    const [timeRange, setTimeRange] = useState('today');

    const getDatesForRange = useCallback((range) => {
        const end = new Date();
        const start = new Date();
        
        if (range === 'today') {
            return { 
                start: new Date(new Date().setHours(0,0,0,0)).toISOString(),
                end: end.toISOString()
            };
        }
        if (range === '7d') start.setDate(end.getDate() - 7);
        else if (range === '30d') start.setDate(end.getDate() - 30);
        else if (range === '90d') start.setDate(end.getDate() - 90);
        else if (range === 'all') start.setFullYear(2020); // Far back

        return { 
            start: start.toISOString(), 
            end: end.toISOString() 
        };
    }, []);

    const fetchData = useCallback(async () => {
        try {
            const { start, end } = getDatesForRange(timeRange);
            const statsUrl = `${API}/api/agent/stats?start_date=${start}&end_date=${end}`;

            const [statusRes, statsRes, callsRes] = await Promise.all([
                fetch(`${API}/api/agent/status`),
                fetch(statsUrl),
                fetch(`${API}/api/calls?limit=25`),
            ]);
            setAgentStatus(await statusRes.json());
            setStats(await statsRes.json());
            const callData = await callsRes.json();
            setCalls(callData.calls || []);
        } catch (e) {
            console.error('Dashboard fetch error:', e);
        }
    }, [timeRange, getDatesForRange]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const statusLabel = {
        idle: 'Agent Idle',
        on_call: 'On Active Call',
        on_campaign: 'Running Campaign',
        campaign_paused: 'Campaign Paused',
    }[agentStatus.status] || 'Unknown';

    const statusDetail = agentStatus.status === 'on_call'
        ? `Calling ${agentStatus.phone_number || '...'}`
        : agentStatus.status === 'on_campaign'
            ? `${agentStatus.campaign_name} — ${agentStatus.campaign_stats?.completed || 0}/${agentStatus.campaign_stats?.total || 0}`
            : 'Waiting for commands';

    return (
        <div className="fade-in">
            <div className="page-header flex-between">
                <div>
                    <h1>Dashboard</h1>
                    <p>Real-time overview of your AI calling agent</p>
                </div>
                <div className="flex gap-1">
                    <div className="range-picker">
                        {RANGE_OPTIONS.map(opt => (
                            <button
                                key={opt.value}
                                className={`range-btn ${timeRange === opt.value ? 'active' : ''}`}
                                onClick={() => setTimeRange(opt.value)}
                            >
                                {opt.label}
                            </button>
                        ))}
                    </div>
                    <button className="btn-secondary" onClick={fetchData}>
                        <RefreshCw size={16} />
                    </button>
                </div>
            </div>

            {/* Agent Status Card */}
            <div className="agent-status-card">
                <div className="agent-status-left">
                    <div className={`status-dot-lg ${agentStatus.status}`} />
                    <div className="agent-status-text">
                        <h3>{statusLabel}</h3>
                        <span>{statusDetail}</span>
                    </div>
                </div>
                {agentStatus.status === 'idle' && (
                    <button className="btn-primary" onClick={() => navigate('/call')}>
                        <PhoneCall size={16} /> New Call
                    </button>
                )}
                {(agentStatus.status === 'on_campaign') && (
                    <button className="btn-secondary" onClick={() => navigate(`/campaigns/${agentStatus.campaign_id}`)}>
                        <Eye size={16} /> View Campaign
                    </button>
                )}
            </div>

            {/* Stats Grid */}
            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-icon blue"><Phone size={20} /></div>
                    <div>
                        <div className="stat-value">{stats.total_calls || 0}</div>
                        <div className="stat-label">Calls Today</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon green"><Clock size={20} /></div>
                    <div>
                        <div className="stat-value">{stats.total_minutes || 0}</div>
                        <div className="stat-label">Minutes Talked</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon green"><CheckCircle size={20} /></div>
                    <div>
                        <div className="stat-value">{stats.connected || 0}</div>
                        <div className="stat-label">Connected</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon red"><XCircle size={20} /></div>
                    <div>
                        <div className="stat-value">{(stats.failed || 0) + (stats.rejected || 0)}</div>
                        <div className="stat-label">Failed / Rejected</div>
                    </div>
                </div>
            </div>

            {/* Recent Call Log */}
            <div className="flex-between mb-2">
                <h3 className="section-title" style={{ margin: 0 }}>Recent Call Log</h3>
                <button className="btn-ghost text-sm" onClick={() => navigate('/campaigns')}>
                    <Megaphone size={14} /> View Campaigns
                </button>
            </div>

            {calls.length === 0 ? (
                <div className="empty-state card">
                    <BarChart3 size={48} />
                    <h3>No calls yet</h3>
                    <p>Start a call or campaign to see activity here</p>
                </div>
            ) : (
                <div className="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Phone Number</th>
                                <th>Name</th>
                                <th>Type</th>
                                <th>Status</th>
                                <th>Duration</th>
                                <th>Time</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {calls.map((call) => (
                                <tr key={call.call_id} onClick={() => setInspectorCallId(call.call_id)}>
                                    <td className="mono">{call.phone_number}</td>
                                    <td>{call.recipient_name || '—'}</td>
                                    <td><span className={`badge ${call.call_type}`}>{call.call_type}</span></td>
                                    <td><span className={`badge ${call.status}`}>{call.status}</span></td>
                                    <td>{call.duration_minutes ? `${call.duration_minutes} min` : formatDuration(call.duration_seconds)}</td>
                                    <td className="text-dim text-sm">{formatDate(call.created_at)}</td>
                                    <td>
                                        <button className="btn-ghost" onClick={(e) => { e.stopPropagation(); setInspectorCallId(call.call_id); }}>
                                            <ArrowUpRight size={14} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {inspectorCallId && (
                <CallInspector
                    callId={inspectorCallId}
                    onClose={() => setInspectorCallId(null)}
                />
            )}
        </div>
    );
}
