import { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import { Zap, Eye, EyeOff, Loader2 } from 'lucide-react';

const DEMO_CREDS = [
  { label: 'Admin', email: 'admin@example.com', password: 'admin123', role: 'admin' },
  { label: 'Manager', email: 'anish@iwsfinserve.com', password: 'manager123', role: 'manager' },
  { label: 'Sales Rep', email: 'rahul@iwsfinserve.com', password: 'rahul123', role: 'sales_rep' },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]     = useState(false);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  if (user) return <Navigate to="/dashboard" replace />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) { setError('Email and password are required.'); return; }
    setError('');
    setLoading(true);
    try {
      await login(email.trim(), password);
      toast.success('Welcome back!');
      navigate('/dashboard');
    } catch (err) {
      const status = err.response?.status;
      if (status === 401 || status === 400) {
        setError('Invalid email or password.');
      } else if (!err.response) {
        setError('Cannot connect to server. Is the backend running?');
      } else {
        setError(err.response?.data?.detail || 'Login failed.');
      }
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = (cred) => {
    setEmail(cred.email);
    setPassword(cred.password);
    setError('');
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
      background: 'var(--bg)',
    }}>
      {/* Decorative blobs */}
      <div style={{
        position: 'fixed', top: '10%', left: '10%', width: 400, height: 400,
        background: 'radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%)',
        borderRadius: '50%', pointerEvents: 'none',
      }} />
      <div style={{
        position: 'fixed', bottom: '10%', right: '10%', width: 300, height: 300,
        background: 'radial-gradient(circle, rgba(14,165,233,0.1) 0%, transparent 70%)',
        borderRadius: '50%', pointerEvents: 'none',
      }} />

      <div style={{ width: '100%', maxWidth: 440, position: 'relative', zIndex: 1 }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 16,
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
            boxShadow: '0 8px 24px rgba(99,102,241,0.35)',
          }}>
            <Zap size={28} color="#fff" />
          </div>
          <h1 style={{ fontSize: '1.75rem', marginBottom: 6 }}>Lead Management</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>IWS Finserve CRM — Sign in to your account</p>
        </div>

        {/* Card */}
        <div className="glass-card" style={{ padding: '32px 36px' }}>
          <form onSubmit={handleSubmit} id="login-form">
            <div className="form-group">
              <label className="form-label" htmlFor="login-email">Email Address</label>
              <input
                id="login-email"
                type="email"
                className="form-input"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                disabled={loading}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="login-password">Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  id="login-password"
                  type={showPw ? 'text' : 'password'}
                  className="form-input"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={loading}
                  style={{ paddingRight: 44 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  id="toggle-password-btn"
                  style={{
                    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer',
                  }}
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="alert alert-danger" id="login-error-msg" style={{ marginBottom: 16 }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary btn-full btn-lg"
              id="login-submit-btn"
              disabled={loading}
            >
              {loading ? <><Loader2 size={16} style={{ animation: 'spin 0.7s linear infinite' }} /> Signing in...</> : 'Sign In'}
            </button>
          </form>

          <div style={{ marginTop: 28 }}>
            <hr className="divider" style={{ margin: '0 0 20px' }} />
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', marginBottom: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.8px' }}>
              Quick Demo Login
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {DEMO_CREDS.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  className="btn btn-ghost"
                  id={`demo-login-${c.role}-btn`}
                  onClick={() => fillDemo(c)}
                  style={{ justifyContent: 'space-between', fontSize: '0.8rem' }}
                >
                  <span style={{ fontWeight: 600 }}>{c.label}</span>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>{c.email}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <p style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 24 }}>
          IWS Finserve Lead Management System © {new Date().getFullYear()}
        </p>
      </div>
    </div>
  );
}
