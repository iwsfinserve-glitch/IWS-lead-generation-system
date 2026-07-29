import { NavLink, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import {
  LayoutDashboard, Users, Users2, Target, Calendar, CheckSquare,
  BarChart3, LogOut, Zap, X, FileEdit, Mail
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import toast from 'react-hot-toast';
import { getLeadUpdateRequests } from '../../api/leadsApi';

const navItems = [
  { to: '/dashboard',    icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/leads',        icon: Target,           label: 'All Leads' },
  { to: '/appointments', icon: Calendar,         label: 'Appointments' },
  { to: '/tasks',        icon: CheckSquare,      label: 'Tasks' },
  { to: '/emails',       icon: Mail,             label: 'Email Leads' },
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

const ROLE_LABELS = { admin: 'Admin', manager: 'Manager', sales_rep: 'Sales Rep' };

export default function Sidebar({ isOpen, onClose }) {
  const { user, logout, isAdmin, isManagerOrAdmin } = useAuth();
  const navigate = useNavigate();
  const [pendingUpdateCount, setPendingUpdateCount] = useState(0);

  useEffect(() => {
    if (!isManagerOrAdmin) return;
    getLeadUpdateRequests({ status: 'pending' })
      .then((reqs) => setPendingUpdateCount(reqs.length))
      .catch(() => {});
  }, [isManagerOrAdmin]);

  const handleLogout = () => {
    logout();
    toast.success('Logged out successfully');
    navigate('/login');
  };

  // Auto-close sidebar on nav link click (mobile)
  const handleNavClick = () => {
    if (onClose) onClose();
  };

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
      {/* Logo row — includes close button on mobile */}
      <div className="sidebar-logo">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <Zap size={16} color="#fff" />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="sidebar-logo-text">IWS Finserv</div>
            <div className="sidebar-logo-sub">Lead CRM</div>
          </div>
          {/* Close button — only visible on mobile via CSS */}
          <button
            className="sidebar-close-btn"
            onClick={onClose}
            aria-label="Close navigation"
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: 4,
              borderRadius: 6,
              display: 'flex',
              alignItems: 'center',
              flexShrink: 0,
            }}
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Nav */}
      <nav className="sidebar-nav">
        <div className="nav-section-label">Navigation</div>

        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            onClick={handleNavClick}
          >
            <Icon size={16} className="nav-icon" />
            {label}
          </NavLink>
        ))}

        {isManagerOrAdmin && (
          <>
            <div className="nav-section-label" style={{ marginTop: 8 }}>Administration</div>
            {adminItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <Icon size={16} className="nav-icon" />
                {label}
              </NavLink>
            ))}
            {/* My Team — managers only */}
            {!isAdmin && managerItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <Icon size={16} className="nav-icon" />
                {label}
              </NavLink>
            ))}
            {/* Lead Update Requests */}
            <NavLink
              to="/lead-update-requests"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={handleNavClick}
              id="sidebar-lead-update-requests-link"
            >
              <FileEdit size={16} className="nav-icon" />
              Update Requests
              {pendingUpdateCount > 0 && (
                <span style={{
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
            </NavLink>
          </>
        )}
      </nav>

      {/* User section */}
      <div className="sidebar-user">
        <div className="sidebar-user-info">
          <div className="sidebar-avatar">{getInitials(user?.name)}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="sidebar-user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.name}
            </div>
            <div className="sidebar-user-role">{ROLE_LABELS[user?.role] || user?.role}</div>
          </div>
        </div>
        <button className="btn btn-ghost btn-sm btn-full" onClick={handleLogout} id="sidebar-logout-btn">
          <LogOut size={14} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
