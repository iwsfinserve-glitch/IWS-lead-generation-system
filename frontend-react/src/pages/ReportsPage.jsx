import { useState, useEffect } from 'react';
import { FileText, Download, Loader2, BarChart3, TrendingUp, Users } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  getLeadJourneyReport, getPeriodicLeadsReport,
  getUserPerformanceReport, getTeamPerformanceReport,
} from '../api/reportsApi';
import { getLeads } from '../api/leadsApi';
import { getUsers } from '../api/usersApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

const STATUS_COLORS = {
  new: '#3b82f6', in_progress: '#f59e0b', potential: '#8b5cf6',
  converted_to_investor: '#10b981', existing_investor: '#059669', non_potential: '#ef4444',
};
const STATUS_LABELS = {
  new: 'New', in_progress: 'In Progress', potential: 'Potential',
  converted_to_investor: 'Converted', existing_investor: 'Existing Investor', non_potential: 'Non-Potential',
};

const CHART_COLORS = ['#6366f1','#0ea5e9','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899'];

// ── Date range helper ─────────────────────────────────────────────
function DateRangeSelector({ value, onChange }) {
  const { preset, start, end } = value;
  const today = new Date().toISOString().slice(0, 10);
  const presets = ['Last 30 Days','Last Month','Last Quarter','Last Year','All Time','Custom Range'];

  const handlePreset = (p) => {
    const t = new Date();
    let s = null, e = null;
    if (p === 'Last 30 Days')  { s = new Date(t - 30*864e5).toISOString().slice(0,10); e = today; }
    if (p === 'Last Month')    { const f=new Date(t.getFullYear(),t.getMonth(),1); s=new Date(f-864e5).toISOString().slice(0,10).slice(0,8)+'01'; e=new Date(f-864e5).toISOString().slice(0,10); }
    if (p === 'Last Quarter')  { s = new Date(t - 90*864e5).toISOString().slice(0,10); e = today; }
    if (p === 'Last Year')     { s = new Date(t - 365*864e5).toISOString().slice(0,10); e = today; }
    onChange({ preset: p, start: s, end: e });
  };

  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <div className="form-group" style={{ margin: 0, minWidth: 160 }}>
        <label className="form-label">Time Period</label>
        <select className="form-select" value={preset} onChange={(e) => handlePreset(e.target.value)} id="report-period-select">
          {presets.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
      {preset === 'Custom Range' && (
        <>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">Start</label>
            <input type="date" className="form-input" value={start || ''} onChange={(e) => onChange({ ...value, start: e.target.value })} id="report-start-date" />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">End</label>
            <input type="date" className="form-input" value={end || ''} onChange={(e) => onChange({ ...value, end: e.target.value })} id="report-end-date" />
          </div>
        </>
      )}
    </div>
  );
}

// ── Download docx helper ──────────────────────────────────────────
function downloadDocx(b64, filename) {
  const bin  = atob(b64);
  const buf  = new Uint8Array(bin.length).map((_, i) => bin.charCodeAt(i));
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a'); a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── Narrative Box ─────────────────────────────────────────────────
function Narrative({ text }) {
  if (!text) return null;
  return (
    <div style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.07) 0%, rgba(14,165,233,0.05) 100%)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 10, padding: '16px 20px', marginTop: 20 }}>
      <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.8px', color: 'var(--primary-light)', marginBottom: 8 }}>AI Analysis Narrative</div>
      <p style={{ fontSize: '0.9rem', lineHeight: 1.7, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}>{text}</p>
    </div>
  );
}

