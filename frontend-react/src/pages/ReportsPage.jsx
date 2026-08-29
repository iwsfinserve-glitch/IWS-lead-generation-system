import { useState, useEffect } from 'react';
import { FileText, Download, Loader2, BarChart3, TrendingUp, Users } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, LineChart, Line, AreaChart, Area, CartesianGrid, ComposedChart,
} from 'recharts';
import {
  getLeadJourneyReport, getPeriodicLeadsReport,
  getUserPerformanceReport, getTeamPerformanceReport, getJourneyLeads,
} from '../api/reportsApi';
import { getUsers } from '../api/usersApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

// ── Brand & colour tokens ─────────────────────────────────────────
const BRAND_BLUE   = '#053abb';
const BRAND_GREEN  = '#10b981';
const BRAND_AMBER  = '#f59e0b';
const BRAND_PURPLE = '#8b5cf6';
const BRAND_RED    = '#ef4444';
const BRAND_TEAL   = '#0ea5e9';
const BRAND_PINK   = '#ec4899';

const STATUS_COLORS = {
  new: BRAND_TEAL, in_progress: BRAND_AMBER, potential: BRAND_PURPLE,
  converted_to_investor: BRAND_GREEN, existing_investor: '#059669', non_potential: BRAND_RED,
};
const STATUS_LABELS = {
  new: 'New', in_progress: 'In Progress', potential: 'Potential',
  converted_to_investor: 'Converted', existing_investor: 'Existing Investor', non_potential: 'Non-Potential',
};

const CHART_COLORS = [BRAND_BLUE, BRAND_GREEN, BRAND_AMBER, BRAND_PURPLE, BRAND_RED, BRAND_TEAL, BRAND_PINK];

// Custom tooltip style shared across charts
const tooltipStyle = {
  contentStyle: {
    background: 'var(--bg-card-solid)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    boxShadow: '0 8px 32px rgba(5,58,187,0.12)',
    fontSize: '0.8rem',
  },
};

// ── Section Header ────────────────────────────────────────────────
function ChartSection({ title, children, cols = 1 }) {
  return (
    <div className="glass-card" style={{ padding: 16, marginBottom: 16 }}>
      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 14, textTransform: 'uppercase', letterSpacing: '0.8px' }}>
        {title}
      </div>
      <div style={cols === 2 ? { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 } : {}}>
        {children}
      </div>
    </div>
  );
}

// ── Date range helper ─────────────────────────────────────────────
function DateRangeSelector({ value, onChange }) {
  const { preset, start, end } = value;
  const today = new Date().toISOString().slice(0, 10);
  const presets = ['Last 30 Days', 'Last Month', 'Last Quarter', 'Last Year', 'All Time', 'Custom Range'];

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

  const renderInline = (str) => {
    const parts = str.split(/(\*\*.*?\*\*|__.*?__)/g);
    return parts.map((part, i) => {
      if ((part.startsWith('**') && part.endsWith('**')) || (part.startsWith('__') && part.endsWith('__'))) {
        return (
          <strong key={i} style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
            {part.slice(2, -2)}
          </strong>
        );
      }
      return part;
    });
  };

  const lines = text.split('\n');
  const elements = [];
  let listBuffer = [];

  const flushList = () => {
    if (listBuffer.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} style={{ margin: '6px 0 10px 18px', paddingLeft: 6, color: 'var(--text-secondary)', fontSize: '0.88rem', lineHeight: 1.65 }}>
          {listBuffer.map((item, idx) => (
            <li key={idx} style={{ marginBottom: 3 }}>{renderInline(item)}</li>
          ))}
        </ul>
      );
      listBuffer = [];
    }
  };

  lines.forEach((rawLine, idx) => {
    const line = rawLine.trim();

    if (!line) {
      flushList();
      return;
    }

    // Horizontal Rule
    if (line === '---' || line === '***' || line === '___' || /^[-*_]{3,}$/.test(line)) {
      flushList();
      elements.push(
        <hr key={`hr-${idx}`} style={{ border: 'none', borderTop: '1px solid rgba(5,58,187,0.12)', margin: '14px 0' }} />
      );
      return;
    }

    // Markdown Headings (e.g. ### Heading or ## Heading or # Heading)
    const headingMatch = line.match(/^(#{1,6})\s*(.*)/);
    if (headingMatch) {
      flushList();
      const level = headingMatch[1].length;
      const cleanTitle = headingMatch[2].replace(/\*\*/g, '').replace(/__/g, '').trim();
      elements.push(
        <div
          key={`h-${idx}`}
          style={{
            fontSize: level <= 2 ? '1.02rem' : '0.92rem',
            fontWeight: 700,
            color: 'var(--primary)',
            marginTop: 16,
            marginBottom: 6,
            letterSpacing: '0.3px',
          }}
        >
          {cleanTitle}
        </div>
      );
      return;
    }

    // Bullet items
    const bulletMatch = line.match(/^[\*\-\•]\s+(.*)/);
    if (bulletMatch) {
      listBuffer.push(bulletMatch[1]);
      return;
    }

    // Numbered list
    const numMatch = line.match(/^(\d+[\.\)])\s+(.*)/);
    if (numMatch) {
      flushList();
      elements.push(
        <div key={`num-${idx}`} style={{ margin: '4px 0', fontSize: '0.88rem', lineHeight: 1.65, color: 'var(--text-secondary)' }}>
          <strong style={{ color: 'var(--primary)', marginRight: 6 }}>{numMatch[1]}</strong>
          {renderInline(numMatch[2])}
        </div>
      );
      return;
    }

    // Regular line / Memorandum line
    flushList();
    elements.push(
      <p key={`p-${idx}`} style={{ fontSize: '0.88rem', lineHeight: 1.65, color: 'var(--text-secondary)', margin: '5px 0' }}>
        {renderInline(line)}
      </p>
    );
  });

  flushList();

  return (
    <div style={{ background: 'linear-gradient(135deg, rgba(5,58,187,0.06) 0%, rgba(14,165,233,0.04) 100%)', border: '1px solid rgba(5,58,187,0.18)', borderRadius: 10, padding: '18px 22px', marginTop: 20 }}>
      <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.8px', color: BRAND_BLUE, marginBottom: 12 }}>
        AI Analysis Narrative
      </div>
      <div>{elements}</div>
    </div>
  );
}

