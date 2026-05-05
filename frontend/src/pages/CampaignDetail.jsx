import React, { useState } from 'react';
import useSWR from 'swr';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ArrowLeft, Play, Pause, X, Check, Clock, Phone,
    ArrowUpRight, RefreshCw, XCircle,
} from 'lucide-react';
import CallInspector from '../components/CallInspector.jsx';
import { authFetch, swrFetcher } from '../utils/api.js';

function formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatDuration(seconds) {
    if (!seconds) return '—';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function getAgentLabel(record) {
    return record?.metadata?.agent_name || record?.agent_name || record?.metadata?.agent_id || record?.agent_id || 'default';
}

export default function CampaignDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [inspectorCallId, setInspectorCallId] = useState(null);

    const { data, mutate, isLoading } = useSWR(`/api/campaigns/${id}`, swrFetcher, { refreshInterval: 4000 });
    
    const campaign = data?.campaign;
    const calls = data?.calls || [];

    const handleAction = async (action) => {
        try {
            await authFetch(`/api/campaigns/${id}/${action}`, { method: 'POST' });
            mutate();
        } catch (e) {
            console.error(`Campaign ${action} error:`, e);
        }
    };

    if (isLoading && !campaign) {
        return <div className="fade-in" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>Loading...</div>;
    }

    if (!campaign) {
        return <div className="fade-in" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>Campaign not found.</div>;
    }

    const s = campaign.stats || {};
    const totalProcessed = (s.completed || 0) + (s.failed || 0) + (s.rejected || 0);
    const progress = s.total > 0 ? Math.round((totalProcessed / s.total) * 100) : 0;
    const isRunning = campaign.status === 'running';
    const isPaused = campaign.status === 'paused';
    const isActive = isRunning || isPaused;

    return (
        <div className="fade-in">
            <div className="page-header flex-between">
                <div>
                    <button className="btn-ghost mb-1" onClick={() => navigate('/campaigns')}>
                        <ArrowLeft size={16} /> Back to Campaigns
                    </button>
                    <h1>{campaign.name}</h1>
                    <p className="flex-center gap-1">
                        <span className={`badge ${campaign.status}`}>{campaign.status}</span>
                        <span className="badge" style={{ background: 'rgba(255,255,255,0.04)' }}>{campaign.mode}</span>
                        <span className="badge agent">{getAgentLabel(campaign.recipients?.[0] || campaign)}</span>
                        <span className="text-dim text-sm">• Created {formatDate(campaign.created_at)}</span>
                    </p>
                </div>
                <div className="flex-center gap-1">
                    <button className="btn-secondary" onClick={() => mutate()}><RefreshCw size={14} /></button>
                    {isRunning && <button className="btn-warning" onClick={() => handleAction('pause')}><Pause size={14} /> Pause</button>}
                    {isPaused && <button className="btn-primary" onClick={() => handleAction('resume')}><Play size={14} /> Resume</button>}
                    {isActive && <button className="btn-danger" onClick={() => handleAction('cancel')}><X size={14} /> Cancel</button>}
                </div>
            </div>

            {/* Stats + Progress */}
            <div className="card mb-3">
                <div className="flex-between mb-2">
                    <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Progress</span>
                    <span style={{ fontSize: '1.5rem', fontWeight: 700 }}>{progress}%</span>
                </div>
                <div className="progress-bar" style={{ height: 10, marginBottom: '1rem' }}>
                    <div className={`progress-bar-fill ${campaign.status === 'completed' ? 'green' : 'blue'}`} style={{ width: `${progress}%` }} />
                </div>
                <div className="stats-grid" style={{ marginBottom: 0 }}>
                    <div className="stat-card">
                        <div className="stat-icon blue"><Phone size={18} /></div>
                        <div><div className="stat-value">{s.total || 0}</div><div className="stat-label">Total</div></div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-icon green"><Check size={18} /></div>
                        <div><div className="stat-value">{s.completed || 0}</div><div className="stat-label">Completed</div></div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-icon red"><XCircle size={18} /></div>
                        <div><div className="stat-value">{(s.failed || 0) + (s.rejected || 0)}</div><div className="stat-label">Failed</div></div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-icon yellow"><Clock size={18} /></div>
                        <div><div className="stat-value">{s.queued || 0}</div><div className="stat-label">Remaining</div></div>
                    </div>
                </div>
            </div>

            {/* Call Records Table */}
            <h3 className="section-title">Call Records</h3>
            {calls.length === 0 ? (
                <div className="empty-state card">
                    <Phone size={36} />
                    <h3>No calls yet</h3>
                    <p>Campaign calls will appear here as they start</p>
                </div>
            ) : (
                <div className="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Phone</th>
                                <th>Name</th>
                                <th>Agent</th>
                                <th>Status</th>
                                <th>Duration</th>
                                <th>End Reason</th>
                                <th>Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            {calls.map((call, i) => (
                                <tr key={call.call_id} onClick={() => setInspectorCallId(call.call_id)}>
                                    {/* Desktop Cells */}
                                    <td className="desktop-cell text-dim">{i + 1}</td>
                                    <td className="desktop-cell mono">{call.phone_number}</td>
                                    <td className="desktop-cell">{call.recipient_name || '—'}</td>
                                    <td className="desktop-cell"><span className="badge agent">{getAgentLabel(call)}</span></td>
                                    <td className="desktop-cell"><span className={`badge ${call.status}`}>{call.status}</span></td>
                                    <td className="desktop-cell">{formatDuration(call.duration_seconds)}</td>
                                    <td className="desktop-cell text-dim text-sm">{call.end_reason || '—'}</td>
                                    <td className="desktop-cell text-dim text-sm">{formatDate(call.created_at)}</td>
                                    {/* Mobile Cell */}
                                    <td className="mobile-cell">
                                        <div className="mono" style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text)', marginBottom: '2px' }}>
                                            {call.phone_number}
                                        </div>
                                        {call.recipient_name && <div className="text-dim" style={{ fontSize: '0.75rem', marginBottom: '2px' }}>{call.recipient_name}</div>}
                                        
                                        <span className={`badge ${call.status} badge-status`} style={{ transform: 'scale(0.85)', transformOrigin: 'top right' }}>{call.status}</span>
                                        
                                        <div className="flex" style={{ gap: '0.3rem', fontSize: '0.7rem', color: 'var(--text-dim)', alignItems: 'center', flexWrap: 'wrap' }}>
                                            <span>{formatDuration(call.duration_seconds)}</span>
                                            {call.end_reason && <><span>•</span><span>{call.end_reason}</span></>}
                                            <span>•</span>
                                            <span>{getAgentLabel(call)}</span>
                                            <span>•</span>
                                            <span>{formatDate(call.created_at)}</span>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {inspectorCallId && <CallInspector callId={inspectorCallId} onClose={() => setInspectorCallId(null)} />}
        </div>
    );
}