// ── Metric Grid ───────────────────────────────────────────────────
function MetricGrid({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
      {items.map(({ label, value }) => (
        <div key={label} className="glass-card" style={{ padding: '14px 16px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, background: 'linear-gradient(135deg, var(--text-primary), var(--primary-light))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>{value ?? '—'}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.6px', marginTop: 4 }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

// ── Tab: Lead Journey ─────────────────────────────────────────────
function LeadJourneyTab({ leads }) {
  const [selId, setSelId] = useState('');
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    if (!selId) { toast.error('Select a lead'); return; }
    setLoading(true);
    try {
      const d = await getLeadJourneyReport(selId);
      setData(d);
    } catch (err) {
      const s = err.response?.status;
      if (s === 403) toast.error('You can only view reports for your assigned leads.');
      else toast.error(err.response?.data?.detail || 'Report generation failed');
    } finally { setLoading(false); }
  };

  const byType = data?.metrics?.by_event_type || {};
  const chartData = Object.entries(byType).map(([k, v]) => ({ name: k.replace(/_/g,' '), value: v }));

  return (
    <div>
      <h3 style={{ marginBottom: 6 }}>Lead Journey Report</h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20, fontSize: '0.875rem' }}>AI-generated narrative of a lead's full engagement history.</p>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 20, flexWrap: 'wrap' }}>
        <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 200 }}>
          <label className="form-label">Select Lead</label>
          <select className="form-select" value={selId} onChange={(e) => { setSelId(e.target.value); setData(null); }} id="journey-lead-select">
            <option value="">Choose a lead…</option>
            {leads.map((l) => <option key={l.id} value={l.id}>{l.name} {l.profession ? `(${l.profession})` : ''}</option>)}
          </select>
        </div>
        <button className="btn btn-primary" onClick={generate} disabled={loading || !selId} id="generate-journey-btn">
          {loading ? <><Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> Generating…</> : <><FileText size={15} /> Generate Report</>}
        </button>
      </div>

      {data && (
        <>
          <h3>{data.lead_name} — Journey Analysis</h3>
          <MetricGrid items={[{ label: 'Timeline Events', value: data.metrics?.total_events }]} />
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData}>
                <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border)', borderRadius: 8 }} />
                <Bar dataKey="value" fill="var(--primary)" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
          <Narrative text={data.narrative} />
          {data.docx_b64 && (
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 16 }} onClick={() => downloadDocx(data.docx_b64, `lead_journey_${selId}.docx`)} id="journey-download-btn">
              <Download size={14} /> Download .docx
            </button>
          )}
        </>
      )}
    </div>
  );
}

// ── Tab: Periodic Leads ───────────────────────────────────────────
function PeriodicLeadsTab({ isManagerOrAdmin, isAdmin, allUsers, reps }) {
  const [dateRange, setDateRange] = useState({ preset: 'Last 30 Days', start: null, end: null });
  const [scopeUserId, setScopeUserId] = useState('');
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateRange.start) params.start_date = dateRange.start;
      if (dateRange.end)   params.end_date   = dateRange.end;
      if (dateRange.preset && dateRange.preset !== 'Custom Range') params.period_label = dateRange.preset;
      if (scopeUserId) params.user_id = scopeUserId;
      const d = await getPeriodicLeadsReport(params);
      setData(d);
    } catch (err) { toast.error(err.response?.data?.detail || 'Report generation failed'); }
    finally { setLoading(false); }
  };

  const m = data?.metrics || {};
  const byStatus = Object.entries(m.by_status || {}).map(([k, v]) => ({ name: STATUS_LABELS[k] || k, value: v, color: STATUS_COLORS[k] || '#64748b' }));
  const bySource = Object.entries(m.by_source || {}).map(([k, v]) => ({ name: k, value: v }));

  return (
    <div>
      <h3 style={{ marginBottom: 6 }}>Periodic Leads Report</h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20, fontSize: '0.875rem' }}>Pipeline distribution and individual lead highlights for the selected period.</p>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20, alignItems: 'flex-end' }}>
        {isManagerOrAdmin && (
          <div className="form-group" style={{ margin: 0, minWidth: 160 }}>
            <label className="form-label">Scope</label>
            <select className="form-select" value={scopeUserId} onChange={(e) => setScopeUserId(e.target.value)} id="periodic-scope-select">
              <option value="">{isAdmin ? 'Firm-Wide' : 'All Team'}</option>
              {(isAdmin ? allUsers : reps).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </div>
        )}
        <DateRangeSelector value={dateRange} onChange={setDateRange} />
        <button className="btn btn-primary" onClick={generate} disabled={loading} id="generate-periodic-btn">
          {loading ? <><Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> Generating…</> : <><BarChart3 size={15} /> Generate</>}
        </button>
      </div>

      {data && (
        <>
          <h3>{m.target_name} — {m.period_label}</h3>
          <MetricGrid items={[
            { label: 'Total Leads',     value: m.total_leads },
            { label: 'Converted',       value: m.converted_leads },
            { label: 'Conversion Rate', value: `${m.conversion_rate}%` },
            { label: 'Pipeline Stages', value: Object.keys(m.by_status || {}).length },
          ]} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {byStatus.length > 0 && (
              <div className="glass-card" style={{ padding: 16 }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 10, textTransform: 'uppercase' }}>Pipeline Distribution</div>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={byStatus} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3}>
                      {byStatus.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border)', borderRadius: 8 }} />
                    <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
            {bySource.length > 0 && (
              <div className="glass-card" style={{ padding: 16 }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 10, textTransform: 'uppercase' }}>Leads by Channel</div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={bySource} layout="vertical">
                    <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} width={90} />
                    <Tooltip contentStyle={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border)', borderRadius: 8 }} />
                    <Bar dataKey="value" radius={[0,4,4,0]}>
                      {bySource.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
          <Narrative text={data.narrative} />
          {data.docx_b64 && (
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 16 }} onClick={() => downloadDocx(data.docx_b64, 'periodic_leads_report.docx')} id="periodic-download-btn">
              <Download size={14} /> Download .docx
            </button>
          )}
        </>
      )}
    </div>
  );
}

