import { useState, useEffect, useCallback } from 'react';
import { Plus, Calendar as CalIcon, List, CheckCircle, ExternalLink, RefreshCw, Unlink } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import Pagination from '../components/common/Pagination';
import ScheduleAppointmentModal from '../components/modals/ScheduleAppointmentModal';
import { getAppointments, updateAppointment } from '../api/appointmentsApi';
import { getGoogleStatus, getGoogleConnectUrl, googleDisconnect, googleSync } from '../api/authApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

const PAGE_SIZE = 10;

const STATUS_BADGE = {
  upcoming:  { bg: 'rgba(59,130,246,0.15)',  color: '#60a5fa',  label: 'Upcoming' },
  pending:   { bg: 'rgba(245,158,11,0.15)',  color: '#fbbf24',  label: 'Pending' },
  completed: { bg: 'rgba(16,185,129,0.15)',  color: '#34d399',  label: 'Completed' },
};

const MODE_BADGE = {
  online:    { bg: 'rgba(99,102,241,0.15)', color: '#818cf8', label: 'Online' },
  in_person: { bg: 'rgba(16,185,129,0.15)', color: '#34d399', label: 'In Person' },
};

// ── Calendar Mini-Grid ─────────────────────────────────────────────
function CalendarView({ appointments, onDayClick }) {
  const [year, setYear]   = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth());

  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

  const firstDay = new Date(year, month, 1);
  let startDow = firstDay.getDay(); // 0=Sun
  startDow = startDow === 0 ? 6 : startDow - 1; // convert to Mon-first
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date();

  const countsByDay = {};
  appointments.forEach((a) => {
    const d = a.start_time?.slice(0, 10);
    const [y, m] = d.split('-').map(Number);
    if (y === year && m === month + 1) {
      const day = parseInt(d.split('-')[2]);
      countsByDay[day] = (countsByDay[day] || 0) + 1;
    }
  });

  const prev = () => {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  };
  const next = () => {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  };

  const cells = Array(startDow).fill(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  return (
    <div>
      {/* Nav */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <button className="btn btn-ghost btn-sm" onClick={prev} id="cal-prev">‹ Prev</button>
        <h3 style={{ margin: 0, fontSize: '1.1rem' }}>{MONTH_NAMES[month]} {year}</h3>
        <button className="btn btn-ghost btn-sm" onClick={next} id="cal-next">Next ›</button>
      </div>

      {/* Day headers */}
      <div className="cal-grid" style={{ marginBottom: 4 }}>
        {dayNames.map((d) => (
          <div key={d} style={{ textAlign: 'center', fontSize: '0.72rem', fontWeight: 700, color: 'var(--primary-light)', padding: '4px 0', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {d}
          </div>
        ))}
      </div>

      {/* Day cells */}
      <div className="cal-grid">
        {cells.map((day, i) => {
          if (day === null) return <div key={`e-${i}`} className="cal-cell empty" />;
          const isToday = year === today.getFullYear() && month === today.getMonth() && day === today.getDate();
          const count   = countsByDay[day] || 0;
          const dateStr = `${year}-${String(month + 1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
          return (
            <div key={day} className={`cal-cell ${isToday ? 'today' : ''}`} onClick={() => count > 0 && onDayClick(dateStr, appointments.filter((a) => a.start_time?.startsWith(dateStr)))} id={`cal-day-${dateStr}`}>
              <div className="cal-day-num">{day}</div>
              {count > 0 && <div className="cal-dot">{count}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Appointment Card ───────────────────────────────────────────────
function ApptCard({ appt, onMarkComplete }) {
  const s = STATUS_BADGE[appt.status] || STATUS_BADGE.upcoming;
  const m = MODE_BADGE[appt.mode] || MODE_BADGE.online;
  const start = new Date(appt.start_time);
  const end   = new Date(appt.end_time);

  return (
    <div className="glass-card" style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, alignItems: 'start' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{appt.title}</span>
          <span style={{ padding: '2px 8px', borderRadius: 12, fontSize: '0.7rem', fontWeight: 700, background: s.bg, color: s.color }}>{s.label}</span>
          <span style={{ padding: '2px 8px', borderRadius: 12, fontSize: '0.7rem', fontWeight: 700, background: m.bg, color: m.color }}>{m.label}</span>
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span>📅 {start.toLocaleDateString()} {start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} – {end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          {appt.lead_name && <span>👤 {appt.lead_name}</span>}
          {appt.location && <span>📍 {appt.location}</span>}
        </div>
        {appt.note && <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 6, fontStyle: 'italic' }}>{appt.note}</div>}
      </div>
      {appt.status !== 'completed' && (
        <button className="btn btn-ghost btn-sm" onClick={() => onMarkComplete(appt.id)} id={`appt-complete-btn-${appt.id}`} title="Mark Complete">
          <CheckCircle size={16} />
        </button>
      )}
    </div>
  );
}

// ── Day Detail Modal ───────────────────────────────────────────────
function DayDetailPanel({ date, appts, onClose }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border)', borderRadius: 16, padding: 28, width: '100%', maxWidth: 480, maxHeight: '80vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h3 style={{ margin: 0 }}>{new Date(date + 'T00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose} id="day-detail-close">✕</button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {appts.map((a) => (
            <div key={a.id} style={{ padding: '10px 14px', background: 'rgba(255,255,255,0.04)', borderRadius: 8, borderLeft: '3px solid var(--primary)' }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>{a.title}</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {new Date(a.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {a.lead_name} · {a.mode?.replace('_',' ')}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Main Appointments Page ─────────────────────────────────────────
export default function AppointmentsPage() {
  const { isManagerOrAdmin } = useAuth();
  const [view, setView]           = useState('list'); // 'list' | 'calendar'
  const [tab, setTab]             = useState('upcoming');
  const [appointments, setAppts]  = useState([]);
  const [loading, setLoading]     = useState(true);
  const [page, setPage]           = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [dayDetail, setDayDetail] = useState(null); // { date, appts }

  const [googleStatus, setGoogleStatus] = useState({ google_connected: false });
  const [syncing, setSyncing] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [appts, gStatus] = await Promise.all([
        getAppointments(),
        getGoogleStatus().catch(() => ({ google_connected: false })),
      ]);
      setAppts(appts);
      setGoogleStatus(gStatus);
    } catch { toast.error('Failed to load appointments'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Handle Google OAuth callback params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('google_connected') === '1') {
      toast.success('Google Calendar connected!');
      window.history.replaceState({}, '', window.location.pathname);
      fetchAll();
    }
    if (params.get('google_error') === '1') {
      toast.error('Google Calendar connection failed. Please try again.');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [fetchAll]);

  const handleMarkComplete = async (id) => {
    try {
      await updateAppointment(id, { status: 'completed' });
      toast.success('Marked complete!');
      fetchAll();
    } catch { toast.error('Failed to update'); }
  };

  const handleGoogleConnect = async () => {
    try {
      const url = await getGoogleConnectUrl();
      window.location.href = url;
    } catch { toast.error('Failed to start Google auth'); }
  };

  const handleGoogleSync = async () => {
    setSyncing(true);
    try {
      await googleSync();
      toast.success('Synced with Google Calendar!');
      fetchAll();
    } catch { toast.error('Sync failed'); }
    finally { setSyncing(false); }
  };

  const handleGoogleDisconnect = async () => {
    try {
      await googleDisconnect();
      toast.success('Disconnected from Google Calendar');
      setGoogleStatus({ google_connected: false });
    } catch { toast.error('Disconnect failed'); }
  };

  const now = new Date().toISOString();
  const upcoming  = appointments.filter((a) => a.start_time >= now).sort((a, b) => a.start_time.localeCompare(b.start_time));
  const previous  = appointments.filter((a) => a.start_time < now).sort((a, b) => b.start_time.localeCompare(a.start_time));
  const pendingF  = appointments.filter((a) => a.status === 'pending');

  const TABS = isManagerOrAdmin
    ? [{ key: 'upcoming', label: 'Upcoming', data: upcoming }, { key: 'previous', label: 'Previous', data: previous }, { key: 'pending', label: 'Pending Follow-ups', data: pendingF }]
    : [{ key: 'upcoming', label: 'Upcoming', data: upcoming }, { key: 'previous', label: 'Previous', data: previous }];

  const activeTab = TABS.find((t) => t.key === tab) || TABS[0];
  const tabData   = activeTab.data;
  const paginated = tabData.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <>
      <Navbar title="Appointments" />
      <div className="page-container">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Appointments</h1>
            <p style={{ color: 'var(--text-muted)' }}>{appointments.length} total appointments</p>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {/* Google Calendar status */}
            {googleStatus.google_connected ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ padding: '6px 12px', background: 'rgba(16,185,129,0.15)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 8, fontSize: '0.8rem', color: '#34d399', fontWeight: 600 }}>
                  ✓ Google Calendar Synced
                </span>
                <button className="btn btn-ghost btn-sm" onClick={handleGoogleSync} disabled={syncing} id="google-sync-btn" title="Sync now">
                  <RefreshCw size={14} style={syncing ? { animation: 'spin 0.7s linear infinite' } : {}} />
                </button>
                <button className="btn btn-ghost btn-sm" onClick={handleGoogleDisconnect} id="google-disconnect-btn" title="Disconnect">
                  <Unlink size={14} />
                </button>
              </div>
            ) : (
              <button className="btn btn-secondary btn-sm" onClick={handleGoogleConnect} id="google-connect-btn">
                <ExternalLink size={14} /> Connect Google Calendar
              </button>
            )}
            <button className="btn btn-primary" onClick={() => setShowCreate(true)} id="create-appt-btn">
              <Plus size={16} /> New Appointment
            </button>
          </div>
        </div>

        {/* View toggle */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          <button className={`btn ${view === 'list' ? 'btn-primary' : 'btn-ghost'} btn-sm`} onClick={() => setView('list')} id="appt-list-view-btn">
            <List size={14} /> List
          </button>
          <button className={`btn ${view === 'calendar' ? 'btn-primary' : 'btn-ghost'} btn-sm`} onClick={() => setView('calendar')} id="appt-cal-view-btn">
            <CalIcon size={14} /> Calendar
          </button>
        </div>

        {loading ? (
          <div className="loading-center"><div className="spinner" /> Loading…</div>
        ) : view === 'calendar' ? (
          <div className="glass-card" style={{ padding: 24 }}>
            <CalendarView appointments={appointments} onDayClick={(date, appts) => setDayDetail({ date, appts })} />
          </div>
        ) : (
          <>
            <div className="tabs">
              {TABS.map((t) => (
                <button key={t.key} className={`tab ${tab === t.key ? 'active' : ''}`} onClick={() => { setTab(t.key); setPage(1); }} id={`appt-tab-${t.key}`}>
                  {t.label} <span style={{ opacity: 0.6, fontSize: '0.75em', marginLeft: 4 }}>({t.data.length})</span>
                </button>
              ))}
            </div>

            {paginated.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📅</div>
                <div className="empty-state-title">No appointments here</div>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {paginated.map((a) => <ApptCard key={a.id} appt={a} onMarkComplete={handleMarkComplete} />)}
                </div>
                <Pagination total={tabData.length} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
              </>
            )}
          </>
        )}
      </div>

      {showCreate && <ScheduleAppointmentModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); fetchAll(); }} />}
      {dayDetail && <DayDetailPanel date={dayDetail.date} appts={dayDetail.appts} onClose={() => setDayDetail(null)} />}
    </>
  );
}
