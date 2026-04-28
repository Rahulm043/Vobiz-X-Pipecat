import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
    X, Phone, Clock, Calendar, Tag, FileText, Headphones,
    Play, Pause, SkipBack, User, Bot, Radio,
} from 'lucide-react';

const API = '';

function formatDuration(seconds) {
    if (!seconds) return '0s';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatDateTime(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString([], {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
}

function RecordingPlayer({ recordingFiles }) {
    const [track, setTrack] = useState('stereo');
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [duration, setDuration] = useState(0);
    const audioRef = useRef(null);

    const trackFile = recordingFiles?.[track];
    const audioSrc = trackFile ? `${API}/recordings/${trackFile}` : null;

    useEffect(() => {
        setIsPlaying(false);
        setProgress(0);
        setDuration(0);
    }, [track]);

    useEffect(() => {
        const audio = audioRef.current;
        if (!audio) return;

        const updateProgress = () => {
            if (audio.duration) setProgress((audio.currentTime / audio.duration) * 100);
        };
        const onLoaded = () => setDuration(audio.duration || 0);
        const onEnded = () => { setIsPlaying(false); setProgress(0); };

        audio.addEventListener('timeupdate', updateProgress);
        audio.addEventListener('loadedmetadata', onLoaded);
        audio.addEventListener('ended', onEnded);
        return () => {
            audio.removeEventListener('timeupdate', updateProgress);
            audio.removeEventListener('loadedmetadata', onLoaded);
            audio.removeEventListener('ended', onEnded);
        };
    }, [audioSrc]);

    const togglePlay = () => {
        const audio = audioRef.current;
        if (!audio) return;
        if (isPlaying) { audio.pause(); }
        else { audio.play().catch(console.error); }
        setIsPlaying(!isPlaying);
    };

    const seekTo = (e) => {
        const audio = audioRef.current;
        if (!audio || !audio.duration) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const percent = (e.clientX - rect.left) / rect.width;
        audio.currentTime = percent * audio.duration;
    };

    const restart = () => {
        const audio = audioRef.current;
        if (!audio) return;
        audio.currentTime = 0;
        audio.play().catch(console.error);
        setIsPlaying(true);
    };

    if (!recordingFiles || !Object.values(recordingFiles).some(Boolean)) {
        return (
            <div className="recording-player" style={{ textAlign: 'center', padding: '2rem' }}>
                <Headphones size={24} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
                <p className="text-sm text-dim">No recordings available</p>
            </div>
        );
    }

    return (
        <div className="recording-player">
            <audio ref={audioRef} src={audioSrc} preload="metadata" />

            <div className="recording-track-select">
                {recordingFiles.stereo && (
                    <button className={`track-btn ${track === 'stereo' ? 'active' : ''}`} onClick={() => setTrack('stereo')}>
                        <Radio size={12} /> Stereo
                    </button>
                )}
                {recordingFiles.user && (
                    <button className={`track-btn ${track === 'user' ? 'active' : ''}`} onClick={() => setTrack('user')}>
                        <User size={12} /> User
                    </button>
                )}
                {recordingFiles.bot && (
                    <button className={`track-btn ${track === 'bot' ? 'active' : ''}`} onClick={() => setTrack('bot')}>
                        <Bot size={12} /> Bot
                    </button>
                )}
            </div>

            <div className="recording-controls">
                <button className="btn-ghost" onClick={restart}><SkipBack size={16} /></button>
                <button className="btn-primary" style={{ borderRadius: '50%', padding: '0.5rem' }} onClick={togglePlay}>
                    {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <span className="text-sm mono text-dim" style={{ marginLeft: 'auto' }}>
                    {formatDuration(audioRef.current?.currentTime || 0)} / {formatDuration(duration)}
                </span>
            </div>

            <div className="audio-progress" onClick={seekTo}>
                <div className="audio-progress-fill" style={{ width: `${progress}%` }} />
            </div>
        </div>
    );
}

export default function CallInspector({ callId, onClose }) {
    const [call, setCall] = useState(null);
    const [tab, setTab] = useState('overview');

    const fetchCall = useCallback(async () => {
        if (!callId) return;
        try {
            const r = await fetch(`${API}/api/calls/${callId}`);
            const data = await r.json();
            setCall(data);
        } catch (e) {
            console.error('CallInspector fetch error:', e);
        }
    }, [callId]);

    useEffect(() => {
        fetchCall();
    }, [fetchCall]);

    // Auto-refresh for live calls (ringing/connected) or calls where transcript is still pending
    useEffect(() => {
        if (!call) return;
        const isLive = ['queued', 'ringing', 'connected', 'in_progress'].includes(call.status);
        const transcriptPending = call.status === 'completed' && (!call.transcript || call.transcript.length === 0);
        if (!isLive && !transcriptPending) return;

        const interval = setInterval(fetchCall, 3000);
        return () => clearInterval(interval);
    }, [call, fetchCall]);

    if (!call) return null;

    return (
        <>
            <div className="inspector-overlay" onClick={onClose} />
            <div className="inspector-panel">
                <div className="inspector-header">
                    <h2>Call Details</h2>
                    <button className="btn-ghost" onClick={onClose}><X size={18} /></button>
                </div>

                <div className="inspector-tabs">
                    {['overview', 'transcript', 'recording'].map((t) => (
                        <button key={t} className={`inspector-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
                            {t.charAt(0).toUpperCase() + t.slice(1)}
                        </button>
                    ))}
                </div>

                {tab === 'overview' && (
                    <div>
                        <div className="inspector-section">
                            <h4>Call Info</h4>
                            <div className="detail-grid">
                                <div className="detail-item">
                                    <div className="detail-label">Phone</div>
                                    <div className="detail-value mono">{call.phone_number}</div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">Status</div>
                                    <div className="detail-value"><span className={`badge ${call.status}`}>{call.status}</span></div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">Type</div>
                                    <div className="detail-value"><span className={`badge ${call.call_type}`}>{call.call_type}</span></div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">Direction</div>
                                    <div className="detail-value">{call.direction}</div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">Duration</div>
                                    <div className="detail-value">{formatDuration(call.duration_seconds)} ({call.duration_minutes || 0} min billed)</div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">End Reason</div>
                                    <div className="detail-value">{call.end_reason || '—'}</div>
                                </div>
                            </div>
                        </div>

                        <div className="inspector-section">
                            <h4>Timestamps</h4>
                            <div className="detail-grid">
                                <div className="detail-item">
                                    <div className="detail-label">Created</div>
                                    <div className="detail-value text-sm">{formatDateTime(call.created_at)}</div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">Connected</div>
                                    <div className="detail-value text-sm">{formatDateTime(call.connected_at)}</div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">Ended</div>
                                    <div className="detail-value text-sm">{formatDateTime(call.ended_at)}</div>
                                </div>
                                <div className="detail-item">
                                    <div className="detail-label">Vobiz UUID</div>
                                    <div className="detail-value text-sm mono" style={{ fontSize: '0.7rem', wordBreak: 'break-all' }}>
                                        {call.vobiz_call_uuid || '—'}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {call.recipient_name && (
                            <div className="inspector-section">
                                <h4>Recipient</h4>
                                <div className="detail-grid">
                                    <div className="detail-item">
                                        <div className="detail-label">Name</div>
                                        <div className="detail-value">{call.recipient_name}</div>
                                    </div>
                                    <div className="detail-item">
                                        <div className="detail-label">Detail</div>
                                        <div className="detail-value">{call.recipient_detail || '—'}</div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {tab === 'transcript' && (
                    <div className="inspector-section">
                        <h4>Conversation</h4>
                        {(!call.transcript || call.transcript.length === 0) ? (
                            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-dim)' }}>
                                <FileText size={24} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
                                <p className="text-sm">No transcript available</p>
                            </div>
                        ) : (
                            <div className="transcript">
                                {call.transcript.map((msg, i) => (
                                    <div key={i} className={`transcript-msg ${msg.role}`}>
                                        {msg.text}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {tab === 'recording' && (
                    <div className="inspector-section">
                        <h4>Recording</h4>
                        <RecordingPlayer recordingFiles={call.recording_files} />
                    </div>
                )}
            </div>
        </>
    );
}
