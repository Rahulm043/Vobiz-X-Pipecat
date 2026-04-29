import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Megaphone, Plus, Play, Pause, Check, X, Clock,
} from 'lucide-react';

const API = '';

function formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function CampaignList() {
    const navigate = useNavigate();
    const [campaigns, setCampaigns] = useState([]);

    useEffect(() => {
        fetchCampaigns();
        const interval = setInterval(fetchCampaigns, 8000);
        return () => clearInterval(interval);
    }, []);

    const fetchCampaigns = async () => {
        try {
            const res = await fetch(`${API}/api/campaigns`);
            const data = await res.json();
            setCampaigns(data.campaigns || []);
        } catch (e) {
            console.error('Campaign fetch error:', e);
        }
    };

    const getProgressPercent = (campaign) => {
        const s = campaign.stats || {};
        return s.total > 0 ? Math.round(((s.completed + s.failed + s.rejected) / s.total) * 100) : 0;
    };

    return (
        <div className="fade-in">
            <div className="page-header flex-between">
                <div>
                    <h1>Campaigns</h1>
                    <p>Manage your outbound calling campaigns</p>
                </div>
                <button className="btn-primary highlight" onClick={() => navigate('/campaigns/new')}>
                    <Plus size={16} /> New Campaign
                </button>
            </div>

            {campaigns.length === 0 ? (
                <div className="empty-state card">
                    <Megaphone size={48} />
                    <h3>No campaigns yet</h3>
                    <p>Create your first campaign to start making bulk calls</p>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {campaigns.map((campaign) => {
                        const progress = getProgressPercent(campaign);
                        const s = campaign.stats || {};
                        return (
                            <div
                                key={campaign.campaign_id}
                                className="card"
                                style={{ cursor: 'pointer' }}
                                onClick={() => navigate(`/campaigns/${campaign.campaign_id}`)}
                            >
                                <div className="flex-between mb-2">
                                    <div>
                                        <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>{campaign.name}</h3>
                                        <span className="text-sm text-dim">{formatDate(campaign.created_at)}</span>
                                    </div>
                                    <div className="flex-center gap-2">
                                        <span className={`badge ${campaign.status}`}>{campaign.status}</span>
                                        <span className="badge" style={{ background: 'rgba(255,255,255,0.04)' }}>
                                            {campaign.mode}
                                        </span>
                                    </div>
                                </div>

                                <div className="progress-bar mb-1">
                                    <div
                                        className={`progress-bar-fill ${campaign.status === 'completed' ? 'green' : 'blue'}`}
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>

                                <div className="flex-between" style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                                    <span>{progress}% complete</span>
                                    <div className="flex-center gap-2">
                                        <span className="flex-center gap-1"><Check size={12} style={{ color: 'var(--success)' }} />{s.completed || 0}</span>
                                        <span className="flex-center gap-1"><X size={12} style={{ color: 'var(--error)' }} />{s.failed || 0}</span>
                                        <span className="flex-center gap-1"><Clock size={12} />{s.queued || 0} left</span>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
