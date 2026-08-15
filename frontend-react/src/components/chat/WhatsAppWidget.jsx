import { useState, useEffect, useRef, useCallback } from 'react';
import {
  MessageCircle, Send, X, Minimize2, Maximize2,
  ChevronRight, CheckCheck, ArrowLeft
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { getWhatsAppChats, getChatMessages, sendWhatsAppMessage } from '../../api/whatsappApi';
import toast from 'react-hot-toast';

/**
 * Floating WhatsApp chat widget — bottom-right corner of every page.
 *
 * Has 3 states:
 *  1. Collapsed (just a green FAB button with unread badge)
 *  2. Chat list (mini contact list)
 *  3. Active chat (message thread with input)
 */
export default function WhatsAppWidget() {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [view, setView] = useState('list'); // list | chat
  const [chats, setChats] = useState([]);
  const [selectedLeadId, setSelectedLeadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [totalUnread, setTotalUnread] = useState(0);

  const messagesEndRef = useRef(null);
  const pollRef = useRef(null);
  const msgPollRef = useRef(null);

  // ── Load chats ─────────────────────────────────────────────────────
  const loadChats = useCallback(async () => {
    try {
      const data = await getWhatsAppChats();
      setChats(data);
      const unread = data.reduce((sum, c) => sum + (c.unread_count || 0), 0);
      setTotalUnread(unread);
    } catch {
      // Silent
    }
  }, []);

  // Poll for new chats
  useEffect(() => {
    loadChats();
    pollRef.current = setInterval(loadChats, 20000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadChats]);

  // ── Load messages ─────────────────────────────────────────────────
  const loadMessages = useCallback(async () => {
    if (!selectedLeadId) return;
    try {
      const data = await getChatMessages(selectedLeadId);
      setMessages(data);
    } catch {
      // Silent
    }
  }, [selectedLeadId]);

  useEffect(() => {
    if (selectedLeadId && view === 'chat') {
      loadMessages();
      msgPollRef.current = setInterval(loadMessages, 5000);
    }
    return () => { if (msgPollRef.current) clearInterval(msgPollRef.current); };
  }, [selectedLeadId, view, loadMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Send message ──────────────────────────────────────────────────
  const handleSend = async (e) => {
    e.preventDefault();
    if (!newMessage.trim() || !selectedLeadId || sending) return;
    setSending(true);
    try {
      const sentMsg = await sendWhatsAppMessage(selectedLeadId, newMessage.trim());
      setMessages((prev) => [...prev, sentMsg]);
      setNewMessage('');
      loadChats();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send');
    } finally {
      setSending(false);
    }
  };

  const handleSelectChat = (leadId) => {
    setSelectedLeadId(leadId);
    setView('chat');
  };

  const handleBack = () => {
    setView('list');
    setSelectedLeadId(null);
  };

  const selectedChat = chats.find((c) => c.lead_id === selectedLeadId);

  const formatTime = (ts) => {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  // Don't render on login page or if no user
  if (!user) return null;

  return (
    <>
      {/* ── FAB Button ── */}
      {!isOpen && (
        <button
          className="wa-widget-fab"
          onClick={() => setIsOpen(true)}
          id="wa-widget-fab"
          title="WhatsApp"
        >
          <MessageCircle size={24} />
          {totalUnread > 0 && (
            <span className="wa-widget-badge">{totalUnread > 9 ? '9+' : totalUnread}</span>
          )}
        </button>
      )}

      {/* ── Widget Panel ── */}
      {isOpen && (
        <div className="wa-widget-panel">
          {/* Header */}
          <div className="wa-widget-header">
            {view === 'chat' && (
              <button onClick={handleBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#fff', marginRight: 6, display: 'flex' }}>
                <ArrowLeft size={16} />
              </button>
            )}
            <MessageCircle size={16} />
            <span style={{ fontWeight: 600, fontSize: '0.85rem', flex: 1 }}>
              {view === 'chat' && selectedChat ? selectedChat.lead_name : 'WhatsApp'}
            </span>
            <button onClick={() => setIsOpen(false)} style={{
              background: 'none', border: 'none', cursor: 'pointer', color: '#fff',
              display: 'flex', padding: 2,
            }}>
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="wa-widget-body">
            {view === 'list' ? (
              /* ── Chat List View ── */
              chats.length === 0 ? (
                <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                  No conversations yet
                </div>
              ) : (
                chats.slice(0, 10).map((chat) => (
                  <div
                    key={chat.lead_id}
                    className="wa-widget-chat-item"
                    onClick={() => handleSelectChat(chat.lead_id)}
                  >
                    <div className="wa-widget-chat-avatar">
                      {chat.lead_name.charAt(0).toUpperCase()}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 500, fontSize: '0.82rem' }}>{chat.lead_name}</span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{formatTime(chat.last_message_time)}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 2 }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>
                          {chat.last_message || 'No messages'}
                        </span>
                        {chat.unread_count > 0 && (
                          <span className="wa-unread-badge" style={{ fontSize: '0.65rem', minWidth: 16, height: 16 }}>
                            {chat.unread_count}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )
            ) : (
              /* ── Chat Thread View ── */
              <>
                <div className="wa-widget-messages">
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`wa-message-bubble ${msg.direction === 'outbound' ? 'outbound' : 'inbound'}`}
                      style={{ marginBottom: 6 }}
                    >
                      <div className="wa-bubble-content" style={{ maxWidth: '85%', padding: '6px 10px' }}>
                        <p className="wa-bubble-text" style={{ fontSize: '0.8rem' }}>{msg.content || '[Media]'}</p>
                        <span className="wa-bubble-time" style={{ fontSize: '0.65rem' }}>
                          {formatTime(msg.timestamp)}
                          {msg.direction === 'outbound' && <CheckCheck size={10} style={{ marginLeft: 2 }} />}
                        </span>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
                <form className="wa-widget-input" onSubmit={handleSend}>
                  <input
                    type="text"
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    placeholder="Type a message..."
                    disabled={sending}
                    style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontSize: '0.82rem', color: 'var(--text-primary)' }}
                  />
                  <button type="submit" disabled={!newMessage.trim() || sending} style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: newMessage.trim() ? '#25D366' : 'var(--text-muted)',
                    display: 'flex', padding: 4,
                  }}>
                    <Send size={16} />
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
