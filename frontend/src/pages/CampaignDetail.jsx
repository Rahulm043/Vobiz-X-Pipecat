import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ArrowLeft, Play, Pause, X, Check, Clock, Phone,
    ArrowUpRight, RefreshCw, XCircle,
} from 'lucide-react';
import CallInspector from '../components/CallInspector.jsx';

const API = '';

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

export default function CampaignDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [campaign, setCampaign] = useState(null);
    const [calls, setCalls] = useState([]);
    const [inspectorCallId, setInspectorCallId] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchData = useCallback(async () => {
        try {
            const res = await fetch(`${API}/api/campaigns/${id}`);
            const data = await res.json();
            setCampaign(data.campaign);
            setCalls(data.calls || []);
        } catch (e) {
            console.error('Campaign detail fetch error:', e);
        }
        setLoading(false);
    }, [id]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 4000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const handleAction = async (action) => {
        try {
            await fetch(`${API}/api/campaigns/${id}/${action}`, { method: 'POST' });
            fetchData();
        } catch (e) {
            console.error(`Campaign ${action} error:`, e);
        }
    };

    if (loading || !campaign) {
        return <div className="fade-in" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>Loading...</div>;
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
                        <span className="text-dim text-sm">• Created {formatDate(campaign.created_at)}</span>
                    </p>
                </div>
                <div className="flex-center gap-1">
                    <button className="btn-secondary" onClick={fetchData}><RefreshCw size={14} /></button>
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
                                <th>Status</th>
                                <th>Duration</th>
                                <th>End Reason</th>
                                <th>Time</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {calls.map((call, i) => (
                                <tr key={call.call_id} onClick={() => setInspectorCallId(call.call_id)}>
                                    <td className="text-dim">{i + 1}</td>
                                    <td className="mono">{call.phone_number}</td>
                                    <td>{call.recipient_name || '—'}</td>
                                    <td><span className={`badge ${call.status}`}>{call.status}</span></td>
                                    <td>{formatDuration(call.duration_seconds)}</td>
                                    <td className="text-dim text-sm">{call.end_reason || '—'}</td>
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

            {inspectorCallId && <CallInspector callId={inspectorCallId} onClose={() => setInspectorCallId(null)} />}
        </div>
    );
}
