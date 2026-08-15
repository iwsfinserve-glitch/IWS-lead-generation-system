import { NavLink, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import {
  LayoutDashboard, Users, Users2, Target, Calendar, CheckSquare,
  BarChart3, LogOut, X, FileEdit, Mail, ChevronRight, MessageCircle
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import toast from 'react-hot-toast';
import { getLeadUpdateRequests } from '../../api/leadsApi';

const navItems = [
  { to: '/dashboard',    icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/leads',        icon: Target,           label: 'Lead Database' },
  { to: '/appointments', icon: Calendar,         label: 'Appointments' },
  { to: '/tasks',        icon: CheckSquare,      label: 'Tasks' },
  { to: '/emails',       icon: Mail,             label: 'Email Leads' },
  { to: '/chats',        icon: MessageCircle,    label: 'WhatsApp' },
  { to: '/reports',      icon: BarChart3,        label: 'Reports' },
];

const adminItems = [
  { to: '/users', icon: Users, label: 'Users' },
];

const managerItems = [
  { to: '/my-team', icon: Users2, label: 'My Team' },
];

function getInitials(name = '') {
  return name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
}

const ROLE_LABELS = { admin: 'Admin', manager: 'Manager', sales_rep: 'RM' };

// ── Logout confirmation modal ──────────────────────────────────────────────
function LogoutConfirmModal({ onConfirm, onCancel }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }} onClick={onCancel}>
      <div
        className="glass-card"
        style={{ width: '100%', maxWidth: 380, padding: 28, borderRadius: 16 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{
          width: 52, height: 52, borderRadius: 14,
          background: 'rgba(239,68,68,0.12)',
          border: '1px solid rgba(239,68,68,0.25)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          margin: '0 auto 18px',
        }}>
          <LogOut size={22} color="var(--danger)" />
        </div>
        <h3 style={{ textAlign: 'center', marginBottom: 8, fontSize: '1.1rem' }}>Sign Out?</h3>
        <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: 24 }}>
          Are you sure you want to sign out? You'll need to log in again to access the CRM.
        </p>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={onCancel} id="logout-cancel-btn">
            Cancel
          </button>
          <button className="btn btn-danger btn-sm" style={{ flex: 1 }} onClick={onConfirm} id="logout-confirm-btn">
            <LogOut size={14} /> Yes, Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Sidebar({ isOpen, onClose, isCollapsed, onToggleCollapse }) {
  const { user, logout, isAdmin, isManagerOrAdmin } = useAuth();
  const navigate = useNavigate();
  const [pendingUpdateCount, setPendingUpdateCount] = useState(0);
  const [showLogoutModal, setShowLogoutModal] = useState(false);

  useEffect(() => {
    if (!isManagerOrAdmin) return;
    getLeadUpdateRequests({ status: 'pending' })
      .then((reqs) => setPendingUpdateCount(reqs.length))
      .catch(() => {});
  }, [isManagerOrAdmin]);

  const handleLogoutConfirm = () => {
    setShowLogoutModal(false);
    logout();
    toast.success('Logged out successfully');
    navigate('/login');
  };

  const handleNavClick = () => {
    if (onClose) onClose(); // auto-close on mobile
  };

  const handleProfileClick = () => {
    if (user?.id) {
      navigate(`/users/${user.id}`);
      if (onClose) onClose();
    }
  };

  // Tooltip shown on collapsed icon-only items
  const navLinkTitle = (label) => isCollapsed ? label : undefined;

  return (
    <>
      <aside className={`sidebar ${isOpen ? 'open' : ''} ${isCollapsed ? 'collapsed' : ''}`}>

        {/* ── Logo area ── */}
        <div className="sidebar-logo">
          {isCollapsed ? (
            /* Collapsed: logo acts as the expand button */
            <button
              onClick={onToggleCollapse}
              aria-label="Expand sidebar"
              title="Expand sidebar"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: '100%', padding: '4px 0',
              }}
            >
              <img src="/iws_logo_png.png" alt="IWS Logo" style={{ width: 32, height: 32, objectFit: 'contain' }} />
            </button>
          ) : (
            /* Expanded: logo + brand text + X to collapse */
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <img src="/iws_logo_png.png" alt="IWS Logo" style={{ width: 32, height: 32, objectFit: 'contain', flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="sidebar-logo-text">IWS Finserv</div>
                <div className="sidebar-logo-sub">Lead CRM</div>
              </div>
              <button
                onClick={onToggleCollapse}
                aria-label="Collapse sidebar"
                title="Collapse sidebar"
                style={{
                  background: 'none', border: 'none',
                  color: 'var(--text-muted)', cursor: 'pointer',
                  padding: 4, borderRadius: 6,
                  display: 'flex', alignItems: 'center',
                  flexShrink: 0,
                  transition: 'color 0.15s',
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = 'var(--text-primary)'}
                onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
              >
                <X size={18} />
              </button>
            </div>
          )}
        </div>

        {/* ── Nav ── */}
        <nav className="sidebar-nav">
          {!isCollapsed && <div className="nav-section-label">Navigation</div>}

          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={handleNavClick}
              title={navLinkTitle(label)}
            >
              <Icon size={16} className="nav-icon" />
              {!isCollapsed && <span className="nav-link-label">{label}</span>}
            </NavLink>
          ))}

          {isManagerOrAdmin && (
            <>
              {!isCollapsed && <div className="nav-section-label" style={{ marginTop: 8 }}>Administration</div>}

              {adminItems.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                  onClick={handleNavClick}
                  title={navLinkTitle(label)}
                >
                  <Icon size={16} className="nav-icon" />
                  {!isCollapsed && <span className="nav-link-label">{label}</span>}
                </NavLink>
              ))}

              {!isAdmin && managerItems.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                  onClick={handleNavClick}
                  title={navLinkTitle(label)}
                >
                  <Icon size={16} className="nav-icon" />
                  {!isCollapsed && <span className="nav-link-label">{label}</span>}
                </NavLink>
              ))}

              <NavLink
                to="/lead-update-requests"
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                onClick={handleNavClick}
                id="sidebar-lead-update-requests-link"
                title={navLinkTitle('Update Requests')}
              >
                <FileEdit size={16} className="nav-icon" />
                {!isCollapsed && (
                  <>
                    <span className="nav-link-label">Update Requests</span>
                    {pendingUpdateCount > 0 && (
                      <span className="sidebar-badge" style={{
                        marginLeft: 'auto',
                        minWidth: 20, height: 20,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        borderRadius: 10,
                        background: 'var(--primary)',
                        color: '#fff',
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        padding: '0 5px',
                      }}>
                        {pendingUpdateCount}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            </>
          )}
        </nav>

        {/* ── User section ── */}
        <div className="sidebar-user">
          {/* Clickable profile */}
          <div
            className="sidebar-user-info"
            onClick={handleProfileClick}
            title={isCollapsed ? `${user?.name} — View profile` : 'View my profile'}
            style={{
              cursor: 'pointer', borderRadius: 8, padding: '4px 8px',
              transition: 'background 0.15s',
              justifyContent: isCollapsed ? 'center' : 'flex-start',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(99,102,241,0.08)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            <div className="sidebar-avatar">{getInitials(user?.name)}</div>
            {!isCollapsed && (
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="sidebar-user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {user?.name}
                </div>
                <div className="sidebar-user-role">{ROLE_LABELS[user?.role] || user?.role}</div>
              </div>
            )}
            {!isCollapsed && <ChevronRight size={14} className="sidebar-chevron" style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
          </div>

          {/* Sign out */}
          <button
            className="btn btn-ghost btn-sm btn-full sidebar-logout-btn"
            onClick={() => setShowLogoutModal(true)}
            id="sidebar-logout-btn"
            title={isCollapsed ? 'Sign Out' : undefined}
            style={{ justifyContent: isCollapsed ? 'center' : undefined }}
          >
            <LogOut size={14} />
            {!isCollapsed && <span className="sidebar-logout-label">Sign Out</span>}
          </button>
        </div>
      </aside>

      {showLogoutModal && (
        <LogoutConfirmModal
          onConfirm={handleLogoutConfirm}
          onCancel={() => setShowLogoutModal(false)}
        />
      )}
    </>
  );
}
