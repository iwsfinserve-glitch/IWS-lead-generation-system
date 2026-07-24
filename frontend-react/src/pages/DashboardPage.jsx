import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/layout/Navbar';
import MetricCard from '../components/common/MetricCard';
import LeadCard from '../components/cards/LeadCard';
import { getLeads } from '../api/leadsApi';
import { getAppointments } from '../api/appointmentsApi';
import { getTasks } from '../api/tasksApi';
import { getUsers } from '../api/usersApi';
import { Users, Target, CheckSquare, Calendar, TrendingUp, Plus, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import CreateLeadModal from '../components/modals/CreateLeadModal';
import ManageUserModal from '../components/modals/ManageUserModal';
import { RoleBadge } from '../components/common/StatusBadge';

// ── Sales Rep Dashboard ─────────────────────────────────────────────
function SalesRepDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [leads, setLeads]           = useState([]);
  const [appointments, setAppts]    = useState([]);
  const [tasks, setTasks]           = useState([]);
  const [loading, setLoading]       = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    Promise.all([
      getLeads({ assigned_rep_id: user.id, limit: 100 }),
      getAppointments(),
      getTasks({ limit: 100 }),
    ]).then(([l, a, t]) => {
      setLeads(l);
      setAppts(a);
      setTasks(t);
    }).catch(() => toast.error('Failed to load dashboard data'))
      .finally(() => setLoading(false));
  }, [user.id]);

  const now = new Date().toISOString();
  const upcoming = appointments.filter((a) => a.start_time >= now).sort((a, b) => a.start_time.localeCompare(b.start_time)).slice(0, 5);
  const pending  = tasks.filter((t) => t.status === 'needsAction').slice(0, 5);
  const unassigned = leads.filter((l) => l.status === 'unassigned').length;
  const potential  = leads.filter((l) => l.status === 'potential').length;
  const converted  = leads.filter((l) => l.status === 'converted_to_investor').length;

  if (loading) return <div className="loading-center"><div className="spinner" /> Loading...</div>;

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard label="My Leads" value={leads.length} icon={Target} />
        <MetricCard label="Unassigned" value={unassigned} icon={Users} color="var(--warning)" />
        <MetricCard label="Potential" value={potential} icon={TrendingUp} color="var(--accent)" />
        <MetricCard label="Converted" value={converted} icon={CheckSquare} color="var(--success)" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 28 }}>
        {/* Upcoming Appointments */}
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Upcoming Appointments</h3>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/appointments')} id="dashboard-appts-link">
              View All <ChevronRight size={14} />
            </button>
          </div>
          {upcoming.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No upcoming appointments.</p>
          ) : upcoming.map((a) => (
            <div key={a.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{a.title}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2 }}>
                {new Date(a.start_time).toLocaleString()} · {a.lead_name}
              </div>
            </div>
          ))}
        </div>

        {/* Pending Tasks */}
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Pending Tasks</h3>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/tasks')} id="dashboard-tasks-link">
              View All <ChevronRight size={14} />
            </button>
          </div>
          {pending.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No pending tasks. Great work!</p>
          ) : pending.map((t) => (
            <div key={t.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{t.title}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2 }}>
                Due: {t.due || 'No due date'} · {t.lead_name || ''}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* My Leads */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>My Leads</h2>
        <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)} id="dashboard-create-lead-btn">
          <Plus size={14} /> New Lead
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {leads.slice(0, 10).map((l) => <LeadCard key={l.id} lead={l} />)}
      </div>
      {leads.length > 10 && (
        <button className="btn btn-ghost btn-full" style={{ marginTop: 12 }} onClick={() => navigate('/leads')} id="dashboard-view-all-leads-btn">
          View all {leads.length} leads
        </button>
      )}

      {showCreate && <CreateLeadModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); window.location.reload(); }} />}
    </>
  );
}

// ── Manager Dashboard ────────────────────────────────────────────────
function ManagerDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getUsers()
      .then((u) => setUsers(u.filter((x) => x.manager_id === user.id)))
      .catch(() => toast.error('Failed to load team'))
      .finally(() => setLoading(false));
  }, [user.id]);

  if (loading) return <div className="loading-center"><div className="spinner" /> Loading...</div>;

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard label="Direct Reports" value={users.length} icon={Users} />
      </div>
      <h2 style={{ marginBottom: 16 }}>My Sales Team</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
        {users.map((u) => (
          <div key={u.id} className="glass-card" style={{ padding: 18, cursor: 'pointer' }} onClick={() => navigate(`/users/${u.id}`)} id={`manager-user-card-${u.id}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
              <div style={{
                width: 40, height: 40, borderRadius: '50%',
                background: 'linear-gradient(135deg, var(--primary), var(--accent))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, color: '#fff',
              }}>
                {u.name.slice(0, 2).toUpperCase()}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>{u.name}</div>
                <RoleBadge role={u.role} />
              </div>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{u.email}</div>
          </div>
        ))}
      </div>
    </>
  );
}

// ── Admin Dashboard ──────────────────────────────────────────────────
function AdminDashboard() {
  const navigate = useNavigate();
  const [users, setUsers]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    getUsers()
      .then(setUsers)
      .catch(() => toast.error('Failed to load users'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading-center"><div className="spinner" /> Loading...</div>;

  const admins   = users.filter((u) => u.role === 'admin').length;
  const managers = users.filter((u) => u.role === 'manager').length;
  const reps     = users.filter((u) => u.role === 'sales_rep').length;

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard label="Total Users" value={users.length} icon={Users} />
        <MetricCard label="Admins"      value={admins}       icon={Users} color="var(--primary-light)" />
        <MetricCard label="Managers"    value={managers}     icon={Users} color="var(--accent)" />
        <MetricCard label="Sales Reps"  value={reps}         icon={Users} color="var(--success)" />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>User Directory ({users.length})</h2>
        <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)} id="admin-create-user-btn">
          <Plus size={14} /> New User
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
        {users.map((u) => (
          <div key={u.id} className="glass-card" style={{ padding: 18, cursor: 'pointer' }} onClick={() => navigate(`/users/${u.id}`)} id={`admin-user-card-${u.id}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
              <div style={{
                width: 40, height: 40, borderRadius: '50%',
                background: 'linear-gradient(135deg, var(--primary), var(--accent))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, color: '#fff',
              }}>
                {u.name.slice(0, 2).toUpperCase()}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>{u.name}</div>
                <RoleBadge role={u.role} />
              </div>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{u.email}</div>
          </div>
        ))}
      </div>

      {showCreate && <ManageUserModal onClose={() => setShowCreate(false)} onSaved={() => { setShowCreate(false); getUsers().then(setUsers); }} />}
    </>
  );
}

// ── Main Dashboard Page ──────────────────────────────────────────────
export default function DashboardPage() {
  const { user, isAdmin, isManager } = useAuth();

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  };

  return (
    <>
      <Navbar title="Dashboard" />
      <div className="page-container">
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ marginBottom: 4 }}>{greeting()}, {user?.name?.split(' ')[0]} 👋</h1>
          <p style={{ color: 'var(--text-muted)' }}>Here's what's happening with your leads today.</p>
        </div>

        {isAdmin   ? <AdminDashboard />   :
         isManager ? <ManagerDashboard /> :
                     <SalesRepDashboard />}
      </div>
    </>
  );
}
