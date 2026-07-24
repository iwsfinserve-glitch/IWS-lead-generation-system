import { useState, useEffect } from 'react';
import { Plus, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/layout/Navbar';
import { RoleBadge } from '../components/common/StatusBadge';
import ManageUserModal from '../components/modals/ManageUserModal';
import { getUsers, deleteUser } from '../api/usersApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

export default function UsersPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [editUser, setEditUser]   = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const fetchUsers = () => {
    setLoading(true);
    getUsers()
      .then(setUsers)
      .catch(() => toast.error('Failed to load users'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchUsers(); }, []);

  const handleDelete = async (u) => {
    try {
      await deleteUser(u.id);
      toast.success(`${u.name} deleted`);
      setDeleteTarget(null);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    }
  };

  const filtered = users.filter((u) => {
    const nameMatch = u.name.toLowerCase().includes(search.toLowerCase()) ||
                      u.email.toLowerCase().includes(search.toLowerCase());
    const roleMatch = !roleFilter || u.role === roleFilter;
    return nameMatch && roleMatch;
  });

  const ROLE_COLORS = {
    admin:    { bg: 'rgba(99,102,241,0.12)', border: 'rgba(99,102,241,0.3)' },
    manager:  { bg: 'rgba(14,165,233,0.12)',  border: 'rgba(14,165,233,0.3)' },
    sales_rep:{ bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.3)' },
  };

  return (
    <>
      <Navbar title="User Management" />
      <div className="page-container">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>User Management</h1>
            <p style={{ color: 'var(--text-muted)' }}>{users.length} total users in the system</p>
          </div>
          {isAdmin && (
            <button className="btn btn-primary" onClick={() => setShowCreate(true)} id="create-user-btn">
              <Plus size={16} /> New User
            </button>
          )}
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
          <div className="search-wrap" style={{ flex: 1, minWidth: 220 }}>
            <Search size={15} className="search-icon" />
            <input
              className="search-input"
              placeholder="Search by name or email…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              id="users-search"
            />
          </div>
          <select className="form-select" style={{ width: 160 }} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} id="users-role-filter">
            <option value="">All Roles</option>
            <option value="admin">Admin</option>
            <option value="manager">Manager</option>
            <option value="sales_rep">Sales Rep</option>
          </select>
        </div>

        {/* Users Grid */}
        {loading ? (
          <div className="loading-center"><div className="spinner" /> Loading users…</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">👥</div>
            <div className="empty-state-title">No users found</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
            {filtered.map((u) => {
              const roleStyle = ROLE_COLORS[u.role] || {};
              const initials = u.name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
              return (
                <div
                  key={u.id}
                  className="glass-card"
                  style={{ padding: 20, cursor: 'pointer', borderLeft: `3px solid ${roleStyle.border || 'var(--border)'}` }}
                  onClick={() => navigate(`/users/${u.id}`)}
                  id={`user-card-${u.id}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
                    <div style={{
                      width: 44, height: 44, borderRadius: '50%',
                      background: 'linear-gradient(135deg, var(--primary), var(--accent))',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontWeight: 800, fontSize: '1rem', color: '#fff', flexShrink: 0,
                    }}>{initials}</div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.name}</div>
                      <RoleBadge role={u.role} />
                    </div>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    ✉️ {u.email}
                  </div>
                  {isAdmin && (
                    <div style={{ display: 'flex', gap: 8 }} onClick={(e) => e.stopPropagation()}>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => { e.stopPropagation(); setEditUser(u); }}
                        id={`edit-user-btn-${u.id}`}
                      >
                        Edit
                      </button>
                      {deleteTarget?.id === u.id ? (
                        <>
                          <button className="btn btn-danger btn-sm" onClick={() => handleDelete(u)} id={`confirm-delete-${u.id}`}>
                            Confirm Delete
                          </button>
                          <button className="btn btn-ghost btn-sm" onClick={() => setDeleteTarget(null)} id={`cancel-delete-${u.id}`}>
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ color: 'var(--danger)' }}
                          onClick={(e) => { e.stopPropagation(); setDeleteTarget(u); }}
                          id={`delete-user-btn-${u.id}`}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showCreate && <ManageUserModal onClose={() => setShowCreate(false)} onSaved={() => { setShowCreate(false); fetchUsers(); }} />}
      {editUser  && <ManageUserModal user={editUser} onClose={() => setEditUser(null)} onSaved={() => { setEditUser(null); fetchUsers(); }} />}
    </>
  );
}
