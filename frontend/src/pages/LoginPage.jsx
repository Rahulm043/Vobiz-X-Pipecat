import React, { useState } from 'react';
import { supabase } from '../supabaseClient';
import { LogIn, Mail, Lock, ShieldCheck, AlertCircle } from 'lucide-react';

export default function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleLogin = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const { error } = await supabase.auth.signInWithPassword({
                email,
                password,
            });

            if (error) throw error;
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-container">
            <div className="login-card fade-in">
                <div className="login-header">
                    <div className="login-logo">
                        <ShieldCheck size={32} color="var(--primary)" />
                    </div>
                    <h1>Vobiz X Pipecat</h1>
                    <p>Enter your credentials to access the dashboard</p>
                </div>

                {error && (
                    <div className="login-error">
                        <AlertCircle size={16} />
                        <span>{error}</span>
                    </div>
                )}

                <form onSubmit={handleLogin} className="login-form">
                    <div className="input-group">
                        <label>Email Address</label>
                        <div className="input-wrapper">
                            <Mail size={18} className="input-icon" />
                            <input
                                type="email"
                                placeholder="name@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                        </div>
                    </div>

                    <div className="input-group">
                        <label>Password</label>
                        <div className="input-wrapper">
                            <Lock size={18} className="input-icon" />
                            <input
                                type="password"
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                            />
                        </div>
                    </div>

                    <button type="submit" className="btn-primary login-btn" disabled={loading}>
                        {loading ? (
                            <span className="flex-center gap-1">
                                <div className="spinner-sm" /> Signing in...
                            </span>
                        ) : (
                            <span className="flex-center gap-1">
                                <LogIn size={18} /> Sign In
                            </span>
                        )}
                    </button>
                </form>

                <div className="login-footer">
                    <p>© 2026 Vobiz AI. All rights reserved.</p>
                </div>
            </div>
            
            <style dangerouslySetInnerHTML={{ __html: `
                .login-container {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    background: radial-gradient(circle at top right, rgba(99, 102, 241, 0.1), transparent),
                                radial-gradient(circle at bottom left, rgba(168, 85, 247, 0.1), transparent);
                    padding: 20px;
                }
                .login-card {
                    width: 100%;
                    max-width: 400px;
                    background: var(--bg-glass);
                    backdrop-filter: blur(12px);
                    border: 1px solid var(--border);
                    border-radius: 20px;
                    padding: 40px;
                    box-shadow: var(--shadow-xl);
                }
                .login-header {
                    text-align: center;
                    margin-bottom: 32px;
                }
                .login-logo {
                    display: inline-flex;
                    padding: 12px;
                    background: rgba(99, 102, 241, 0.1);
                    border-radius: 12px;
                    margin-bottom: 16px;
                }
                .login-header h1 {
                    font-size: 1.5rem;
                    margin-bottom: 8px;
                    background: var(--gradient-primary);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }
                .login-header p {
                    color: var(--text-dim);
                    font-size: 0.9rem;
                }
                .login-form {
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                }
                .input-group label {
                    display: block;
                    font-size: 0.85rem;
                    font-weight: 500;
                    margin-bottom: 8px;
                    color: var(--text);
                }
                .input-wrapper {
                    position: relative;
                    display: flex;
                    align-items: center;
                }
                .input-icon {
                    position: absolute;
                    left: 12px;
                    color: var(--text-dim);
                }
                .input-wrapper input {
                    width: 100%;
                    padding: 12px 12px 12px 40px;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid var(--border);
                    border-radius: 10px;
                    color: var(--text);
                    transition: all 0.2s;
                }
                .input-wrapper input:focus {
                    outline: none;
                    border-color: var(--primary);
                    background: rgba(255, 255, 255, 0.08);
                    box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
                }
                .login-btn {
                    width: 100%;
                    padding: 12px;
                    font-weight: 600;
                    margin-top: 10px;
                }
                .login-error {
                    background: rgba(239, 68, 68, 0.1);
                    border: 1px solid rgba(239, 68, 68, 0.2);
                    border-radius: 10px;
                    padding: 12px;
                    color: #f87171;
                    font-size: 0.85rem;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin-bottom: 24px;
                }
                .login-footer {
                    margin-top: 32px;
                    text-align: center;
                    font-size: 0.75rem;
                    color: var(--text-dim);
                }
                .spinner-sm {
                    width: 16px;
                    height: 16px;
                    border: 2px solid rgba(255, 255, 255, 0.3);
                    border-top-color: white;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            ` }} />
        </div>
    );
}
