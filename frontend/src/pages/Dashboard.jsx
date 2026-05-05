import React, { useState, useCallback } from 'react';
import useSWR from 'swr';
import { useNavigate } from 'react-router-dom';
import {
    Phone, Clock, CheckCircle, XCircle, Activity, PhoneCall,
    BarChart3, ArrowUpRight, RefreshCw, Eye, Megaphone,
} from 'lucide-react';
import CallInspector from '../components/CallInspector.jsx';
import { swrFetcher } from '../utils/api.js';

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

function getCallAgentLabel(call) {
    return call.metadata?.agent_name || call.metadata?.agent_id || 'default';
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
    const [inspectorCallId, setInspectorCallId] = useState(null);
    const [timeRange, setTimeRange] = useState('today');

    const getDatesForRange = useCallback((range) => {
        const end = new Date();
        end.setHours(23, 59, 59, 999); // End of today

        const start = new Date();
        start.setHours(0, 0, 0, 0); // Start of today
        
        if (range === '7d') start.setDate(end.getDate() - 7);
        else if (range === '30d') start.setDate(end.getDate() - 30);
        else if (range === '90d') start.setDate(end.getDate() - 90);
        else if (range === 'all') start.setFullYear(2020);

        return { 
            start: start.toISOString(), 
            end: end.toISOString() 
        };
    }, []);

    const { start, end } = getDatesForRange(timeRange);
    const statsUrl = `/api/agent/stats?start_date=${start}&end_date=${end}`;

    const { data: agentStatus = { status: 'idle' }, mutate: mutateStatus } = useSWR('/api/agent/status', swrFetcher, { refreshInterval: 5000 });
    const { data: stats = {}, mutate: mutateStats } = useSWR(statsUrl, swrFetcher, { refreshInterval: 5000 });
    const { data: callsData = { calls: [] }, mutate: mutateCalls } = useSWR('/api/calls?limit=25', swrFetcher, { refreshInterval: 5000 });
    const calls = callsData.calls || [];

    const handleRefresh = () => {
        mutateStatus();
        mutateStats();
        mutateCalls();
    };

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

    const agentName = import.meta.env.VITE_AGENT_NAME;

    return (
        <div className="fade-in">
            <div className="page-header flex-between">
                <div>
                    {agentName && <div className="agent-name-label">{agentName}</div>}
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
                    <button className="btn-secondary" onClick={handleRefresh}>
                        <RefreshCw size={16} />
                    </button>
                </div>
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

            {/* Agent Status Card (Now below stats) */}
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
                                <th>Agent</th>
                                <th>Status</th>
                                <th>Duration</th>
                                <th>Time</th>
                                <th>Source</th>
                            </tr>
                        </thead>
                        <tbody>
                            {calls.map((call) => (
                                <tr key={call.call_id} onClick={() => setInspectorCallId(call.call_id)}>
                                    {/* Desktop Cells */}
                                    <td className="desktop-cell mono">{call.phone_number}</td>
                                    <td className="desktop-cell">{call.recipient_name || '—'}</td>
                                    <td className="desktop-cell"><span className={`badge ${call.call_type}`}>{call.call_type}</span></td>
                                    <td className="desktop-cell"><span className="badge agent">{getCallAgentLabel(call)}</span></td>
                                    <td className="desktop-cell"><span className={`badge ${call.status}`}>{call.status}</span></td>
                                    <td className="desktop-cell">{call.duration_minutes ? `${call.duration_minutes} min` : formatDuration(call.duration_seconds)}</td>
                                    <td className="desktop-cell text-dim text-sm">{formatDate(call.created_at)}</td>
                                    <td className="desktop-cell">
                                        <div className="source-label">
                                            {call.campaign_name || 'Single Call'}
                                        </div>
                                    </td>
                                    {/* Mobile Cell */}
                                    <td className="mobile-cell">
                                        <div className="mono" style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text)', marginBottom: '2px' }}>
                                            {call.phone_number}
                                        </div>
                                        {call.recipient_name && <div className="text-dim" style={{ fontSize: '0.75rem', marginBottom: '2px' }}>{call.recipient_name}</div>}
                                        
                                        <span className={`badge ${call.status} badge-status`} style={{ transform: 'scale(0.85)', transformOrigin: 'top right' }}>{call.status}</span>
                                        
                                        <div className="flex" style={{ gap: '0.3rem', fontSize: '0.7rem', color: 'var(--text-dim)', alignItems: 'center', flexWrap: 'wrap' }}>
                                            <span className={`badge ${call.call_type}`} style={{ padding: '0.1rem 0.3rem', fontSize: '0.65rem' }}>{call.call_type}</span>
                                            <span>•</span>
                                            <span>{getCallAgentLabel(call)}</span>
                                            <span>•</span>
                                            <span>{call.duration_minutes ? `${call.duration_minutes} min` : formatDuration(call.duration_seconds)}</span>
                                            <span>•</span>
                                            <span>{formatDate(call.created_at)}</span>
                                            <span>•</span>
                                            <span className="text-primary" style={{ fontWeight: 600 }}>{call.campaign_name || 'Single Call'}</span>
                                        </div>
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
