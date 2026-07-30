import { useState, useEffect } from 'react';
import { Mail, Send, Calendar, Clock, X, ExternalLink } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import { getLeads } from '../api/leadsApi';
import { sendEmailToLead, getEmailHistory } from '../api/emailsApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import { getGoogleStatus, getGoogleConnectUrl } from '../api/authApi';
import Modal from '../components/common/Modal';

export default function EmailLeadsPage() {
  const { user } = useAuth();
  const [leads, setLeads] = useState([]);
  const [selectedLeadId, setSelectedLeadId] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [selectedHistoryItem, setSelectedHistoryItem] = useState(null);

  const [googleStatus, setGoogleStatus] = useState({ google_connected: false });
  const [loadingGoogle, setLoadingGoogle] = useState(true);

  useEffect(() => {
    if (user?.id) {
      getLeads({ assigned_rep_id: user.id, limit: 1000 })
        .then(setLeads)
        .catch(() => toast.error('Failed to load leads'));
        
      getGoogleStatus()
        .then(setGoogleStatus)
        .catch(() => setGoogleStatus({ google_connected: false }))
        .finally(() => setLoadingGoogle(false));
    }
  }, [user?.id]);

  useEffect(() => {
    if (selectedLeadId) {
      setLoadingHistory(true);
      getEmailHistory(selectedLeadId)
        .then(setHistory)
        .catch(() => toast.error('Failed to load email history'))
        .finally(() => setLoadingHistory(false));
    } else {
      setHistory([]);
    }
  }, [selectedLeadId]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!selectedLeadId || !subject.trim() || !body.trim() || !googleStatus.google_connected) return;

    setSending(true);
    try {
      await sendEmailToLead({
        lead_id: parseInt(selectedLeadId),
        subject: subject.trim(),
        body: body.trim(),
      });
      toast.success('Email sent successfully!');
      setSubject('');
      setBody('');
      // Refresh history
      const newHistory = await getEmailHistory(selectedLeadId);
      setHistory(newHistory);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send email');
    } finally {
      setSending(false);
    }
  };

  const handleGoogleConnect = async () => {
    try {
      const url = await getGoogleConnectUrl();
      window.location.href = url;
    } catch { toast.error('Failed to start Google auth'); }
  };

  const isFormValid = selectedLeadId && subject.trim() && body.trim();

  return (
    <>
      <Navbar title="Email Leads" />
      <div className="page-container">
        
        {/* Compose Section */}
        <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
            <Mail size={20} className="text-primary" />
            Compose Email
          </h2>
          
          <form onSubmit={handleSend}>
            <div className="form-group">
              <label className="form-label">Select Lead *</label>
              <select 
                className="form-select" 
                value={selectedLeadId} 
                onChange={(e) => setSelectedLeadId(e.target.value)}
                disabled={sending}
              >
                <option value="">-- Choose a Lead --</option>
                {leads.map(lead => (
                  <option key={lead.id} value={lead.id}>
                    {lead.name} {lead.email ? `(${lead.email})` : '(No Email)'}
                  </option>
                ))}
              </select>
            </div>
            
            <div className="form-group">
              <label className="form-label">Subject *</label>
              <input 
                className="form-input" 
                type="text" 
                placeholder="Email Subject" 
                value={subject} 
                onChange={(e) => setSubject(e.target.value)}
                disabled={sending}
              />
            </div>
            
            <div className="form-group">
              <label className="form-label">Message *</label>
              <textarea 
                className="form-input" 
                rows="6" 
                placeholder="Write your email here..." 
                value={body} 
                onChange={(e) => setBody(e.target.value)}
                disabled={sending}
                style={{ resize: 'vertical' }}
              />
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
              {loadingGoogle ? (
                <button type="button" className="btn btn-primary" disabled>
                  Loading...
                </button>
              ) : !googleStatus.google_connected ? (
                <button 
                  type="button" 
                  className="btn btn-secondary" 
                  onClick={handleGoogleConnect}
                >
                  <ExternalLink size={16} />
                  Connect Google Workspace to Send Emails
                </button>
              ) : (
                <button 
                  type="submit" 
                  className="btn btn-primary" 
                  disabled={!isFormValid || sending}
                >
                  <Send size={16} />
                  {sending ? 'Sending...' : 'Send Email'}
                </button>
              )}
            </div>
          </form>
        </div>

        {/* History Section */}
        {selectedLeadId && (
          <div>
            <h3 style={{ marginBottom: 16 }}>Email History</h3>
            {loadingHistory ? (
              <div className="loading-center"><div className="spinner spinner-md" /></div>
            ) : history.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-title">No emails sent to this lead yet.</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {history.map(item => (
                  <div 
                    key={item.id} 
                    className="glass-card" 
                    style={{ padding: '16px', cursor: 'pointer', transition: 'transform 0.2s' }}
                    onClick={() => setSelectedHistoryItem(item)}
                    onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-2px)'}
                    onMouseLeave={(e) => e.currentTarget.style.transform = 'none'}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 8, fontSize: '1.05rem' }}>{item.subject}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Calendar size={14} /> {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Clock size={14} /> {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      <span>To: {item.sent_to}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* History Detail Modal */}
      {selectedHistoryItem && (
        <Modal title="Email Details" onClose={() => setSelectedHistoryItem(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 4 }}>Subject</div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{selectedHistoryItem.subject}</div>
            </div>
            <div style={{ display: 'flex', gap: 24 }}>
              <div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 4 }}>Sent To</div>
                <div>{selectedHistoryItem.sent_to}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 4 }}>Date & Time</div>
                <div>{new Date(selectedHistoryItem.created_at).toLocaleString()}</div>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 8 }}>Message Body</div>
              <div style={{ 
                padding: '16px', 
                background: 'var(--bg)', 
                borderRadius: '8px',
                whiteSpace: 'pre-wrap',
                border: '1px solid var(--border)'
              }}>
                {selectedHistoryItem.body}
              </div>
            </div>
          </div>
          <div className="modal-footer" style={{ marginTop: 24 }}>
            <button className="btn btn-primary" onClick={() => setSelectedHistoryItem(null)}>Close</button>
          </div>
        </Modal>
      )}
    </>
  );
}
