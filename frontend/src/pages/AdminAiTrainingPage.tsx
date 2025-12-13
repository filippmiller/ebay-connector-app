import { useState, useEffect } from 'react';
import { apiClient } from '../api/client';

interface TrainingSession {
    id: string;
    domain: string;
    title: string;
    notes?: string;
    started_at: string;
    ended_at?: string;
    examples_count: number;
}

export default function AdminAiTrainingPage() {
    const [sessions, setSessions] = useState<TrainingSession[]>([]);
    const [selectedDomain, setSelectedDomain] = useState('analytics');
    const [currentSession, setCurrentSession] = useState<TrainingSession | null>(null);

    // Voice recording state
    const [isRecording, setIsRecording] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);

    // Model interaction state
    const [modelResponse, setModelResponse] = useState<any>(null);
    const [isQuerying, setIsQuerying] = useState(false);
    const [editedSQL, setEditedSQL] = useState('');
    const [exampleStatus, setExampleStatus] = useState('draft');

    useEffect(() => {
        loadSessions();
    }, [selectedDomain]);

    const loadSessions = async () => {
        try {
            const response = await apiClient.get(`/api/ai-training/sessions?domain=${selectedDomain}`);
            setSessions(response.data);
        } catch (error) {
            console.error('Failed to load sessions:', error);
        }
    };

    const createSession = async () => {
        const title = prompt('Session title:');
        if (!title) return;

        try {
            const response = await apiClient.post('/api/ai-training/sessions', {
                domain: selectedDomain,
                title,
                notes: '',
            });
            setCurrentSession(response.data);
            await loadSessions();
        } catch (error) {
            console.error('Failed to create session:', error);
            alert('Failed to create session');
        }
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            const chunks: Blob[] = [];

            recorder.ondataavailable = (e) => chunks.push(e.data);
            recorder.onstop = async () => {
                const blob = new Blob(chunks, { type: 'audio/webm' });
                await transcribeAudio(blob);
                stream.getTracks().forEach(track => track.stop());
            };

            recorder.start();
            setMediaRecorder(recorder);
            setIsRecording(true);
        } catch (error) {
            console.error('Failed to start recording:', error);
            alert('Microphone access denied');
        }
    };

    const stopRecording = () => {
        if (mediaRecorder) {
            mediaRecorder.stop();
            setIsRecording(false);
        }
    };

    const transcribeAudio = async (audioBlob: Blob) => {
        try {
            const formData = new FormData();
            formData.append('file', audioBlob, 'recording.webm');
            formData.append('lang', 'ru');

            // Use external widget STT endpoint or implement own
            const widgetUrl = import.meta.env.VITE_CHAT_WIDGET_BASE_URL;
            const response = await fetch(`${widgetUrl}/api/stt/transcribe`, {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();
            setTranscript(data.text);
        } catch (error) {
            console.error('STT failed:', error);
            alert('Transcription failed');
        }
    };

    const askModel = async () => {
        if (!transcript.trim()) {
            alert('No transcript');
            return;
        }

        setIsQuerying(true);
        try {
            const response = await apiClient.post('/api/ai-assistant/query', {
                text: transcript,
                locale: 'ru-RU',
                source: 'admin-training',
                context: {
                    session_id: currentSession?.id,
                },
            });

            setModelResponse(response.data);
            setEditedSQL(response.data.sql || '');
        } catch (error) {
            console.error('Query failed:', error);
            alert('Model query failed');
        } finally {
            setIsQuerying(false);
        }
    };

    const saveExample = async (promote: boolean = false) => {
        if (!currentSession || !modelResponse) return;

        try {
            // Create example
            const exampleResponse = await apiClient.post('/api/ai-training/examples', {
                session_id: currentSession.id,
                domain: currentSession.domain,
                input_mode: 'voice',
                raw_input_text: transcript,
                raw_model_output: modelResponse,
                status: exampleStatus,
            });

            const exampleId = exampleResponse.data.id;

            // Update with approved output and optionally promote
            await apiClient.patch(`/api/ai-training/examples/${exampleId}`, {
                final_approved_output: {
                    sql: editedSQL,
                    explanation: modelResponse.explanation,
                },
                status: promote ? 'promoted' : exampleStatus,
                promote_to_rule: promote,
            });

            alert(promote ? 'Example promoted to semantic rule!' : 'Example saved!');

            // Reset
            setTranscript('');
            setModelResponse(null);
            setEditedSQL('');
            await loadSessions();
        } catch (error) {
            console.error('Failed to save example:', error);
            alert('Failed to save example');
        }
    };

    return (
        <div style={{ display: 'flex', height: '100vh', background: '#f5f5f5' }}>
            {/* Sidebar */}
            <div style={{ width: '300px', background: 'white', padding: '20px', borderRight: '1px solid #ddd' }}>
                <h2 style={{ marginTop: 0 }}>AI Training Center</h2>

                <div style={{ marginBottom: '20px' }}>
                    <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>Domain:</label>
                    <select
                        value={selectedDomain}
                        onChange={(e) => setSelectedDomain(e.target.value)}
                        style={{ width: '100%', padding: '8px', fontSize: '14px' }}
                    >
                        <option value="analytics">Analytics</option>
                        <option value="email">Email</option>
                        <option value="case">Case</option>
                    </select>
                </div>

                <button
                    onClick={createSession}
                    style={{ width: '100%', padding: '10px', marginBottom: '20px', background: '#4CAF50', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                >
                    + New Session
                </button>

                <div style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                    <h3 style={{ fontSize: '14px', color: '#666' }}>Sessions ({sessions.length})</h3>
                    {sessions.map(session => (
                        <div
                            key={session.id}
                            onClick={() => setCurrentSession(session)}
                            style={{
                                padding: '12px',
                                marginBottom: '8px',
                                background: currentSession?.id === session.id ? '#e3f2fd' : '#f9f9f9',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                border: currentSession?.id === session.id ? '2px solid #2196F3' : '1px solid #ddd',
                            }}
                        >
                            <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{session.title}</div>
                            <div style={{ fontSize: '12px', color: '#666' }}>
                                {session.examples_count} examples • {new Date(session.started_at).toLocaleDateString()}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Main Area */}
            <div style={{ flex: 1, padding: '20px' }}>
                {!currentSession ? (
                    <div style={{ textAlign: 'center', marginTop: '100px', color: '#999' }}>
                        Select or create a session to start training
                    </div>
                ) : (
                    <>
                        <h1>{currentSession.title}</h1>
                        <p style={{ color: '#666' }}>Domain: {currentSession.domain} • {currentSession.examples_count} examples</p>

                        {/* Voice Input Panel */}
                        <div style={{ background: 'white', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                            <h3>Voice Input</h3>
                            <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
                                <button
                                    onClick={isRecording ? stopRecording : startRecording}
                                    style={{
                                        padding: '12px 24px',
                                        background: isRecording ? '#f44336' : '#2196F3',
                                        color: 'white',
                                        border: 'none',
                                        borderRadius: '4px',
                                        cursor: 'pointer',
                                        fontSize: '16px',
                                    }}
                                >
                                    {isRecording ? '⏹ Stop Recording' : '🎤 Record'}
                                </button>
                                <button
                                    onClick={askModel}
                                    disabled={!transcript || isQuerying}
                                    style={{
                                        padding: '12px 24px',
                                        background: transcript && !isQuerying ? '#4CAF50' : '#ccc',
                                        color: 'white',
                                        border: 'none',
                                        borderRadius: '4px',
                                        cursor: transcript ? 'pointer' : 'not-allowed',
                                    }}
                                >
                                    {isQuerying ? 'Querying...' : 'Ask Model'}
                                </button>
                            </div>

                            {transcript && (
                                <div style={{ padding: '12px', background: '#f0f0f0', borderRadius: '4px', marginTop: '10px' }}>
                                    <strong>Transcript:</strong> {transcript}
                                </div>
                            )}
                        </div>

                        {/* Model Output */}
                        {modelResponse && (
                            <div style={{ background: 'white', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                                <h3>Model Proposal</h3>

                                <div style={{ marginBottom: '15px' }}>
                                    <strong>Generated SQL:</strong>
                                    <textarea
                                        value={editedSQL}
                                        onChange={(e) => setEditedSQL(e.target.value)}
                                        rows={8}
                                        style={{
                                            width: '100%',
                                            marginTop: '8px',
                                            padding: '12px',
                                            fontFamily: 'monospace',
                                            fontSize: '13px',
                                            border: '1px solid #ddd',
                                            borderRadius: '4px',
                                        }}
                                    />
                                </div>

                                <div style={{ marginBottom: '15px' }}>
                                    <strong>Explanation:</strong>
                                    <p style={{ padding: '12px', background: '#f9f9f9', borderRadius: '4px' }}>
                                        {modelResponse.explanation}
                                    </p>
                                </div>

                                <div style={{ marginBottom: '15px' }}>
                                    <strong>Status:</strong>
                                    <select
                                        value={exampleStatus}
                                        onChange={(e) => setExampleStatus(e.target.value)}
                                        style={{ marginLeft: '10px', padding: '6px', fontSize: '14px' }}
                                    >
                                        <option value="draft">Draft</option>
                                        <option value="approved">Approved</option>
                                        <option value="rejected">Rejected</option>
                                    </select>
                                </div>

                                <div style={{ display: 'flex', gap: '10px' }}>
                                    <button
                                        onClick={() => saveExample(false)}
                                        style={{
                                            padding: '10px 20px',
                                            background: '#2196F3',
                                            color: 'white',
                                            border: 'none',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                        }}
                                    >
                                        Save Example
                                    </button>
                                    <button
                                        onClick={() => saveExample(true)}
                                        style={{
                                            padding: '10px 20px',
                                            background: '#FF9800',
                                            color: 'white',
                                            border: 'none',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                        }}
                                    >
                                        ⭐ Save & Promote to Rule
                                    </button>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
