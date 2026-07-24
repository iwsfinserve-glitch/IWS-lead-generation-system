import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import { getUser } from '../api/usersApi';
import { getLeads } from '../api/leadsApi';
import { getTasks } from '../api/tasksApi';
import { getAppointments } from '../api/appointmentsApi';
import { RoleBadge } from '../components/common/StatusBadge';
import LeadCard from '../components/cards/LeadCard';
import ManageUserModal from '../components/modals/ManageUserModal';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

export default function UserDetailsPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [user, setUser]     = useState(null);
  const [leads, setLeads]   = useState([]);
  const [tasks, setTasks]   = useState([]);
  const [appts, setAppts]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]       = useState('leads');
  const [showEdit, setShowEdit] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [u, l, t, a] = await Promise.all([
        getUser(id),
        getLeads({ assigned_rep_id: id, limit: 200 }),
        getTasks({ assigned_to_id: id, limit: 200 }),
        getAppointments({ user_id: id }),
      ]);
      setUser(u);
      setLeads(l);
      setTasks(t);
      setAppts(a);
    } catch { toast.error('Failed to load user data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, [id]);

  if (loading) return (
    <>
      <Navbar title="User Details" />
      <div className="loading-center" style={{ height: 'calc(100vh - 60px)' }}>
        <div className="spinner spinner-lg" />
      </div>
    </>
  );

  if (!user) return null;

  const initials = user.name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
  const pendingTasks = tasks.filter((t) => t.status === 'needsAction').length;
  const doneTasks    = tasks.filter((t) => t.status === 'completed').length;

  const TABS = [
    { key: 'leads',  label: `Leads (${leads.length})` },
    { key: 'tasks',  label: `Tasks (${tasks.length})` },
    { key: 'appts',  label: `Appointments (${appts.length})` },
  ];

  return (
    <>
      <Navbar title="User Details" />
      <div className="page-container">
        <button className="btn btn-ghost btn-sm" style={{ marginBottom: 16 }} onClick={() => navigate(-1)} id="user-details-back-btn">
          <ArrowLeft size={14} /> Back
        </button>

        {/* Profile header */}
        <div className="glass-card" style={{ padding: '24px 28px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'linear-gradient(135deg, var(--primary), var(--accent))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem', fontWeight: 800, color: '#fff', flexShrink: 0 }}>
            {initials}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
              <h2 style={{ margin: 0 }}>{user.name}</h2>
              <RoleBadge role={user.role} />
            </div>
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>📧 {user.email}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>📊 {leads.length} leads · {pendingTasks} pending tasks · {doneTasks} tasks done</div>
            </div>
          </div>
          {isAdmin && (
            <button className="btn btn-secondary btn-sm" onClick={() => setShowEdit(true)} id="edit-user-btn">
              <Edit size={14} /> Edit User
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={`tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)} id={`user-tab-${t.key}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Leads tab */}
        {tab === 'leads' && (
          leads.length === 0 ? (
            <div className="empty-state"><div className="empty-state-icon">🎯</div><div className="empty-state-title">No leads assigned</div></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {leads.map((l) => <LeadCard key={l.id} lead={l} />)}
            </div>
          )
        )}

        {/* Tasks tab */}
        {tab === 'tasks' && (
          tasks.length === 0 ? (
            <div className="empty-state"><div className="empty-state-icon">✅</div><div className="empty-state-title">No tasks</div></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {tasks.map((t) => (
                <div key={t.id} className="glass-card" style={{ padding: '14px 16px', borderLeft: `3px solid ${t.status === 'completed' ? 'var(--success)' : 'var(--primary)'}` }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>{t.title}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    {t.status === 'completed' ? '✅ Completed' : '⏳ Pending'} · Due: {t.due || 'N/A'} · {t.lead_name}
                  </div>
                </div>
              ))}
            </div>
          )
        )}

        {/* Appointments tab */}
        {tab === 'appts' && (
          appts.length === 0 ? (
            <div className="empty-state"><div className="empty-state-icon">📅</div><div className="empty-state-title">No appointments</div></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {appts.map((a) => (
                <div key={a.id} className="glass-card" style={{ padding: '14px 16px' }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>{a.title}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    {new Date(a.start_time).toLocaleDateString()} · {a.lead_name} · {a.mode?.replace('_',' ')}
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>

      {showEdit && <ManageUserModal user={user} onClose={() => setShowEdit(false)} onSaved={() => { setShowEdit(false); fetchAll(); }} />}
    </>
  );
}
