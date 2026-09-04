import { useState, useEffect, useMemo } from 'react';
import { MessageCircle, Search, Phone, RefreshCw, X, User } from 'lucide-react';
import { getLeadsWithoutChats, syncChatHistory } from '../../api/whatsappApi';
import toast from 'react-hot-toast';

/**
 * StartChatModal
 *
 * Shows a searchable list of all CRM leads that have no WhatsApp conversation yet.
 * The user can select a lead and either:
 *   (a) "Sync History" — import past messages from WhatsApp into the CRM, or
 *   (b) "Start Fresh" — open the chat pane empty so they can send the first message.
 *
 * Props:
 *   onClose()              — close the modal without doing anything
 *   onChatReady(leadId)    — called when the chat is ready to open (lead selected + synced)
 */
export default function StartChatModal({ onClose, onChatReady }) {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLead, setSelectedLead] = useState(null);
  const [syncing, setSyncing] = useState(false);

  // Fetch leads without chats on mount
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getLeadsWithoutChats();
        if (!cancelled) setLeads(data);
      } catch {
        toast.error('Could not load leads');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return leads;
    return leads.filter(
      (l) =>
        l.name.toLowerCase().includes(q) ||
        (l.phone_number || '').includes(q)
    );
  }, [leads, searchQuery]);

  const handleAddChat = async () => {
    if (!selectedLead) return;
    setSyncing(true);
    try {
      const result = await syncChatHistory(selectedLead.id);
      const count = result.imported ?? 0;
      if (count > 0) {
        toast.success(`✅ Imported ${count} message${count !== 1 ? 's' : ''} from WhatsApp!`);
      } else {
        toast(`Starting chat with ${selectedLead.name}`, { icon: '💬' });
      }
      onChatReady(selectedLead.id, selectedLead);
    } catch (err) {
      // Even if sync fails, still open the chat — messages will come via webhook
      toast.error(err.response?.data?.detail || 'Could not fetch history, but chat is ready');
      onChatReady(selectedLead.id, selectedLead);
    } finally {
      setSyncing(false);
    }
  };

  const statusColor = {
    new: '#6366f1',
    contacted: '#f59e0b',
    qualified: '#10b981',
    converted: '#25D366',
    lost: '#ef4444',
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      onClick={onClose}
    >
      <div
        className="glass-card"
        style={{ width: '100%', maxWidth: 520, borderRadius: 16, padding: 0, overflow: 'hidden' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10,
              background: 'rgba(37, 211, 102, 0.12)',
              border: '1px solid rgba(37, 211, 102, 0.25)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <MessageCircle size={18} color="#25D366" />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1rem' }}>Start a Chat</h3>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Select a lead to open or sync their WhatsApp history
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Search */}
        <div style={{
          padding: '12px 24px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'rgba(0,0,0,0.1)',
        }}>
          <Search size={14} color="var(--text-muted)" />
          <input
            type="text"
            placeholder="Search leads by name or phone..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            autoFocus
            id="start-chat-search"
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              color: 'var(--text-primary)', fontSize: '0.875rem',
            }}
          />
        </div>

        {/* Lead List */}
        <div style={{ maxHeight: 320, overflowY: 'auto' }}>
          {loading ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite', marginBottom: 8, display: 'block', margin: '0 auto 8px' }} />
              Loading leads...
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
              <User size={36} style={{ opacity: 0.3, marginBottom: 8 }} />
              <p style={{ fontSize: '0.85rem', margin: 0 }}>
                {leads.length === 0
                  ? 'All your leads already have WhatsApp conversations!'
                  : 'No leads match your search'}
              </p>
            </div>
          ) : (
            filtered.map((lead) => {
              const isSelected = selectedLead?.id === lead.id;
              const dot = statusColor[lead.status] || 'var(--text-muted)';
              return (
                <div
                  key={lead.id}
                  id={`start-chat-lead-${lead.id}`}
                  onClick={() => setSelectedLead(lead)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 24px',
                    cursor: 'pointer',
                    background: isSelected ? 'rgba(37, 211, 102, 0.08)' : 'transparent',
                    borderLeft: isSelected ? '3px solid #25D366' : '3px solid transparent',
                    transition: 'background 0.15s',
                  }}
                >
                  {/* Avatar */}
                  <div style={{
                    width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
                    background: isSelected
                      ? 'rgba(37,211,102,0.18)'
                      : 'rgba(99,102,241,0.12)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontWeight: 700, fontSize: '0.95rem',
                    color: isSelected ? '#25D366' : 'var(--primary)',
                    border: isSelected ? '1.5px solid rgba(37,211,102,0.4)' : '1.5px solid rgba(99,102,241,0.2)',
                  }}>
                    {lead.name.charAt(0).toUpperCase()}
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                      {lead.name}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                      <Phone size={11} color="var(--text-muted)" />
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        {lead.phone_number}
                      </span>
                      {lead.status && (
                        <>
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>·</span>
                          <span style={{
                            fontSize: '0.7rem', fontWeight: 600, textTransform: 'capitalize',
                            color: dot,
                          }}>
                            {lead.status.replace(/_/g, ' ')}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {isSelected && (
                    <div style={{
                      width: 18, height: 18, borderRadius: '50%',
                      background: '#25D366',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                        <path d="M2 5l2 2 4-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Action Footer */}
        {selectedLead && (
          <div style={{
            padding: '16px 24px',
            borderTop: '1px solid var(--border)',
            background: 'rgba(37,211,102,0.04)',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Selected:</div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#25D366' }}>
                {selectedLead.name}
              </div>
            </div>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleAddChat}
              disabled={syncing}
              id="start-chat-add-btn"
              style={{
                background: '#25D366', borderColor: '#25D366',
                display: 'flex', alignItems: 'center', gap: 6,
                fontSize: '0.8rem',
              }}
            >
              {syncing ? (
                <><RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} /> Adding...</>
              ) : (
                <><MessageCircle size={12} /> Add Chat</>
              )}
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
