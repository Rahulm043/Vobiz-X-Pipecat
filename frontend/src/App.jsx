import React, { useState, useEffect, useRef } from 'react';
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import { WebSocketTransport, ProtobufFrameSerializer } from '@pipecat-ai/websocket-transport';
import { PipecatClientProvider, PipecatClientAudio, usePipecatClient, useRTVIClientEvent } from '@pipecat-ai/client-react';
import { Mic, MicOff, Phone, PhoneOff, MessageSquare, Loader2 } from 'lucide-react';
import './index.css';

// Initialize the client outside the component tree
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/web-ws`;

const transport = new WebSocketTransport({
  wsUrl,
  serializer: new ProtobufFrameSerializer(),
  playerSampleRate: 24000,
  recorderSampleRate: 16000,
});
// Monkey-patch to avoid "not implemented" errors in React SDK
Object.defineProperty(transport, 'isCamEnabled', { get: () => false });
Object.defineProperty(transport, 'isSharingScreen', { get: () => false });

const client = new PipecatClient({
  transport,
  enableMic: true,
});

function VoiceAssistant() {
  const client = usePipecatClient();
  const [status, setStatus] = useState('idle');
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const [error, setError] = useState(null);
  const transcriptEndRef = useRef(null);
  const audioRef = useRef(null);

  // Debugging: Monitor track started
  useRTVIClientEvent(RTVIEvent.TrackStarted, (track, participant) => {
    console.log('[DEBUG] Track Started:', track.kind, 'from', participant?.local ? 'local' : 'bot');
    if (track.kind === 'audio' && !participant?.local && audioRef.current) {
      console.log('[DEBUG] Manually attaching bot audio track to fallback element');
      const stream = new MediaStream([track]);
      audioRef.current.srcObject = stream;
      audioRef.current.play().catch(e => console.error('[DEBUG] Manual playback failed:', e));
    }
  });

  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, () => {
    console.log('[DEBUG] Bot started speaking...');
  });

  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, () => {
    console.log('[DEBUG] Bot stopped speaking.');
  });

  // Sync state with client status
  useRTVIClientEvent(RTVIEvent.Connected, () => {
    console.log('[DEBUG] Client connected');
    setStatus('connected');
  });
  useRTVIClientEvent(RTVIEvent.Disconnected, () => {
    console.log('[DEBUG] Client disconnected');
    setStatus('idle');
  });
  useRTVIClientEvent(RTVIEvent.Error, (err) => {
    console.error('[DEBUG] Client Error:', err);
    setError(err.message || 'An error occurred');
    setStatus('error');
  });

  // Handle transcripts
  useRTVIClientEvent(RTVIEvent.UserTranscript, (data) => {
    console.log('[DEBUG] User Transcript:', data.text);
    setTranscript(prev => [...prev, { role: 'user', text: data.text }]);
  });
  useRTVIClientEvent(RTVIEvent.BotTranscript, (data) => {
    console.log('[DEBUG] Bot Transcript:', data.text);
    setTranscript(prev => [...prev, { role: 'bot', text: data.text }]);
  });

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  const startSession = async () => {
    setError(null);
    setStatus('connecting');
    setTranscript([]);
    try {
      console.log('[DEBUG] Starting session...');
      await client.connect();
    } catch (err) {
      console.error('[DEBUG] Connection error:', err);
      setError(err.message || 'Connection failed');
      setStatus('error');
    }
  };

  const stopSession = async () => {
    await client.disconnect();
  };

  const toggleMute = () => {
    const newMuteState = !isMuted;
    client.enableMic(!newMuteState);
    setIsMuted(newMuteState);
  };

  return (
    <div className="card">
      {/* Standard hidden audio helper */}
      <PipecatClientAudio />

      {/* Manual fallback audio helper */}
      <audio ref={audioRef} autoPlay style={{ display: 'none' }} />

      <header>
        <h1>Pipecat Agent</h1>
        <div className="status-indicator">
          <span className={`dot ${status}`} />
          <span>
            {status === 'idle' && 'Ready to connect'}
            {status === 'connecting' && 'Connecting to agent...'}
            {status === 'connected' && 'Agent Online'}
            {status === 'error' && `Error: ${error}`}
          </span>
        </div>
      </header>

      <section className="transcript-container">
        {transcript.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', textAlign: 'center', marginTop: '4rem', opacity: 0.5 }}>
            <MessageSquare size={48} style={{ marginBottom: '1rem' }} />
            <p>Start the call to begin chatting</p>
          </div>
        ) : (
          transcript.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              {msg.text}
            </div>
          ))
        )}
        <div ref={transcriptEndRef} />
      </section>

      <footer className="controls">
        {status === 'connected' ? (
          <>
            <button className="secondary" onClick={toggleMute}>
              {isMuted ? <MicOff size={20} /> : <Mic size={20} />}
              {isMuted ? 'Unmute' : 'Mute'}
            </button>
            <button className="danger" onClick={stopSession}>
              <PhoneOff size={20} />
              End Call
            </button>
          </>
        ) : (
          <button
            className="primary"
            onClick={startSession}
            disabled={status === 'connecting'}
          >
            {status === 'connecting' ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Phone size={20} />
            )}
            {status === 'connecting' ? 'Connecting...' : 'Start Voice Chat'}
          </button>
        )}
      </footer>

      {status === 'connected' && (
        <div className="visualizer">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="bar" style={{ height: `${4 + Math.random() * 20}px` }} />
          ))}
        </div>
      )}
    </div>
  );
}

function App() {
  return (
    <PipecatClientProvider client={client}>
      <VoiceAssistant />
    </PipecatClientProvider>
  );
}

export default App;