// ── Tab: Individual Performance ───────────────────────────────────
function PerformanceTab({ isAdmin, pool, poolLabel }) {
  const [selUid, setSelUid]   = useState('');
  const [dateRange, setDateRange] = useState({ preset: 'Last 30 Days', start: null, end: null });
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    if (!selUid) { toast.error('Select a user'); return; }
    setLoading(true);
    try {
      const params = {};
      if (dateRange.start) params.start_date = dateRange.start;
      if (dateRange.end)   params.end_date   = dateRange.end;
      if (dateRange.preset && dateRange.preset !== 'Custom Range') params.period_label = dateRange.preset;
      const d = await getUserPerformanceReport(selUid, params);
      setData(d);
    } catch (err) {
      if (err.response?.status === 403) toast.error('You can only view reports for your direct reports.');
      else toast.error(err.response?.data?.detail || 'Report generation failed');
    } finally { setLoading(false); }
  };

  const m = data?.metrics || {};
  const byStatus = Object.entries(m.by_status || {}).map(([k, v]) => ({ name: STATUS_LABELS[k] || k, value: v, color: STATUS_COLORS[k] || '#64748b' }));

  return (
    <div>
      <h3 style={{ marginBottom: 6 }}>Individual Performance Review</h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20, fontSize: '0.875rem' }}>AI-generated individual performance covering leads, conversions, appointments, and tasks.</p>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20, alignItems: 'flex-end' }}>
        <div className="form-group" style={{ margin: 0, minWidth: 200 }}>
          <label className="form-label">{poolLabel}</label>
          <select className="form-select" value={selUid} onChange={(e) => { setSelUid(e.target.value); setData(null); }} id="perf-user-select">
            <option value="">Choose…</option>
            {pool.map((u) => <option key={u.id} value={u.id}>{u.name} ({(u.role||'').replace('_',' ')})</option>)}
          </select>
        </div>
        <DateRangeSelector value={dateRange} onChange={setDateRange} />
        <button className="btn btn-primary" onClick={generate} disabled={loading || !selUid} id="generate-perf-btn">
          {loading ? <><Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> Generating…</> : <><TrendingUp size={15} /> Generate</>}
        </button>
      </div>

      {data && (
        <>
          <h3>{m.user_name} — {data.period_label}</h3>
          <MetricGrid items={[
            { label: 'Leads Assigned',  value: m.total_leads_assigned },
            { label: 'Converted',       value: m.converted_leads },
            { label: 'Conversion Rate', value: `${m.conversion_rate}%` },
            { label: 'Appointments',    value: m.total_appointments },
            { label: 'Total Tasks',     value: m.total_tasks },
            { label: 'Tasks Completed', value: m.tasks_completed },
            { label: 'Task Completion', value: `${m.task_completion_rate}%` },
          ]} />
          {byStatus.length > 0 && (
            <div className="glass-card" style={{ padding: 16, marginBottom: 16 }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 10, textTransform: 'uppercase' }}>Lead Pipeline Breakdown</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byStatus}>
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border)', borderRadius: 8 }} />
                  <Bar dataKey="value" radius={[4,4,0,0]}>
                    {byStatus.map((e, i) => <Cell key={i} fill={e.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <Narrative text={data.narrative} />
          {data.docx_b64 && (
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 16 }} onClick={() => downloadDocx(data.docx_b64, `performance_${selUid}.docx`)} id="perf-download-btn">
              <Download size={14} /> Download .docx
            </button>
          )}
        </>
      )}
    </div>
  );
}

