import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Users, Target, Calendar, CheckSquare,
  BarChart3, LogOut, ChevronRight, Zap,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import toast from 'react-hot-toast';

const navItems = [
  { to: '/dashboard',    icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/leads',        icon: Target,           label: 'All Leads' },
  { to: '/appointments', icon: Calendar,         label: 'Appointments' },
  { to: '/tasks',        icon: CheckSquare,      label: 'Tasks' },
  { to: '/reports',      icon: BarChart3,        label: 'Reports' },
];

const adminItems = [
  { to: '/users', icon: Users, label: 'Users' },
];

function getInitials(name = '') {
  return name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
}

const ROLE_LABELS = { admin: 'Admin', manager: 'Manager', sales_rep: 'Sales Rep' };

export default function Sidebar() {
  const { user, logout, isAdmin, isManagerOrAdmin } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    toast.success('Logged out successfully');
    navigate('/login');
  };

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Zap size={16} color="#fff" />
          </div>
          <div>
            <div className="sidebar-logo-text">IWS Finserve</div>
            <div className="sidebar-logo-sub">Lead CRM</div>
          </div>
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
              >
                <Icon size={16} className="nav-icon" />
                {label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* User section */}
      <div className="sidebar-user">
        <div className="sidebar-user-info">
          <div className="sidebar-avatar">{getInitials(user?.name)}</div>
          <div style={{ minWidth: 0 }}>
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
