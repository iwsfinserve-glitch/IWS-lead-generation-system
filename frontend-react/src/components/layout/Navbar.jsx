import { useState, useEffect, useRef } from 'react';
import { Bell, CheckCheck, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { getNotifications, getUnreadCount, markNotificationRead, markAllRead } from '../../api/notificationsApi';

export default function Navbar({ title }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
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
    const interval = setInterval(fetchNotifs, 10000); // poll every 10 seconds for real-time updates
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
    if (!isOpen) {
      fetchNotifs();
    }
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
      // silent
    }
  };

  return (
    <header className="navbar">
      <span className="navbar-title">{title}</span>
      <div className="navbar-actions" style={{ position: 'relative' }} ref={dropdownRef}>
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
            style={{
              position: 'absolute',
              top: 'calc(100% + 8px)',
              right: 0,
              width: 340,
              maxHeight: 420,
              background: 'var(--bg-card-solid, #1e293b)',
              border: '1px solid var(--border, rgba(255,255,255,0.1))',
              borderRadius: 12,
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
              zIndex: 1000,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '12px 16px',
                borderBottom: '1px solid var(--border, rgba(255,255,255,0.1))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>
                Notifications {unreadCount > 0 && `(${unreadCount} unread)`}
              </div>
              {unreadCount > 0 && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={handleMarkAllRead}
                  style={{ fontSize: '0.75rem', padding: '2px 8px', display: 'flex', alignItems: 'center', gap: 4 }}
                >
                  <CheckCheck size={14} /> Mark all read
                </button>
              )}
            </div>

            <div style={{ overflowY: 'auto', flex: 1, padding: 8 }}>
              {notifications.length === 0 ? (
                <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
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
                      marginBottom: 4,
                      cursor: 'pointer',
                      background: notif.is_read ? 'transparent' : 'rgba(99, 102, 241, 0.12)',
                      borderLeft: notif.is_read ? '3px solid transparent' : '3px solid var(--primary, #6366f1)',
                      transition: 'background 0.2s',
                    }}
                  >
                    <div style={{ fontWeight: notif.is_read ? 600 : 700, fontSize: '0.85rem', marginBottom: 2 }}>
                      {notif.title}
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: 4 }}>
                      {notif.message}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {new Date(notif.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        <div style={{ width: 1, height: 24, background: 'var(--border)' }} />
        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          {user?.name}
        </div>
      </div>
    </header>
  );
}
