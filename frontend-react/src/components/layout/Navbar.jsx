import { useState, useEffect, useRef } from 'react';
import { Bell, CheckCheck, Menu, Moon, Sun, Trash2, X } from 'lucide-react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useAuth } from '../../context/AuthContext';
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllRead,
  deleteNotification,
  clearAllNotifications,
} from '../../api/notificationsApi';
import { useTheme } from '../../context/ThemeContext';

export default function Navbar({ title }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const outletCtx = useOutletContext?.() || {};
  const toggleSidebar = outletCtx.toggleSidebar;
  const { theme, toggleTheme } = useTheme();

  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const dropdownRef = useRef(null);

  const fetchNotifs = async () => {
    try {
      const [list, countData] = await Promise.all([
        getNotifications({ limit: 20 }).catch(() => []),
        getUnreadCount().catch(() => ({ count: 0 })),
      ]);
      setNotifications(list);
      setUnreadCount(countData.count || 0);
    } catch {
      // silent catch for background polling
    }
  };

  useEffect(() => {
    if (!user) return;
    fetchNotifs();
    const interval = setInterval(fetchNotifs, 10000); // poll every 10 seconds
    return () => clearInterval(interval);
  }, [user]);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleToggle = () => {
    if (!isOpen) fetchNotifs();
    setIsOpen(!isOpen);
  };

  const handleItemClick = async (notif) => {
    if (!notif.is_read) {
      try {
        await markNotificationRead(notif.id);
        setNotifications((prev) =>
          prev.map((n) => (n.id === notif.id ? { ...n, is_read: true } : n))
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch {
        // silent
      }
    }
    setIsOpen(false);
    if (notif.link_type === 'lead' && notif.link_id) {
      navigate(`/leads/${notif.link_id}`);
    } else if (notif.link_type === 'task') {
      navigate('/tasks');
    } else if (notif.link_type === 'appointment') {
      navigate('/appointments');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      toast.error('Failed to mark notifications as read');
    }
  };

  const handleClearAll = async (e) => {
    e?.stopPropagation();
    try {
      await clearAllNotifications();
      setNotifications([]);
      setUnreadCount(0);
      toast.success('All notifications cleared');
    } catch {
      toast.error('Failed to clear notifications');
    }
  };

  const handleDeleteOne = async (e, notifId) => {
    e.stopPropagation();
    try {
      await deleteNotification(notifId);
      const target = notifications.find((n) => n.id === notifId);
      setNotifications((prev) => prev.filter((n) => n.id !== notifId));
      if (target && !target.is_read) {
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
    } catch {
      toast.error('Failed to remove notification');
    }
  };

  return (
    <header className="navbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* Hamburger — only visible on mobile via CSS */}
        {toggleSidebar && (
          <button
            className="mobile-menu-btn"
            onClick={toggleSidebar}
            aria-label="Toggle navigation"
            id="mobile-menu-toggle"
          >
            <Menu size={20} />
          </button>
        )}
        <span className="navbar-title">{title}</span>
      </div>

      <div className="navbar-actions" style={{ position: 'relative' }} ref={dropdownRef}>
        <button
          className="btn btn-ghost btn-icon"
          onClick={toggleTheme}
          title="Toggle Theme"
        >
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>
        <button
          className="btn btn-ghost btn-icon"
          id="navbar-notifications-btn"
          title="Notifications"
          onClick={handleToggle}
          style={{ position: 'relative' }}
        >
          <Bell size={18} />
          {unreadCount > 0 && (
            <span
              style={{
                position: 'absolute',
                top: 4,
                right: 4,
                background: 'var(--danger)',
                color: '#fff',
                borderRadius: '50%',
                width: 16,
                height: 16,
                fontSize: '0.65rem',
                fontWeight: 800,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {isOpen && (
          <div
            className="notif-dropdown"
            style={{
              position: 'absolute',
              top: 'calc(100% + 8px)',
              right: 0,
              width: 380,
              maxWidth: 'calc(100vw - 24px)',
              maxHeight: 460,
              background: 'var(--bg-card-solid, #1e293b)',
              border: '1px solid var(--border, rgba(255,255,255,0.1))',
              borderRadius: 12,
              boxShadow: '0 10px 30px -5px rgba(0, 0, 0, 0.5)',
              zIndex: 1000,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              boxSizing: 'border-box',
            }}
          >
            <div
              style={{
                padding: '12px 14px',
                borderBottom: '1px solid var(--border, rgba(255,255,255,0.1))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                flexWrap: 'nowrap',
                boxSizing: 'border-box',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                <span style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                  Notifications
                </span>
                {unreadCount > 0 && (
                  <span
                    style={{
                      background: 'rgba(99, 102, 241, 0.15)',
                      color: 'var(--primary, #6366f1)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      padding: '1px 6px',
                      borderRadius: 10,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {unreadCount} unread
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={handleMarkAllRead}
                    title="Mark all as read"
                    style={{
                      fontSize: '0.75rem',
                      padding: '3px 8px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      whiteSpace: 'nowrap',
                      height: 'auto',
                      minHeight: '26px',
                    }}
                  >
                    <CheckCheck size={13} /> Mark read
                  </button>
                )}
                {notifications.length > 0 && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={handleClearAll}
                    id="clear-all-notifications-btn"
                    title="Clear all notifications"
                    style={{
                      fontSize: '0.75rem',
                      padding: '3px 8px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      color: 'var(--danger, #ef4444)',
                      whiteSpace: 'nowrap',
                      height: 'auto',
                      minHeight: '26px',
                    }}
                  >
                    <Trash2 size={13} /> Clear all
                  </button>
                )}
              </div>
            </div>

            <div
              style={{
                overflowY: 'auto',
                flex: 1,
                padding: '8px 10px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              {notifications.length === 0 ? (
                <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  No notifications yet
                </div>
              ) : (
                notifications.map((notif) => (
                  <div
                    key={notif.id}
                    onClick={() => handleItemClick(notif)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      background: notif.is_read ? 'rgba(255, 255, 255, 0.02)' : 'rgba(99, 102, 241, 0.12)',
                      borderLeft: notif.is_read ? '3px solid transparent' : '3px solid var(--primary, #6366f1)',
                      borderTop: '1px solid var(--border, rgba(255,255,255,0.05))',
                      borderRight: '1px solid var(--border, rgba(255,255,255,0.05))',
                      borderBottom: '1px solid var(--border, rgba(255,255,255,0.05))',
                      transition: 'all 0.15s ease',
                      boxSizing: 'border-box',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        justifyContent: 'space-between',
                        gap: 8,
                        marginBottom: 4,
                      }}
                    >
                      <div
                        style={{
                          fontWeight: notif.is_read ? 600 : 700,
                          fontSize: '0.85rem',
                          color: 'var(--text-primary)',
                          wordBreak: 'break-word',
                          overflowWrap: 'break-word',
                          flex: 1,
                          minWidth: 0,
                          lineHeight: 1.35,
                        }}
                      >
                        {notif.title}
                      </div>
                      <button
                        type="button"
                        onClick={(e) => handleDeleteOne(e, notif.id)}
                        title="Dismiss notification"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--text-muted, #94a3b8)',
                          cursor: 'pointer',
                          padding: 2,
                          width: 20,
                          height: 20,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          borderRadius: 4,
                          flexShrink: 0,
                          marginTop: -2,
                          marginRight: -4,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = 'var(--danger, #ef4444)';
                          e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = 'var(--text-muted, #94a3b8)';
                          e.currentTarget.style.background = 'transparent';
                        }}
                      >
                        <X size={14} />
                      </button>
                    </div>
                    <div
                      style={{
                        fontSize: '0.78rem',
                        color: 'var(--text-secondary)',
                        marginBottom: 6,
                        wordBreak: 'break-word',
                        overflowWrap: 'break-word',
                        lineHeight: 1.4,
                      }}
                    >
                      {notif.message}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {new Date(notif.created_at).toLocaleString([], {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        <div style={{ width: 1, height: 24, background: 'rgba(255,255,255,0.2)' }} />
        <div style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.8)', whiteSpace: 'nowrap', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {user?.name}
        </div>
      </div>
    </header>
  );
}
