import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  MessageCircle, Send, Search, Phone, User, ArrowLeft,
  Wifi, WifiOff, Settings, ChevronRight, Clock, CheckCheck, Plus, Trash2, RefreshCw
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getWhatsAppChats, getChatMessages, sendWhatsAppMessage, getInstanceStatus, deleteWhatsAppChat, syncChatHistory } from '../api/whatsappApi';
import { getLead } from '../api/leadsApi';
import WhatsAppConnectModal from '../components/modals/WhatsAppConnectModal';
import StartChatModal from '../components/modals/StartChatModal';
import Navbar from '../components/layout/Navbar';
import toast from 'react-hot-toast';

/**
 * Full-page WhatsApp Inbox — split-pane chat interface.
 *
 * Left panel:  Contact list (leads with WhatsApp conversations)
 * Right panel: Chat thread with message input
 */
export default function WhatsAppInbox() {
  const { toggleSidebar } = useOutletContext();
  const { user } = useAuth();
  const instanceName = `rep_${user?.id}`;

  // ── State ──────────────────────────────────────────────────────────
  const [chats, setChats] = useState([]);
  const [selectedLeadId, setSelectedLeadId] = useState(null);
  const [activeLead, setActiveLead] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('checking'); // checking | open | close
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [showStartChatModal, setShowStartChatModal] = useState(false);
  const [mobileShowChat, setMobileShowChat] = useState(false);

  const messagesEndRef = useRef(null);
  const chatPollRef = useRef(null);
  const msgPollRef = useRef(null);
  const autoSyncedLeadRef = useRef(null);

  // ── Load chats ─────────────────────────────────────────────────────
  const loadChats = useCallback(async () => {
    try {
      const data = await getWhatsAppChats();
      setChats(data);
    } catch {
      // Silent — chats may be empty
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Check connection status ────────────────────────────────────────
  useEffect(() => {
    async function checkStatus() {
      try {
        const result = await getInstanceStatus(instanceName);
        setConnectionStatus(result.status === 'open' ? 'open' : 'close');
      } catch {
        setConnectionStatus('close');
      }
    }
    checkStatus();
  }, [instanceName]);

  // ── Initial load + polling ─────────────────────────────────────────
  useEffect(() => {
    loadChats();
    chatPollRef.current = setInterval(loadChats, 15000); // Refresh chat list every 15s
    return () => {
      if (chatPollRef.current) clearInterval(chatPollRef.current);
    };
  }, [loadChats]);

  // ── Load messages for selected lead ────────────────────────────────
  const loadMessages = useCallback(async () => {
    if (!selectedLeadId) return;
    try {
      const data = await getChatMessages(selectedLeadId);
      setMessages(data);
    } catch (err) {
      toast.error('Failed to load messages');
    }
  }, [selectedLeadId]);

  useEffect(() => {
    if (selectedLeadId) {
      loadMessages();
      // Poll for new messages every 3s when a chat is open
      msgPollRef.current = setInterval(loadMessages, 3000);
    }
    return () => {
      if (msgPollRef.current) clearInterval(msgPollRef.current);
    };
  }, [selectedLeadId, loadMessages]);

  // ── Auto-scroll to bottom ─────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Send message ──────────────────────────────────────────────────
  const handleSend = async (e) => {
    e.preventDefault();
    if (!newMessage.trim() || !selectedLeadId || sending) return;

    const messageText = newMessage.trim();
    setSending(true);

    // Optimistic UI: show message instantly before API confirms
    const optimisticMsg = {
      id: `optimistic_${Date.now()}`,
      direction: 'outbound',
      content: messageText,
      timestamp: new Date().toISOString(),
      status: 'sending',
    };
    setMessages((prev) => [...prev, optimisticMsg]);
    setNewMessage('');

    try {
      const sentMsg = await sendWhatsAppMessage(selectedLeadId, messageText);
      // Replace optimistic message with real one
      setMessages((prev) =>
        prev.map((m) => (m.id === optimisticMsg.id ? sentMsg : m))
      );
      // Refresh chat list to update last message preview
      loadChats();
    } catch (err) {
      // Remove optimistic message on failure
      setMessages((prev) => prev.filter((m) => m.id !== optimisticMsg.id));
      setNewMessage(messageText); // Restore the message text
      toast.error(err.response?.data?.detail || 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  // ── Select a chat ─────────────────────────────────────────────────
  const handleSelectChat = (leadId, leadData = null) => {
    setSelectedLeadId(leadId);
    setMobileShowChat(true);
    if (leadData) {
      setActiveLead({
        lead_id: leadData.id || leadId,
        lead_name: leadData.name,
        lead_phone: leadData.phone_number,
        lead_status: leadData.status,
      });
    }
  };

  // If a lead is selected that isn't in `chats` yet (e.g., 0 messages), fetch lead details
  useEffect(() => {
    if (selectedLeadId && !chats.some((c) => c.lead_id === selectedLeadId)) {
      if (!activeLead || activeLead.lead_id !== selectedLeadId) {
        getLead(selectedLeadId)
          .then((l) => {
            if (l) {
              setActiveLead({
                lead_id: l.id,
                lead_name: l.name,
                lead_phone: l.phone_number,
                lead_status: l.status,
              });
            }
          })
          .catch(() => {});
      }
    }
  }, [selectedLeadId, chats, activeLead]);

  const handleBackToList = () => {
    setMobileShowChat(false);
  };

  // ── Delete chat ───────────────────────────────────────────────────
  const handleDeleteChat = async () => {
    if (!selectedLeadId) return;
    if (!window.confirm('Are you sure you want to delete this chat from the CRM?')) return;
    
    try {
      await deleteWhatsAppChat(selectedLeadId);
      toast.success('Chat deleted');
      setSelectedLeadId(null);
      setActiveLead(null);
      setMobileShowChat(false);
      loadChats();
    } catch (err) {
      toast.error('Failed to delete chat');
    }
  };

  // ── Sync Chat History ───────────────────────────────────────────────
  const [syncing, setSyncing] = useState(false);

  const handleSyncChat = async (silent = false) => {
    if (!selectedLeadId || syncing) return;
    
    setSyncing(true);
    const loadingToast = silent ? null : toast.loading('Syncing messages...');
    try {
      const res = await syncChatHistory(selectedLeadId);
      if (!silent) {
        if (res.imported > 0) {
          toast.success(`Synced ${res.imported} message(s)!`, { id: loadingToast });
        } else if (res.total > 0) {
          toast.success(`Chat is up to date (${res.total} messages)`, { id: loadingToast });
        } else {
          toast.success('No message history found on WhatsApp', { id: loadingToast });
        }
      } else if (loadingToast) {
        toast.dismiss(loadingToast);
      }
      await loadMessages();
      await loadChats();
    } catch (err) {
      if (!silent) {
        toast.error(err.response?.data?.detail || 'Failed to sync chat history', { id: loadingToast });
      }
    } finally {
      setSyncing(false);
    }
  };

  // ── Auto-sync when opening a chat with 0 messages (guarded to run once per lead) ──
  useEffect(() => {
    if (
      selectedLeadId &&
      messages.length === 0 &&
      !syncing &&
      connectionStatus === 'open' &&
      autoSyncedLeadRef.current !== selectedLeadId
    ) {
      autoSyncedLeadRef.current = selectedLeadId;
      handleSyncChat(true); // silent sync
    }
  }, [selectedLeadId, messages.length, connectionStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Displayed chats (includes active newly added chat even before first message) ──
  const displayedChats = useMemo(() => {
    if (activeLead && !chats.some((c) => c.lead_id === activeLead.lead_id)) {
      return [
        {
          lead_id: activeLead.lead_id,
          lead_name: activeLead.lead_name,
          lead_phone: activeLead.lead_phone,
          lead_status: activeLead.lead_status,
          last_message: 'No messages yet',
          last_message_time: new Date().toISOString(),
          unread_count: 0,
          direction: null,
        },
        ...chats,
      ];
    }
    return chats;
  }, [chats, activeLead]);

  // ── Filter chats by search ────────────────────────────────────────
  const filteredChats = displayedChats.filter((c) =>
    (c.lead_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    (c.lead_phone || '').includes(searchQuery)
  );

  const selectedChat = displayedChats.find((c) => c.lead_id === selectedLeadId) || (activeLead?.lead_id === selectedLeadId ? activeLead : null);

  // ── Format timestamp ──────────────────────────────────────────────
  const formatTime = (ts) => {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const formatMessageTime = (ts) => {
    if (!ts) return '';
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <>
      <Navbar title="WhatsApp" onMenuClick={toggleSidebar} />

      <div className="wa-inbox-container">
        {/* ── Left Panel: Chat List ── */}
        <div className={`wa-chat-list ${mobileShowChat ? 'wa-hide-mobile' : ''}`}>
          {/* Status Bar + New Chat Button */}
          <div className="wa-status-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {connectionStatus === 'open' ? (
                <><Wifi size={14} color="var(--success)" /><span style={{ color: 'var(--success)', fontSize: '0.78rem' }}>Connected</span></>
              ) : (
                <><WifiOff size={14} color="var(--danger)" /><span style={{ color: 'var(--danger)', fontSize: '0.78rem' }}>Disconnected</span></>
              )}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowStartChatModal(true)}
                style={{ padding: '4px 8px', fontSize: '0.75rem', color: '#25D366', borderColor: 'rgba(37,211,102,0.3)' }}
                id="wa-new-chat-btn"
                title="Start a new chat with a lead"
              >
                <Plus size={12} /> New Chat
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowConnectModal(true)}
                style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                id="wa-connect-btn"
              >
                <Settings size={12} /> {connectionStatus === 'open' ? 'Manage' : 'Connect'}
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="wa-search-box">
            <Search size={14} color="var(--text-muted)" />
            <input
              type="text"
              placeholder="Search contacts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="wa-search-input"
              id="wa-search-input"
            />
          </div>

          {/* Chat items */}
          <div className="wa-chat-items">
            {loading ? (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Loading chats...
              </div>
            ) : filteredChats.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
                <MessageCircle size={36} style={{ opacity: 0.3, marginBottom: 8 }} />
                <p style={{ fontSize: '0.85rem', margin: 0 }}>No WhatsApp conversations yet</p>
                <p style={{ fontSize: '0.78rem', margin: '4px 0 0' }}>
                  {connectionStatus === 'open'
                    ? 'Messages from your leads will appear here'
                    : 'Connect your WhatsApp to get started'}
                </p>
              </div>
            ) : (
              filteredChats.map((chat) => (
                <div
                  key={chat.lead_id}
                  className={`wa-chat-item ${selectedLeadId === chat.lead_id ? 'active' : ''}`}
                  onClick={() => handleSelectChat(chat.lead_id)}
                  id={`wa-chat-${chat.lead_id}`}
                >
                  <div className="wa-chat-avatar">
                    {chat.lead_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="wa-chat-info">
                    <div className="wa-chat-header">
                      <span className="wa-chat-name">{chat.lead_name}</span>
                      <span className="wa-chat-time">{formatTime(chat.last_message_time)}</span>
                    </div>
                    <div className="wa-chat-preview">
                      <span className="wa-chat-last-msg">
                        {chat.direction === 'outbound' && <CheckCheck size={12} style={{ marginRight: 3, opacity: 0.5 }} />}
                        {chat.last_message || 'No messages'}
                      </span>
                      {chat.unread_count > 0 && (
                        <span className="wa-unread-badge">{chat.unread_count}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Right Panel: Chat Thread ── */}
        <div className={`wa-chat-thread ${mobileShowChat ? 'wa-show-mobile' : ''}`}>
          {selectedLeadId && selectedChat ? (
            <>
              {/* Chat Header */}
              <div className="wa-thread-header">
                <button className="wa-back-btn" onClick={handleBackToList}>
                  <ArrowLeft size={18} />
                </button>
                <div className="wa-chat-avatar" style={{ width: 36, height: 36, fontSize: '0.85rem' }}>
                  {selectedChat.lead_name.charAt(0).toUpperCase()}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{selectedChat.lead_name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    <Phone size={10} style={{ marginRight: 3 }} />
                    {selectedChat.lead_phone}
                    {selectedChat.lead_status && (
                      <span className="wa-status-pill">{selectedChat.lead_status.replace(/_/g, ' ')}</span>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    className="btn btn-ghost"
                    onClick={handleSyncChat}
                    style={{ padding: '6px 8px', color: 'var(--text-primary)' }}
                    title="Manual sync messages"
                  >
                    <RefreshCw size={16} />
                  </button>
                  <button
                    className="btn btn-ghost"
                    onClick={handleDeleteChat}
                    style={{ padding: '6px 8px', color: 'var(--danger)' }}
                    title="Delete chat from CRM"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              {/* Messages */}
              <div className="wa-messages-area">
                {messages.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    <MessageCircle size={40} style={{ opacity: 0.2, marginBottom: 8 }} />
                    <p style={{ fontSize: '0.85rem' }}>No messages yet. Start a conversation!</p>
                  </div>
                ) : (
                  messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`wa-message-bubble ${msg.direction === 'outbound' ? 'outbound' : 'inbound'}`}
                    >
                      <div className="wa-bubble-content">
                        {msg.media_type && (
                          <div className="wa-media-badge">
                            📎 {msg.media_type}
                          </div>
                        )}
                        <p className="wa-bubble-text">{msg.content || '[Media]'}</p>
                        <span className="wa-bubble-time">
                          {formatMessageTime(msg.timestamp)}
                          {msg.direction === 'outbound' && (
                            <CheckCheck size={12} style={{ marginLeft: 3, color: msg.status === 'read' ? '#53bdeb' : 'inherit' }} />
                          )}
                        </span>
                      </div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Message Input */}
              <form className="wa-input-bar" onSubmit={handleSend}>
                <input
                  type="text"
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  placeholder="Type a message..."
                  className="wa-message-input"
                  disabled={sending || connectionStatus !== 'open'}
                  id="wa-message-input"
                />
                <button
                  type="submit"
                  className="wa-send-btn"
                  disabled={!newMessage.trim() || sending || connectionStatus !== 'open'}
                  id="wa-send-btn"
                >
                  <Send size={18} />
                </button>
              </form>
            </>
          ) : (
            <div className="wa-empty-state">
              <div className="wa-empty-icon">
                <MessageCircle size={56} />
              </div>
              <h3 style={{ margin: '16px 0 6px' }}>WhatsApp Inbox</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', maxWidth: 320 }}>
                Select a conversation from the left panel to view messages, or wait for your leads to message you.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Connect Modal */}
      {showConnectModal && (
        <WhatsAppConnectModal
          onClose={() => setShowConnectModal(false)}
          onConnected={() => {
            setConnectionStatus('open');
            loadChats();
          }}
        />
      )}

      {/* Start Chat Modal */}
      {showStartChatModal && (
        <StartChatModal
          onClose={() => setShowStartChatModal(false)}
          onChatReady={async (leadId, leadData) => {
            setShowStartChatModal(false);
            await loadChats();
            handleSelectChat(leadId, leadData);
          }}
        />
      )}
    </>
  );
}
