import React, { useState, useEffect, useRef, useCallback } from 'react';
import useSWR from 'swr';
import {
    X, Phone, Clock, Calendar, Tag, FileText, Headphones,
    Play, Pause, SkipBack, User, Bot, Radio,
} from 'lucide-react';
import { authFetch, swrFetcher } from '../utils/api.js';
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:7860';

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

function RecordingPlayer({ callId, recordingFiles }) {
    const [track, setTrack] = useState('stereo');
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [duration, setDuration] = useState(0);
    const [audioSrc, setAudioSrc] = useState(null);
    const audioRef = useRef(null);

    useEffect(() => {
        setIsPlaying(false);
        setProgress(0);
        setDuration(0);

        // Try to get signed URL for remote storage
        const remoteKey = `${track}_remote`;
        const hasRemote = recordingFiles && recordingFiles[remoteKey];
        const hasLocal = recordingFiles && recordingFiles[track];

        if (callId && hasRemote) {
            authFetch(`/api/calls/${callId}/recording-url/${track}`)
                .then(r => r.json())
                .then(data => {
                    if (data.url) setAudioSrc(data.url);
                    else if (hasLocal) setAudioSrc(`${API_BASE}/recordings/${recordingFiles[track]}`);
                })
                .catch(err => {
                    console.error("Failed to fetch signed URL:", err);
                    if (hasLocal) setAudioSrc(`${API_BASE}/recordings/${recordingFiles[track]}`);
                });
        } else if (hasLocal) {
            setAudioSrc(`${API_BASE}/recordings/${recordingFiles[track]}`);
        } else {
            setAudioSrc(null);
        }
    }, [track, callId, recordingFiles]);

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
                <button className="btn-primary" style={{ width: '42px', height: '42px', borderRadius: '50%', padding: 0, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={togglePlay}>
                    {isPlaying ? <Pause size={20} /> : <Play size={20} fill="currentColor" style={{ marginLeft: '2px' }} />}
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
    const [tab, setTab] = useState('overview');

    const { data: call, mutate } = useSWR(callId ? `/api/calls/${callId}` : null, swrFetcher, {
        refreshInterval: (data) => {
            if (!data) return 3000; // Poll while initially loading if desired, or 0. Let's use 0 until we know.
            const isLive = ['queued', 'ringing', 'connected', 'in_progress'].includes(data.status);
            const transcriptPending = data.status === 'completed' && (!data.transcript || data.transcript.length === 0);
            return (isLive || transcriptPending) ? 3000 : 0;
        }
    });

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
                        <RecordingPlayer callId={call.call_id} recordingFiles={call.recording_files} />
                    </div>
                )}
            </div>
        </>
    );
}
