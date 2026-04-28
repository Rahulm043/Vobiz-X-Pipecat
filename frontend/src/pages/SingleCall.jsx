import React, { useState, useRef, useEffect } from 'react';
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import { WebSocketTransport, ProtobufFrameSerializer } from '@pipecat-ai/websocket-transport';
import { PipecatClientProvider, PipecatClientAudio, usePipecatClient, useRTVIClientEvent } from '@pipecat-ai/client-react';
import {
    Phone, PhoneOff, PhoneCall, Mic, MicOff, Loader2,
    MessageSquare, Radio,
} from 'lucide-react';

const API = '';

function WebCallUI() {
    const client = usePipecatClient();
    const [status, setStatus] = useState('idle');
    const [isMuted, setIsMuted] = useState(false);
    const [transcript, setTranscript] = useState([]);
    const [error, setError] = useState(null);
    const transcriptEndRef = useRef(null);
    const audioRef = useRef(null);

    useRTVIClientEvent(RTVIEvent.TrackStarted, (track, participant) => {
        if (track.kind === 'audio' && !participant?.local && audioRef.current) {
            const stream = new MediaStream([track]);
            audioRef.current.srcObject = stream;
            audioRef.current.play().catch(e => console.error(e));
        }
    });

    useRTVIClientEvent(RTVIEvent.Connected, () => setStatus('connected'));
    useRTVIClientEvent(RTVIEvent.Disconnected, () => setStatus('idle'));
    useRTVIClientEvent(RTVIEvent.Error, (err) => { setError(err.message); setStatus('error'); });
    useRTVIClientEvent(RTVIEvent.UserTranscript, (d) => setTranscript(p => [...p, { role: 'user', text: d.text }]));
    useRTVIClientEvent(RTVIEvent.BotTranscript, (d) => setTranscript(p => [...p, { role: 'bot', text: d.text }]));

    useEffect(() => { transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [transcript]);

    const start = async () => {
        setError(null); setStatus('connecting'); setTranscript([]);
        try { await client.connect(); } catch (e) { setError(e.message); setStatus('error'); }
    };

    const stop = async () => { await client.disconnect(); };
    const toggleMute = () => { const n = !isMuted; client.enableMic(!n); setIsMuted(n); };

    return (
        <div className="card" style={{ marginTop: '1.5rem' }}>
            <PipecatClientAudio />
            <audio ref={audioRef} autoPlay style={{ display: 'none' }} />

            <div className="flex-between mb-2">
                <div className="flex-center">
                    <Radio size={18} className={status === 'connected' ? '' : ''} style={{ color: status === 'connected' ? 'var(--success)' : 'var(--text-dim)' }} />
                    <span style={{ fontWeight: 600 }}>Web Call</span>
                </div>
                <span className={`badge ${status === 'connected' ? 'connected' : status === 'connecting' ? 'running' : 'idle'}`}>
                    {status === 'connected' ? 'Live' : status === 'connecting' ? 'Connecting...' : 'Ready'}
                </span>
            </div>

            <div className="transcript" style={{ height: 280, marginBottom: '1rem' }}>
                {transcript.length === 0 ? (
                    <div className="empty-state" style={{ padding: '2rem' }}>
                        <MessageSquare size={36} />
                        <p className="text-sm">Start the web call to see transcript</p>
                    </div>
                ) : (
                    transcript.map((msg, i) => (
                        <div key={i} className={`transcript-msg ${msg.role}`}>{msg.text}</div>
                    ))
                )}
                <div ref={transcriptEndRef} />
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                {status === 'connected' ? (
                    <>
                        <button className="btn-secondary" onClick={toggleMute}>
                            {isMuted ? <MicOff size={16} /> : <Mic size={16} />}
                            {isMuted ? 'Unmute' : 'Mute'}
                        </button>
                        <button className="btn-danger" onClick={stop}>
                            <PhoneOff size={16} /> End Call
                        </button>
                    </>
                ) : (
                    <button className="btn-primary" onClick={start} disabled={status === 'connecting'}>
                        {status === 'connecting' ? <Loader2 size={16} className="animate-spin" /> : <Phone size={16} />}
                        {status === 'connecting' ? 'Connecting...' : 'Start Web Call'}
                    </button>
                )}
            </div>
        </div>
    );
}

// Create client outside component
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/web-ws`;
const transport = new WebSocketTransport({ wsUrl, serializer: new ProtobufFrameSerializer(), playerSampleRate: 24000, recorderSampleRate: 16000 });
Object.defineProperty(transport, 'isCamEnabled', { get: () => false });
Object.defineProperty(transport, 'isSharingScreen', { get: () => false });
const pipecatClient = new PipecatClient({ transport, enableMic: true });

export default function SingleCall() {
    const [phoneNumber, setPhoneNumber] = useState('');
    const [isDialing, setIsDialing] = useState(false);
    const [dialResult, setDialResult] = useState(null);
    const [mode, setMode] = useState('sip'); // 'sip' or 'web'

    const handleSipCall = async () => {
        if (!phoneNumber.trim()) return;
        setIsDialing(true);
        setDialResult(null);
        try {
            const res = await fetch(`${API}/api/calls/single`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone_number: phoneNumber.startsWith('+') ? phoneNumber : `+91${phoneNumber}` }),
            });
            const data = await res.json();
            if (res.ok) {
                setDialResult({ success: true, callId: data.call_id, message: `Call initiated to ${data.phone_number}` });
            } else {
                setDialResult({ success: false, message: data.detail || 'Failed to initiate call' });
            }
        } catch (e) {
            setDialResult({ success: false, message: e.message });
        }
        setIsDialing(false);
    };

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Single Call</h1>
                <p>Make an individual SIP call or test with a web call</p>
            </div>

            {/* Mode Toggle */}
            <div className="inspector-tabs" style={{ maxWidth: 300, marginBottom: '1.5rem' }}>
                <button className={`inspector-tab ${mode === 'sip' ? 'active' : ''}`} onClick={() => setMode('sip')}>
                    <PhoneCall size={14} style={{ marginRight: 4 }} /> SIP Call
                </button>
                <button className={`inspector-tab ${mode === 'web' ? 'active' : ''}`} onClick={() => setMode('web')}>
                    <Radio size={14} style={{ marginRight: 4 }} /> Web Call
                </button>
            </div>

            {mode === 'sip' ? (
                <div className="card" style={{ maxWidth: 480 }}>
                    <div className="form-group">
                        <label>Phone Number</label>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <span style={{
                                background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)',
                                borderRadius: 'var(--radius-sm)', padding: '0.7rem 0.75rem', color: 'var(--text-dim)',
                                fontSize: '0.9rem', fontWeight: 500,
                            }}>+91</span>
                            <input
                                type="tel"
                                placeholder="9876543210"
                                value={phoneNumber}
                                onChange={(e) => setPhoneNumber(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSipCall()}
                            />
                        </div>
                    </div>

                    {dialResult && (
                        <div className={`card ${dialResult.success ? '' : ''}`} style={{
                            background: dialResult.success ? 'var(--success-bg)' : 'var(--error-bg)',
                            border: `1px solid ${dialResult.success ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
                            padding: '0.75rem 1rem', marginBottom: '1rem', fontSize: '0.875rem',
                            color: dialResult.success ? 'var(--success)' : 'var(--error)',
                        }}>
                            {dialResult.message}
                        </div>
                    )}

                    <button className="btn-primary" onClick={handleSipCall} disabled={isDialing || !phoneNumber.trim()} style={{ width: '100%' }}>
                        {isDialing ? <Loader2 size={16} /> : <PhoneCall size={16} />}
                        {isDialing ? 'Dialing...' : 'Call Now'}
                    </button>
                </div>
            ) : (
                <PipecatClientProvider client={pipecatClient}>
                    <WebCallUI />
                </PipecatClientProvider>
            )}
        </div>
    );
}
