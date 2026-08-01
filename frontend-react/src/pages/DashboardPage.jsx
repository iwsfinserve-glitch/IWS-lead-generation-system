import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/layout/Navbar';
import MetricCard from '../components/common/MetricCard';
import LeadCard from '../components/cards/LeadCard';
import { getLeads, getLeadsSummary, getSources } from '../api/leadsApi';
import { getAppointments } from '../api/appointmentsApi';
import { getTasks } from '../api/tasksApi';
import { getUsers } from '../api/usersApi';
import { Users, Target, CheckSquare, TrendingUp, Plus, ChevronRight, Search, X } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import CreateLeadModal from '../components/modals/CreateLeadModal';
import ManageUserModal from '../components/modals/ManageUserModal';
import { RoleBadge } from '../components/common/StatusBadge';

// ── Sales Rep Dashboard ─────────────────────────────────────────────
function SalesRepDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [leads, setLeads]           = useState([]);
  const [allLeads, setAllLeads]     = useState([]);
  const [summary, setSummary]       = useState({});
  const [sources, setSources]       = useState([]);
  const [reps, setReps]             = useState([]);
  const [appointments, setAppts]    = useState([]);
  const [tasks, setTasks]           = useState([]);
  const [loading, setLoading]       = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const [searchParams, setSearchParams] = useSearchParams();
  const leadSearch = searchParams.get('search') || '';
  const leadStatus = searchParams.get('status') || '';
  const leadSource = searchParams.get('source') || '';
  const leadRep    = searchParams.get('rep') || '';

  const updateParams = (newParams) => {
    const current = Object.fromEntries(searchParams.entries());
    Object.keys(newParams).forEach(k => {
      if (!newParams[k]) delete current[k];
      else current[k] = newParams[k];
    });
    setSearchParams(current, { replace: true });
  };
  const setLeadSearch = (val) => updateParams({ search: val });
  const setLeadStatus = (val) => updateParams({ status: val });
  const setLeadSource = (val) => updateParams({ source: val });
  const setLeadRep    = (val) => updateParams({ rep: val });

  useEffect(() => {
    Promise.all([
      getLeads({ assigned_rep_id: user.id, limit: 500 }),
      getLeadsSummary({ assigned_rep_id: user.id }).catch(() => ({})),
      getAppointments(),
      getTasks({ limit: 100 }),
      getSources().catch(() => []),
      getUsers().catch(() => []),
    ]).then(([l, s, a, t, src, usersRes]) => {
      setAllLeads(l);
      setLeads(l.slice(0, 10));
      setSummary(s);
      setAppts(a);
      setTasks(t);
      setSources(src);
      setReps(usersRes.filter(u => u.role === 'manager' || u.role === 'sales_rep'));
    }).catch(() => toast.error('Failed to load dashboard data'))
      .finally(() => setLoading(false));
  }, [user.id]);

  // Filter my leads based on search/status/source
  const STATUS_OPTS = [
    { value: '', label: 'All Statuses' },
    { value: 'unassigned', label: 'Unassigned' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'potential', label: 'Potential' },
    { value: 'non_potential', label: 'Non-Potential' },
    { value: 'converted_to_investor', label: 'Converted' },
    { value: 'existing_investor', label: 'Existing Investor' },
  ];
  const filteredLeads = allLeads.filter((l) => {
    if (leadSearch.trim()) {
      const t = leadSearch.toLowerCase();
      if (!(
        l.name.toLowerCase().includes(t) ||
        (l.profession || '').toLowerCase().includes(t) ||
        (l.source_name || '').toLowerCase().includes(t)
      )) return false;
    }
    if (leadStatus && l.status !== leadStatus) return false;
    if (leadSource && String(l.source_id) !== leadSource) return false;
    if (leadRep) {
      if (leadRep === 'unassigned') {
        if (l.assigned_rep_id) return false;
      } else if (String(l.assigned_rep_id) !== leadRep) {
        return false;
      }
    }
    return true;
  });
  const hasLeadFilters = leadSearch.trim() || leadStatus || leadSource || leadRep;

  const now = new Date().toISOString();
  const upcoming = appointments.filter((a) => a.start_time >= now).sort((a, b) => a.start_time.localeCompare(b.start_time)).slice(0, 5);
  const pending  = tasks.filter((t) => t.status === 'needsAction').slice(0, 5);
  const totalLeads = summary.total || 0;
  const potential  = summary.potential || 0;
  const nonPotential = summary.non_potential || 0;
  const converted  = summary.converted_to_investor || 0;

  if (loading) return <div className="loading-center"><div className="spinner" /> Loading...</div>;

  return (
    <>
      <div className="metrics-grid">
        <MetricCard label="My Clients" value={totalLeads} icon={Target} />
        <MetricCard label="Potential" value={potential} icon={TrendingUp} color="var(--accent)" />
        <MetricCard label="Non-potential" value={nonPotential} icon={X} color="var(--warning)" />
        <MetricCard label="Converted" value={converted} icon={CheckSquare} color="var(--success)" />
      </div>

      <div className="dashboard-grid">
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
                Due: {t.end_time ? new Date(t.end_time).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : (t.due || 'No due date')} {t.lead_name ? `· ${t.lead_name}` : ''}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* My Clients */}
      <div className="page-header">
        <h2 style={{ margin: 0 }}>My Clients</h2>
        <div className="page-header-actions">
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)} id="dashboard-create-lead-btn">
            <Plus size={14} /> New Lead
          </button>
        </div>
      </div>
      {/* Lead Filters */}
      <div className="filter-toolbar" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <div className="search-wrap" style={{ flex: '1 1 180px', minWidth: 140 }}>
          <Search size={13} className="search-icon" />
          <input
            className="search-input"
            placeholder="Search leads…"
            value={leadSearch}
            onChange={(e) => setLeadSearch(e.target.value)}
            id="dashboard-lead-search"
          />
        </div>
        <select
          className="form-select"
          style={{ width: 'auto', minWidth: 130, padding: '7px 10px', fontSize: '0.8rem', cursor: 'pointer' }}
          value={leadStatus}
          onChange={(e) => setLeadStatus(e.target.value)}
          id="dashboard-lead-status"
        >
          {STATUS_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select
          className="form-select"
          style={{ width: 'auto', minWidth: 130, padding: '7px 10px', fontSize: '0.8rem', cursor: 'pointer' }}
          value={leadSource}
          onChange={(e) => setLeadSource(e.target.value)}
          id="dashboard-lead-source"
        >
          <option value="">All Sources</option>
          {sources.map((s) => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
        </select>
        <select
          className="form-select"
          style={{ width: 'auto', minWidth: 130, padding: '7px 10px', fontSize: '0.8rem', cursor: 'pointer' }}
          value={leadRep}
          onChange={(e) => setLeadRep(e.target.value)}
          id="dashboard-lead-rep"
        >
          <option value="">All Reps</option>
          <option value="unassigned">Unassigned</option>
          {reps.map((r) => <option key={r.id} value={String(r.id)}>{r.name}</option>)}
        </select>
        {hasLeadFilters && (
          <button className="btn btn-ghost btn-sm" onClick={() => { setLeadSearch(''); setLeadStatus(''); setLeadSource(''); setLeadRep(''); }} id="dashboard-lead-clear">
            <X size={13} /> Clear
          </button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {filteredLeads.slice(0, 10).map((l) => <LeadCard key={l.id} lead={l} />)}
        {filteredLeads.length === 0 && <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>{hasLeadFilters ? 'No leads match your filters.' : 'No leads assigned to you yet.'}</p>}
      </div>
      {(hasLeadFilters ? filteredLeads.length : totalLeads) > 10 && (
        <button className="btn btn-ghost btn-full" style={{ marginTop: 12 }} onClick={() => navigate('/leads')} id="dashboard-view-all-leads-btn">
          View all {hasLeadFilters ? filteredLeads.length : totalLeads} leads
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
  const [leads, setLeads]           = useState([]);
  const [allLeads, setAllLeads]     = useState([]);
  const [summary, setSummary]       = useState({});
  const [sources, setSources]       = useState([]);
  const [reps, setReps]             = useState([]);
  const [appointments, setAppts]    = useState([]);
  const [tasks, setTasks]           = useState([]);
  const [teamSize, setTeamSize]     = useState(0);
  const [loading, setLoading]       = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const [searchParams, setSearchParams] = useSearchParams();
  const leadSearch = searchParams.get('search') || '';
  const leadStatus = searchParams.get('status') || '';
  const leadSource = searchParams.get('source') || '';
  const leadRep    = searchParams.get('rep') || '';

  const updateParams = (newParams) => {
    setSearchParams(prev => {
      const current = Object.fromEntries(prev.entries());
      Object.keys(newParams).forEach(k => {
        if (!newParams[k]) delete current[k];
        else current[k] = newParams[k];
      });
      return current;
    }, { replace: true });
  };
  const setLeadSearch = (val) => updateParams({ search: val });
  const setLeadStatus = (val) => updateParams({ status: val });
  const setLeadSource = (val) => updateParams({ source: val });
  const setLeadRep    = (val) => updateParams({ rep: val });

  const [localSearch, setLocalSearch] = useState(leadSearch);
  useEffect(() => { setLocalSearch(leadSearch); }, [leadSearch]);
  useEffect(() => {
    const handler = setTimeout(() => {
      if (localSearch !== leadSearch) setLeadSearch(localSearch);
    }, 400);
    return () => clearTimeout(handler);
  }, [localSearch, leadSearch]);

  useEffect(() => {
    Promise.all([
      getLeads({ assigned_rep_id: user.id, limit: 500 }),
      getLeadsSummary({ assigned_rep_id: user.id }).catch(() => ({})),
      getAppointments(),
      getTasks({ limit: 100 }),
      getUsers().then((u) => { setReps(u.filter(x => x.role === 'manager' || x.role === 'sales_rep')); return u.filter((x) => x.manager_id === user.id).length; }),
      getSources().catch(() => []),
    ]).then(([l, s, a, t, ts, src]) => {
      setAllLeads(l);
      setLeads(l.slice(0, 10));
      setSummary(s);
      setAppts(a);
      setTasks(t);
      setTeamSize(ts);
      setSources(src);
    }).catch(() => toast.error('Failed to load dashboard data'))
      .finally(() => setLoading(false));
  }, [user.id]);

  const STATUS_OPTS = [
    { value: '', label: 'All Statuses' },
    { value: 'unassigned', label: 'Unassigned' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'potential', label: 'Potential' },
    { value: 'non_potential', label: 'Non-Potential' },
    { value: 'converted_to_investor', label: 'Converted' },
    { value: 'existing_investor', label: 'Existing Investor' },
  ];
  const filteredLeads = allLeads.filter((l) => {
    if (leadSearch.trim()) {
      const t = leadSearch.toLowerCase();
      if (!(
        l.name.toLowerCase().includes(t) ||
        (l.profession || '').toLowerCase().includes(t) ||
        (l.source_name || '').toLowerCase().includes(t)
      )) return false;
    }
    if (leadStatus && l.status !== leadStatus) return false;
    if (leadSource && String(l.source_id) !== leadSource) return false;
    if (leadRep) {
      if (leadRep === 'unassigned') {
        if (l.assigned_rep_id) return false;
      } else if (String(l.assigned_rep_id) !== leadRep) {
        return false;
      }
    }
    return true;
  });
  const hasLeadFilters = leadSearch.trim() || leadStatus || leadSource || leadRep;

  const now = new Date().toISOString();
  const upcoming  = appointments.filter((a) => a.start_time >= now).sort((a, b) => a.start_time.localeCompare(b.start_time)).slice(0, 5);
  const pending   = tasks.filter((t) => t.status === 'needsAction').slice(0, 5);
  const totalLeads = summary.total || 0;
  const potential = summary.potential || 0;
  const nonPotential = summary.non_potential || 0;
  const converted = summary.converted_to_investor || 0;

  if (loading) return <div className="loading-center"><div className="spinner" /> Loading...</div>;

  return (
    <>
      <div className="metrics-grid">
        <MetricCard label="My Clients"   value={totalLeads}  icon={Target} />
        <MetricCard label="Potential"  value={potential}     icon={TrendingUp} color="var(--accent)" />
        <MetricCard label="Non-potential" value={nonPotential} icon={X} color="var(--warning)" />
        <MetricCard label="Converted"  value={converted}     icon={CheckSquare} color="var(--success)" />
        <MetricCard label="My Team"    value={teamSize}      icon={Users} color="var(--primary-light)"
          onClick={() => navigate('/my-team')} style={{ cursor: 'pointer' }} />
      </div>

      {/* Quick link to My Team */}
      <div
        className="glass-card"
        style={{
          padding: '14px 20px', marginBottom: 24, display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', cursor: 'pointer',
          background: 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.08))',
          border: '1px solid rgba(99,102,241,0.2)',
        }}
        onClick={() => navigate('/my-team')}
        id="dashboard-my-team-link"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Users size={18} color="var(--primary)" />
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>My Sales Team</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              View your {teamSize} direct report{teamSize !== 1 ? 's' : ''}, their leads and performance
            </div>
          </div>
        </div>
        <ChevronRight size={16} color="var(--text-muted)" />
      </div>

      <div className="dashboard-grid">
        {/* Upcoming Appointments */}
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Upcoming Appointments</h3>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/appointments')} id="mgr-dashboard-appts-link">
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
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/tasks')} id="mgr-dashboard-tasks-link">
              View All <ChevronRight size={14} />
            </button>
          </div>
          {pending.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No pending tasks. Great work!</p>
          ) : pending.map((t) => (
            <div key={t.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{t.title}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2 }}>
                Due: {t.end_time ? new Date(t.end_time).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : (t.due || 'No due date')} {t.lead_name ? `· ${t.lead_name}` : ''}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* My Clients */}
      <div className="page-header">
        <h2 style={{ margin: 0 }}>My Clients</h2>
        <div className="page-header-actions">
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)} id="mgr-dashboard-create-lead-btn">
            <Plus size={14} /> New Lead
          </button>
        </div>
      </div>
      {/* Lead Filters */}
      <div className="filter-toolbar" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <div className="search-wrap" style={{ flex: '1 1 180px', minWidth: 140 }}>
          <Search size={13} className="search-icon" />
          <input
            className="search-input"
            placeholder="Search leads…"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            id="mgr-dashboard-lead-search"
          />
        </div>
        <select
          className="form-select"
          style={{ width: 'auto', minWidth: 130, padding: '7px 10px', fontSize: '0.8rem', cursor: 'pointer' }}
          value={leadStatus}
          onChange={(e) => setLeadStatus(e.target.value)}
          id="mgr-dashboard-lead-status"
        >
          {STATUS_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select
          className="form-select"
          style={{ width: 'auto', minWidth: 130, padding: '7px 10px', fontSize: '0.8rem', cursor: 'pointer' }}
          value={leadSource}
          onChange={(e) => setLeadSource(e.target.value)}
          id="mgr-dashboard-lead-source"
        >
          <option value="">All Sources</option>
          {sources.map((s) => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
        </select>
        <select
          className="form-select"
          style={{ width: 'auto', minWidth: 130, padding: '7px 10px', fontSize: '0.8rem', cursor: 'pointer' }}
          value={leadRep}
          onChange={(e) => setLeadRep(e.target.value)}
          id="mgr-dashboard-lead-rep"
        >
          <option value="">All Reps</option>
          <option value="unassigned">Unassigned</option>
          {reps.map((r) => <option key={r.id} value={String(r.id)}>{r.name}</option>)}
        </select>
        {hasLeadFilters && (
          <button className="btn btn-ghost btn-sm" onClick={() => { setLeadSearch(''); setLeadStatus(''); setLeadSource(''); setLeadRep(''); }} id="mgr-dashboard-lead-clear">
            <X size={13} /> Clear
          </button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {filteredLeads.slice(0, 10).map((l) => <LeadCard key={l.id} lead={l} />)}
        {filteredLeads.length === 0 && <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>{hasLeadFilters ? 'No leads match your filters.' : 'No leads assigned to you yet.'}</p>}
      </div>
      {(hasLeadFilters ? filteredLeads.length : totalLeads) > 10 && (
        <button className="btn btn-ghost btn-full" style={{ marginTop: 12 }} onClick={() => navigate('/leads')} id="mgr-dashboard-view-all-leads-btn">
          View all {hasLeadFilters ? filteredLeads.length : totalLeads} leads
        </button>
      )}

      {showCreate && <CreateLeadModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); window.location.reload(); }} />}
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
      <div className="metrics-grid">
        <MetricCard label="Total Users" value={users.length} icon={Users} />
        <MetricCard label="Admins"      value={admins}       icon={Users} color="var(--primary-light)" />
        <MetricCard label="Managers"    value={managers}     icon={Users} color="var(--accent)" />
        <MetricCard label="Sales Reps"  value={reps}         icon={Users} color="var(--success)" />
      </div>

      <div className="page-header">
        <h2 style={{ margin: 0 }}>User Directory ({users.length})</h2>
        <div className="page-header-actions">
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)} id="admin-create-user-btn">
            <Plus size={14} /> New User
          </button>
        </div>
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
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{u.email || u.username}</div>
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
          <h1 style={{ marginBottom: 4 }}>{greeting()}, {user?.name?.split(' ')[0]}</h1>
          <p style={{ color: 'var(--text-muted)' }}>Here's what's happening with your leads today.</p>
        </div>

        {isAdmin   ? <AdminDashboard />   :
         isManager ? <ManagerDashboard /> :
                     <SalesRepDashboard />}
      </div>
    </>
  );
}
