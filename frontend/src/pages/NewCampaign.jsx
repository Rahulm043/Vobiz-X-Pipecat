import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Upload, FileSpreadsheet, Plus, Trash2, Play, AlertCircle,
    Users, Settings2, ArrowRight,
} from 'lucide-react';

const API = '';

export default function NewCampaign() {
    const navigate = useNavigate();
    const fileRef = useRef(null);

    const [name, setName] = useState('');
    const [mode, setMode] = useState('sequential');
    const [concurrentLimit, setConcurrentLimit] = useState(1);
    const [callGapSeconds, setCallGapSeconds] = useState(30);
    const [recipients, setRecipients] = useState([]);
    const [manualNumbers, setManualNumbers] = useState('');
    const [tab, setTab] = useState('upload'); // 'upload' or 'manual'
    const [uploading, setUploading] = useState(false);
    const [uploadResult, setUploadResult] = useState(null);
    const [launching, setLaunching] = useState(false);
    const [error, setError] = useState(null);

    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setUploading(true);
        setUploadResult(null);
        setError(null);

        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch(`${API}/api/upload/recipients`, { method: 'POST', body: formData });
            const data = await res.json();
            setUploadResult(data);
            setRecipients(data.recipients || []);
        } catch (e) {
            setError(`Upload failed: ${e.message}`);
        }
        setUploading(false);
    };

    const handleManualParse = async () => {
        if (!manualNumbers.trim()) return;
        setUploading(true);
        setError(null);
        try {
            const res = await fetch(`${API}/api/upload/recipients`, {
                method: 'POST',
                body: manualNumbers,
            });
            const data = await res.json();
            setUploadResult(data);
            setRecipients(data.recipients || []);
        } catch (e) {
            setError(`Parse failed: ${e.message}`);
        }
        setUploading(false);
    };

    const removeRecipient = (index) => {
        setRecipients((prev) => prev.filter((_, i) => i !== index));
    };

    const startCampaign = async () => {
        if (!name.trim()) { setError('Please enter a campaign name'); return; }
        if (recipients.length === 0) { setError('Add at least one recipient'); return; }

        setLaunching(true);
        setError(null);
        try {
            const res = await fetch(`${API}/api/campaigns`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name, mode, concurrent_limit: concurrentLimit,
                    call_gap_seconds: callGapSeconds, recipients,
                }),
            });
            const data = await res.json();
            if (res.ok) {
                navigate(`/campaigns/${data.campaign_id}`);
            } else {
                setError(data.detail || 'Failed to create campaign');
            }
        } catch (e) {
            setError(e.message);
        }
        setLaunching(false);
    };

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>New Campaign</h1>
                <p>Create a bulk outbound calling campaign</p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                {/* Left: Config */}
                <div>
                    <div className="card mb-3">
                        <h3 className="section-title flex-center"><Settings2 size={18} /> Configuration</h3>

                        <div className="form-group">
                            <label>Campaign Name</label>
                            <input placeholder="e.g. Spring Outreach 2026" value={name} onChange={(e) => setName(e.target.value)} />
                        </div>

                        <div className="form-group">
                            <label>Mode</label>
                            <div className="inspector-tabs">
                                <button className={`inspector-tab ${mode === 'sequential' ? 'active' : ''}`} onClick={() => setMode('sequential')}>
                                    Sequential
                                </button>
                                <button className={`inspector-tab ${mode === 'concurrent' ? 'active' : ''}`} onClick={() => setMode('concurrent')}>
                                    Concurrent
                                </button>
                            </div>
                        </div>

                        {mode === 'concurrent' && (
                            <div className="form-group">
                                <label>Max Concurrent Calls</label>
                                <input type="number" min={1} max={5} value={concurrentLimit} onChange={(e) => setConcurrentLimit(parseInt(e.target.value) || 1)} />
                            </div>
                        )}

                        {mode === 'sequential' && (
                            <div className="form-group">
                                <label>Gap Between Calls (seconds)</label>
                                <input type="number" min={5} max={300} value={callGapSeconds} onChange={(e) => setCallGapSeconds(parseInt(e.target.value) || 30)} />
                            </div>
                        )}
                    </div>

                    {error && (
                        <div className="card mb-2" style={{
                            background: 'var(--error-bg)', border: '1px solid rgba(239,68,68,0.2)',
                            padding: '0.75rem 1rem', color: 'var(--error)', fontSize: '0.875rem',
                        }}>
                            <AlertCircle size={14} style={{ marginRight: 6 }} /> {error}
                        </div>
                    )}

                    <button className="btn-primary" style={{ width: '100%' }} onClick={startCampaign} disabled={launching || recipients.length === 0}>
                        <Play size={16} /> {launching ? 'Launching Campaign...' : `Launch Campaign (${recipients.length} recipients)`}
                    </button>
                </div>

                {/* Right: Recipients */}
                <div>
                    <div className="card">
                        <h3 className="section-title flex-center"><Users size={18} /> Recipients</h3>

                        <div className="inspector-tabs mb-2">
                            <button className={`inspector-tab ${tab === 'upload' ? 'active' : ''}`} onClick={() => setTab('upload')}>
                                <Upload size={14} /> Upload File
                            </button>
                            <button className={`inspector-tab ${tab === 'manual' ? 'active' : ''}`} onClick={() => setTab('manual')}>
                                <Plus size={14} /> Manual Entry
                            </button>
                        </div>

                        {tab === 'upload' ? (
                            <>
                                <div className="file-drop-zone" onClick={() => fileRef.current?.click()}>
                                    <FileSpreadsheet size={36} style={{ color: 'var(--primary)', marginBottom: '0.5rem' }} />
                                    <p><strong>Click to upload</strong> CSV or Excel file</p>
                                    <p className="text-sm text-dim">Columns: phone, name, detail</p>
                                </div>
                                <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.txt" style={{ display: 'none' }} onChange={handleFileUpload} />
                            </>
                        ) : (
                            <div className="form-group">
                                <label>Phone Numbers (one per line)</label>
                                <textarea
                                    rows={6}
                                    placeholder={"9876543210\n9123456789\n8001234567"}
                                    value={manualNumbers}
                                    onChange={(e) => setManualNumbers(e.target.value)}
                                />
                                <button className="btn-secondary mt-2" style={{ width: '100%' }} onClick={handleManualParse} disabled={uploading}>
                                    <ArrowRight size={16} /> Parse Numbers
                                </button>
                            </div>
                        )}

                        {uploadResult && (
                            <div className="mt-2" style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                                ✅ {uploadResult.summary?.valid || 0} valid / {uploadResult.summary?.invalid || 0} invalid
                                {uploadResult.warnings?.length > 0 && (
                                    <div style={{ marginTop: '0.5rem', color: 'var(--warning)' }}>
                                        {uploadResult.warnings.slice(0, 3).map((w, i) => <div key={i}>⚠️ {w}</div>)}
                                    </div>
                                )}
                            </div>
                        )}

                        {recipients.length > 0 && (
                            <div className="mt-2">
                                <div className="table-container" style={{ maxHeight: 320, overflowY: 'auto' }}>
                                    <table>
                                        <thead>
                                            <tr>
                                                <th>#</th>
                                                <th>Phone</th>
                                                <th>Name</th>
                                                <th></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {recipients.map((r, i) => (
                                                <tr key={i}>
                                                    <td className="text-dim">{i + 1}</td>
                                                    <td className="mono">{r.phone_number}</td>
                                                    <td>{r.name || '—'}</td>
                                                    <td>
                                                        <button className="btn-ghost" onClick={() => removeRecipient(i)}>
                                                            <Trash2 size={14} style={{ color: 'var(--error)' }} />
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
