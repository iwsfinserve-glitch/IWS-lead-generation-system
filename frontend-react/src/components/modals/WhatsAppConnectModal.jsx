import { useState, useEffect, useRef } from 'react';
import { Smartphone, Wifi, WifiOff, RefreshCw, CheckCircle2, X } from 'lucide-react';
import { createWhatsAppInstance, getInstanceQR, getInstanceStatus, logoutWhatsAppInstance } from '../../api/whatsappApi';
import { useAuth } from '../../context/AuthContext';
import toast from 'react-hot-toast';

/**
 * Modal for connecting a WhatsApp account via QR code scan.
 *
 * Flow:
 *  1. User clicks "Connect WhatsApp"
 *  2. Modal calls createWhatsAppInstance → gets initial QR code
 *  3. QR is displayed; user scans with WhatsApp > Linked Devices
 *  4. Polls getInstanceStatus every 5s until status === "open"
 *  5. On success, shows green checkmark and auto-closes
 */
export default function WhatsAppConnectModal({ onClose, onConnected }) {
  const { user } = useAuth();
  const instanceName = `rep_${user?.id}`;

  const [step, setStep] = useState('loading'); // loading | qr | connected | error
  const [qrCode, setQrCode] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const pollRef = useRef(null);

  async function initConnection() {
    setStep('loading');
    try {
      const status = await getInstanceStatus(instanceName);
      if (status.status === 'open') {
        setStep('connected');
        return;
      }

      const result = await createWhatsAppInstance(instanceName);
      if (result.qr_code) {
        setQrCode(result.qr_code);
        setStep('qr');
      } else {
        const qrResult = await getInstanceQR(instanceName);
        if (qrResult.qr_code) {
          setQrCode(qrResult.qr_code);
          setStep('qr');
        }
      }
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to initialize WhatsApp connection');
      setStep('error');
    }
  }

  // Create instance and fetch QR on mount
  useEffect(() => {
    initConnection();
  }, [instanceName]);

  // Poll for connection status while QR is displayed
  useEffect(() => {
    if (step !== 'qr') return;

    pollRef.current = setInterval(async () => {
      try {
        const result = await getInstanceStatus(instanceName);
        if (result.status === 'open') {
          clearInterval(pollRef.current);
          setStep('connected');
          toast.success('WhatsApp connected successfully!');
          if (onConnected) onConnected();
        }
      } catch {
        // Silently retry
      }
    }, 5000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [step, instanceName, onConnected]);

  const handleRefreshQR = () => {
    initConnection();
  };

  const handleDisconnect = async () => {
    if (!window.confirm("Are you sure you want to disconnect WhatsApp from the CRM?")) return;
    
    setIsDisconnecting(true);
    try {
      await logoutWhatsAppInstance();
      toast.success("Disconnected successfully");
      initConnection(); // Re-initialize to get a new QR code immediately
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to disconnect");
    } finally {
      setIsDisconnecting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }} onClick={onClose}>
      <div
        className="glass-card"
        style={{ width: '100%', maxWidth: 440, padding: 32, borderRadius: 16 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 10,
              background: 'rgba(37, 211, 102, 0.12)',
              border: '1px solid rgba(37, 211, 102, 0.25)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Smartphone size={20} color="#25D366" />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.05rem' }}>Connect WhatsApp</h3>
              <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                Scan QR with your phone
              </p>
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', padding: 4,
          }}>
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        {step === 'loading' && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <RefreshCw size={32} color="var(--primary)" className="spin" style={{ animation: 'spin 1s linear infinite' }} />
            <p style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              Initializing WhatsApp connection...
            </p>
          </div>
        )}

        {step === 'qr' && qrCode && (
          <div style={{ textAlign: 'center' }}>
            <div style={{
              background: '#fff', borderRadius: 12, padding: 16,
              display: 'inline-block', marginBottom: 16,
            }}>
              <img
                src={qrCode.startsWith('data:') ? qrCode : `data:image/png;base64,${qrCode}`}
                alt="WhatsApp QR Code"
                style={{ width: 240, height: 240, imageRendering: 'pixelated' }}
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
                <strong>Steps:</strong>
              </p>
              <ol style={{
                textAlign: 'left', fontSize: '0.82rem', color: 'var(--text-muted)',
                paddingLeft: 20, lineHeight: 1.8,
              }}>
                <li>Open WhatsApp on your phone</li>
                <li>Tap <strong>Settings → Linked Devices</strong></li>
                <li>Tap <strong>Link a Device</strong></li>
                <li>Point your phone camera at this QR code</li>
              </ol>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              <Wifi size={14} />
              <span>Waiting for scan...</span>
            </div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleRefreshQR}
              style={{ marginTop: 12, fontSize: '0.8rem' }}
            >
              <RefreshCw size={12} /> Refresh QR
            </button>
          </div>
        )}

        {step === 'connected' && (
          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            <CheckCircle2 size={56} color="var(--success)" />
            <h4 style={{ marginTop: 16, marginBottom: 4 }}>Connected!</h4>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: 20 }}>
              Your WhatsApp is now linked to the CRM. Messages will appear in your inbox.
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button 
                className="btn btn-ghost btn-sm" 
                style={{ color: 'var(--danger)' }}
                onClick={handleDisconnect}
                disabled={isDisconnecting}
              >
                {isDisconnecting ? "Disconnecting..." : "Disconnect"}
              </button>
              <button className="btn btn-primary btn-sm" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        )}

        {step === 'error' && (
          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            <WifiOff size={40} color="var(--danger)" />
            <p style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              {errorMsg}
            </p>
            <button className="btn btn-primary btn-sm" onClick={handleRefreshQR} style={{ marginTop: 16 }}>
              <RefreshCw size={12} /> Retry
            </button>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