// ── Tab: Team Digest ──────────────────────────────────────────────
function TeamDigestTab({ isAdmin, managers }) {
  const [dateRange, setDateRange] = useState({ preset: 'Last 30 Days', start: null, end: null });
  const [mgrFilter, setMgrFilter] = useState('');
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateRange.start) params.start_date = dateRange.start;
      if (dateRange.end)   params.end_date   = dateRange.end;
      if (dateRange.preset && dateRange.preset !== 'Custom Range') params.period_label = dateRange.preset;
      if (mgrFilter) params.manager_id = mgrFilter;
      const d = await getTeamPerformanceReport(params);
      setData(d);
    } catch (err) { toast.error(err.response?.data?.detail || 'Report generation failed'); }
    finally { setLoading(false); }
  };

  const td = data?.metrics || {};
  const members = (td.members || []);
  const memberChart = members.map((m) => ({ name: m.user_name, leads: m.total_leads_assigned, converted: m.converted_leads, tasks: m.tasks_completed }));

  return (
    <div>
      <h3 style={{ marginBottom: 6 }}>Team Performance Digest</h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20, fontSize: '0.875rem' }}>Aggregate team metrics with AI analysis — comparative performance, bottlenecks, and recommendations.</p>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20, alignItems: 'flex-end' }}>
        {isAdmin && managers.length > 0 && (
          <div className="form-group" style={{ margin: 0, minWidth: 200 }}>
            <label className="form-label">Filter by Manager Team</label>
            <select className="form-select" value={mgrFilter} onChange={(e) => setMgrFilter(e.target.value)} id="team-mgr-filter">
              <option value="">All Managers (Firm-Wide)</option>
              {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}
        <DateRangeSelector value={dateRange} onChange={setDateRange} />
        <button className="btn btn-primary" onClick={generate} disabled={loading} id="generate-team-btn">
          {loading ? <><Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> Generating…</> : <><Users size={15} /> Generate</>}
        </button>
      </div>

      {data && (
        <>
          <h3>{td.team_label || 'Team'} — {data.period_label}</h3>
          <MetricGrid items={[
            { label: 'Team Members',  value: data.member_count },
            { label: 'Total Leads',   value: td.totals?.total_leads },
            { label: 'Converted',     value: td.totals?.converted_leads },
            { label: 'Avg Conversion',value: `${td.totals?.avg_conversion_rate || 0}%` },
          ]} />

          {memberChart.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div className="glass-card" style={{ padding: 16 }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 10, textTransform: 'uppercase' }}>Leads per Member</div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={memberChart}>
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border)', borderRadius: 8 }} />
                    <Bar dataKey="leads" fill="var(--primary)" radius={[4,4,0,0]} name="Leads" />
                    <Bar dataKey="converted" fill="var(--success)" radius={[4,4,0,0]} name="Converted" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="glass-card" style={{ padding: 16 }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 10, textTransform: 'uppercase' }}>Tasks Completed</div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={memberChart}>
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border)', borderRadius: 8 }} />
                    <Bar dataKey="tasks" fill="var(--accent)" radius={[4,4,0,0]} name="Tasks Done" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
          <Narrative text={data.narrative} />
          {data.docx_b64 && (
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 16 }} onClick={() => downloadDocx(data.docx_b64, 'team_digest.docx')} id="team-download-btn">
              <Download size={14} /> Download .docx
            </button>
          )}
        </>
      )}
    </div>
  );
}

// ── Main Reports Page ─────────────────────────────────────────────
export default function ReportsPage() {
  const { user, isAdmin, isManager, isManagerOrAdmin } = useAuth();
  const [leads, setLeads]       = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [tab, setTab]           = useState('journey');
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    Promise.all([
      getLeads({ limit: 1000 }),
      isManagerOrAdmin ? getUsers() : Promise.resolve([]),
    ]).then(([l, u]) => { setLeads(l); setAllUsers(u); })
      .catch(() => toast.error('Failed to load data'))
      .finally(() => setLoading(false));
  }, [isManagerOrAdmin]);

  const reps     = allUsers.filter((u) => u.role === 'sales_rep');
  const managers = allUsers.filter((u) => u.role === 'manager');
  const myReps   = isManager ? reps.filter((r) => r.manager_id === user?.id) : reps;
  const perfPool = isAdmin ? allUsers : myReps;

  const TABS = [
    { key: 'journey',   label: 'Lead Journey' },
    { key: 'periodic',  label: 'Periodic Leads' },
    ...(isManagerOrAdmin ? [
      { key: 'performance', label: isManager ? 'Rep Performance' : 'Individual Performance' },
      { key: 'team',        label: 'Team Digest' },
    ] : []),
  ];

  return (
    <>
      <Navbar title="Reports" />
      <div className="page-container">
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ marginBottom: 4 }}>Reports & Analytics</h1>
          <p style={{ color: 'var(--text-muted)' }}>Generate AI-powered reports and download .docx summaries.</p>
        </div>

        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={`tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)} id={`report-tab-${t.key}`}>
              {t.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="loading-center"><div className="spinner" /> Loading…</div>
        ) : (
          <div className="glass-card" style={{ padding: 28 }}>
            {tab === 'journey'     && <LeadJourneyTab leads={leads} />}
            {tab === 'periodic'    && <PeriodicLeadsTab isManagerOrAdmin={isManagerOrAdmin} isAdmin={isAdmin} allUsers={allUsers} reps={myReps} />}
            {tab === 'performance' && <PerformanceTab isAdmin={isAdmin} pool={perfPool} poolLabel={isAdmin ? 'Select User' : 'Select Sales Rep'} />}
            {tab === 'team'        && <TeamDigestTab isAdmin={isAdmin} managers={managers} />}
          </div>
        )}
      </div>
    </>
  );
}