// ── Metric Grid ───────────────────────────────────────────────────
function MetricGrid({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12, marginBottom: 20 }}>
      {items.map(({ label, value, accent }) => (
        <div key={label} className="glass-card" style={{ padding: '14px 16px', textAlign: 'center', borderTop: `3px solid ${accent || BRAND_BLUE}` }}>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, background: `linear-gradient(135deg, ${accent || BRAND_BLUE}, ${BRAND_TEAL})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>{value ?? '—'}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.6px', marginTop: 4 }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

// ── Custom dot for line charts ────────────────────────────────────
const BrandDot = (props) => {
  const { cx, cy, fill } = props;
  return <circle cx={cx} cy={cy} r={4} fill="white" stroke={fill} strokeWidth={2} />;
};

// ── Tab: Lead Journey ─────────────────────────────────────────────
function LeadJourneyTab({ journeyLeads, journeyLeadsLoading }) {
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

  const byType     = data?.metrics?.by_event_type || {};
  const chartData  = Object.entries(byType).map(([k, v]) => ({ name: k.replace(/_/g,' '), value: v }));
  const timeData   = data?.metrics?.events_over_time || [];

  return (
    <div>
      <h3 style={{ marginBottom: 6 }}>Lead Journey Report</h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20, fontSize: '0.875rem' }}>AI-generated narrative of a lead's full engagement history with interactive visuals.</p>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 20, flexWrap: 'wrap' }}>
        <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 200 }}>
          <label className="form-label">Select Lead</label>
          {journeyLeadsLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              <Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite' }} /> Loading leads…
            </div>
          ) : (
            <select className="form-select" value={selId} onChange={(e) => { setSelId(e.target.value); setData(null); }} id="journey-lead-select">
              <option value="">Choose a lead…</option>
              {journeyLeads.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}{l.profession ? ` (${l.profession})` : ''} — {STATUS_LABELS[l.status] || l.status}
                </option>
              ))}
            </select>
          )}
        </div>
        <button className="btn btn-primary" onClick={generate} disabled={loading || !selId} id="generate-journey-btn">
          {loading ? <><Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> Generating…</> : <><FileText size={15} /> Generate Report</>}
        </button>
      </div>

      {data && (
        <>
          <h3 style={{ marginBottom: 4 }}>{data.lead_name} — Journey Analysis</h3>
          {data.metrics?.lead_profession && (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 16 }}>
              {data.metrics.lead_profession} · {STATUS_LABELS[data.metrics.lead_status] || data.metrics.lead_status}
              {data.metrics.lead_source ? ` · Source: ${data.metrics.lead_source}` : ''}
            </p>
          )}
          <MetricGrid items={[
            { label: 'Total Events',   value: data.metrics?.total_events,   accent: BRAND_BLUE },
            { label: 'Event Types',    value: chartData.length,             accent: BRAND_PURPLE },
            { label: 'Timeline Span',  value: timeData.length > 1 ? `${timeData.length} days` : timeData.length === 1 ? '1 day' : '—', accent: BRAND_TEAL },
          ]} />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            {chartData.length > 0 && (
              <ChartSection title="Events by Interaction Type">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} width={100} />
                    <Tooltip {...tooltipStyle} />
                    <Bar dataKey="value" radius={[0, 5, 5, 0]} label={{ position: 'right', fill: 'var(--text-muted)', fontSize: 10 }}>
                      {chartData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartSection>
            )}

            {timeData.length > 1 && (
              <ChartSection title="Interaction Activity Over Time">
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={timeData} margin={{ left: 0, right: 8 }}>
                    <defs>
                      <linearGradient id="journeyGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={BRAND_BLUE} stopOpacity={0.25} />
                        <stop offset="95%" stopColor={BRAND_BLUE} stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 9 }} tickFormatter={(v) => v.slice(5)} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                    <Tooltip {...tooltipStyle} labelFormatter={(l) => `Date: ${l}`} />
                    <Area type="monotone" dataKey="events" stroke={BRAND_BLUE} strokeWidth={2.5} fill="url(#journeyGrad)" dot={<BrandDot fill={BRAND_BLUE} />} name="Events" />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartSection>
            )}
          </div>

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
  const timeData = m.leads_over_time || [];

  return (
    <div>
      <h3 style={{ marginBottom: 6 }}>Periodic Leads Report</h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: 20, fontSize: '0.875rem' }}>Pipeline distribution, trend analysis, and individual lead highlights for the selected period.</p>

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
          <h3 style={{ marginBottom: 4 }}>{m.target_name} — {m.period_label}</h3>
          <MetricGrid items={[
            { label: 'Total Leads',     value: m.total_leads,         accent: BRAND_BLUE },
            { label: 'Converted',       value: m.converted_leads,     accent: BRAND_GREEN },
            { label: 'Conversion Rate', value: `${m.conversion_rate}%`, accent: BRAND_AMBER },
            { label: 'Pipeline Stages', value: Object.keys(m.by_status || {}).length, accent: BRAND_PURPLE },
          ]} />

          {/* Row 1: pipeline pie + channel bar */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            {byStatus.length > 0 && (
              <ChartSection title="Pipeline Distribution">
                <ResponsiveContainer width="100%" height={230}>
                  <PieChart>
                    <Pie data={byStatus} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={88} paddingAngle={3}>
                      {byStatus.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                    <Tooltip {...tooltipStyle} />
                    <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>} />
                  </PieChart>
                </ResponsiveContainer>
              </ChartSection>
            )}
            {bySource.length > 0 && (
              <ChartSection title="Leads by Acquisition Channel">
                <ResponsiveContainer width="100%" height={230}>
                  <BarChart data={bySource} layout="vertical" margin={{ left: 0, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} width={90} />
                    <Tooltip {...tooltipStyle} />
                    <Bar dataKey="value" radius={[0, 5, 5, 0]}>
                      {bySource.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartSection>
            )}
          </div>

          {/* Row 2: leads over time (full width area chart) */}
          {timeData.length > 1 && (
            <ChartSection title="Leads Created vs Converted Over Time">
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={timeData} margin={{ left: 0, right: 8 }}>
                  <defs>
                    <linearGradient id="createdGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={BRAND_BLUE} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={BRAND_BLUE} stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="convertedGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={BRAND_GREEN} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={BRAND_GREEN} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 9 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip {...tooltipStyle} labelFormatter={(l) => `Date: ${l}`} />
                  <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>} />
                  <Area type="monotone" dataKey="created"   stroke={BRAND_BLUE}  strokeWidth={2.5} fill="url(#createdGrad)"   dot={<BrandDot fill={BRAND_BLUE} />}  name="Created" />
                  <Area type="monotone" dataKey="converted" stroke={BRAND_GREEN} strokeWidth={2.5} fill="url(#convertedGrad)" dot={<BrandDot fill={BRAND_GREEN} />} name="Converted" />
                </AreaChart>
              </ResponsiveContainer>
            </ChartSection>
          )}

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
  const byStatus  = Object.entries(m.by_status || {}).map(([k, v]) => ({ name: STATUS_LABELS[k] || k, value: v, color: STATUS_COLORS[k] || '#64748b' }));
  const tasksTrend = m.tasks_over_time || [];

  // Build radar-style summary for task/appointment combo chart
  const activityData = [
    { name: 'Leads',        value: m.total_leads_assigned || 0 },
    { name: 'Converted',    value: m.converted_leads || 0 },
    { name: 'Appointments', value: m.total_appointments || 0 },
    { name: 'Tasks Done',   value: m.tasks_completed || 0 },
  ];

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
          <h3 style={{ marginBottom: 4 }}>{m.user_name} — {data.period_label}</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 16 }}>{(m.user_role || '').replace('_', ' ')}</p>
          <MetricGrid items={[
            { label: 'Leads Assigned',  value: m.total_leads_assigned,               accent: BRAND_BLUE },
            { label: 'Converted',       value: m.converted_leads,                    accent: BRAND_GREEN },
            { label: 'Conversion Rate', value: `${m.conversion_rate}%`,              accent: BRAND_AMBER },
            { label: 'Appointments',    value: m.total_appointments,                 accent: BRAND_PURPLE },
            { label: 'Tasks Assigned',  value: m.total_tasks,                        accent: BRAND_TEAL },
            { label: 'Tasks Completed', value: m.tasks_completed,                    accent: BRAND_GREEN },
            { label: 'Task Completion', value: `${m.task_completion_rate}%`,         accent: m.task_completion_rate >= 70 ? BRAND_GREEN : BRAND_RED },
            { label: 'Interactions',    value: m.total_interactions,                 accent: BRAND_PINK },
          ]} />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            {/* Pipeline breakdown (bar) */}
            {byStatus.length > 0 && (
              <ChartSection title="Lead Pipeline Breakdown">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={byStatus} margin={{ top: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                    <Tooltip {...tooltipStyle} />
                    <Bar dataKey="value" radius={[5, 5, 0, 0]}>
                      {byStatus.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartSection>
            )}

            {/* Activity overview (composed bar) */}
            <ChartSection title="Activity Overview">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={activityData} margin={{ top: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip {...tooltipStyle} />
                  <Bar dataKey="value" radius={[5, 5, 0, 0]}>
                    {activityData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartSection>
          </div>

          {/* Task completion trend (full-width line chart) */}
          {tasksTrend.length > 1 && (
            <ChartSection title="Task Assignment &amp; Completion Trend">
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={tasksTrend} margin={{ left: 0, right: 8 }}>
                  <defs>
                    <linearGradient id="assignedGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={BRAND_BLUE} stopOpacity={0.22} />
                      <stop offset="95%" stopColor={BRAND_BLUE} stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="completedGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={BRAND_GREEN} stopOpacity={0.28} />
                      <stop offset="95%" stopColor={BRAND_GREEN} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 9 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip {...tooltipStyle} labelFormatter={(l) => `Date: ${l}`} />
                  <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>} />
                  <Area type="monotone" dataKey="assigned"  stroke={BRAND_BLUE}  strokeWidth={2.5} fill="url(#assignedGrad)"  dot={<BrandDot fill={BRAND_BLUE} />}  name="Assigned" />
                  <Area type="monotone" dataKey="completed" stroke={BRAND_GREEN} strokeWidth={2.5} fill="url(#completedGrad)" dot={<BrandDot fill={BRAND_GREEN} />} name="Completed" />
                </AreaChart>
              </ResponsiveContainer>
            </ChartSection>
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
  const memberChart = members.map((m) => ({ name: m.user_name?.split(' ')[0] || m.user_name, leads: m.total_leads_assigned, converted: m.converted_leads, tasks: m.tasks_completed, appointments: m.total_appointments }));
  const memberStatusChart = td.member_status_chart || [];

  // All status keys that appear across any member
  const allStatuses = ['new', 'in_progress', 'potential', 'converted_to_investor', 'existing_investor', 'non_potential'];
  const usedStatuses = allStatuses.filter((s) => memberStatusChart.some((row) => (row[s] || 0) > 0));

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
          <h3 style={{ marginBottom: 4 }}>{td.team_label || 'Team'} — {data.period_label}</h3>
          <MetricGrid items={[
            { label: 'Team Members',   value: data.member_count,                     accent: BRAND_BLUE },
            { label: 'Total Leads',    value: td.totals?.total_leads,                accent: BRAND_TEAL },
            { label: 'Converted',      value: td.totals?.converted_leads,            accent: BRAND_GREEN },
            { label: 'Avg Conversion', value: `${td.totals?.avg_conversion_rate || 0}%`, accent: BRAND_AMBER },
            { label: 'Appointments',   value: td.totals?.total_appointments,         accent: BRAND_PURPLE },
            { label: 'Tasks Done',     value: td.totals?.tasks_completed,            accent: BRAND_GREEN },
          ]} />

          {memberChart.length > 0 && (
            <>
              {/* Row 1: leads per member + tasks per member */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                <ChartSection title="Leads Assigned vs Converted per Member">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={memberChart} margin={{ top: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                      <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                      <Tooltip {...tooltipStyle} />
                      <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>} />
                      <Bar dataKey="leads"     fill={BRAND_BLUE}  radius={[4,4,0,0]} name="Assigned" />
                      <Bar dataKey="converted" fill={BRAND_GREEN} radius={[4,4,0,0]} name="Converted" />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartSection>

                <ChartSection title="Tasks Completed &amp; Appointments per Member">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={memberChart} margin={{ top: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                      <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                      <Tooltip {...tooltipStyle} />
                      <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>} />
                      <Bar dataKey="tasks"        fill={BRAND_AMBER}  radius={[4,4,0,0]} name="Tasks Done" />
                      <Bar dataKey="appointments" fill={BRAND_PURPLE} radius={[4,4,0,0]} name="Appointments" />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartSection>
              </div>

              {/* Row 2: Stacked status breakdown per member (full width) */}
              {usedStatuses.length > 0 && memberStatusChart.length > 0 && (
                <ChartSection title="Lead Status Distribution per Member (Stacked)">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={memberStatusChart} margin={{ top: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                      <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} allowDecimals={false} />
                      <Tooltip {...tooltipStyle} />
                      <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>} />
                      {usedStatuses.map((status) => (
                        <Bar key={status} dataKey={status} stackId="status" fill={STATUS_COLORS[status] || '#94a3b8'} name={STATUS_LABELS[status] || status} />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </ChartSection>
              )}
            </>
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
  const [allUsers, setAllUsers]                         = useState([]);
  const [journeyLeads, setJourneyLeads]                 = useState([]);
  const [journeyLeadsLoading, setJourneyLeadsLoading]   = useState(true);
  const [tab, setTab]                                   = useState('journey');
  const [loading, setLoading]                           = useState(true);

  useEffect(() => {
    Promise.all([
      isManagerOrAdmin ? getUsers() : Promise.resolve([]),
    ]).then(([u]) => { setAllUsers(u); })
      .catch(() => toast.error('Failed to load data'))
      .finally(() => setLoading(false));
  }, [isManagerOrAdmin]);

  useEffect(() => {
    // Load the RBAC-filtered leads for Lead Journey dropdown
    setJourneyLeadsLoading(true);
    getJourneyLeads()
      .then((leads) => setJourneyLeads(leads))
      .catch(() => toast.error('Failed to load leads for dropdown'))
      .finally(() => setJourneyLeadsLoading(false));
  }, []);

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
          <h1 style={{ marginBottom: 4 }}>Reports &amp; Analytics</h1>
          <p style={{ color: 'var(--text-muted)' }}>Generate AI-powered visual reports and download .docx summaries.</p>
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
            {tab === 'journey'     && <LeadJourneyTab journeyLeads={journeyLeads} journeyLeadsLoading={journeyLeadsLoading} />}
            {tab === 'periodic'    && <PeriodicLeadsTab isManagerOrAdmin={isManagerOrAdmin} isAdmin={isAdmin} allUsers={allUsers} reps={myReps} />}
            {tab === 'performance' && <PerformanceTab isAdmin={isAdmin} pool={perfPool} poolLabel={isAdmin ? 'Select User' : 'Select RM'} />}
            {tab === 'team'        && <TeamDigestTab isAdmin={isAdmin} managers={managers} />}
          </div>
        )}
      </div>
    </>
  );
}
