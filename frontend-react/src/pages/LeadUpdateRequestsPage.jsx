import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle, XCircle, ArrowLeft, Clock, User, FileEdit } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import { getLeadUpdateRequests, resolveLeadUpdateRequest } from '../api/leadsApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

const STATUS_STYLE = {
  pending:  { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.35)', label: '⏳ Pending' },
  approved: { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.35)',  label: '✅ Approved' },
  rejected: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.35)',  label: '❌ Rejected' },
};

function DiffRow({ label, current, proposed }) {
  if (proposed == null) return null;
  const changed = proposed !== current;
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '110px 1fr auto 1fr',
      alignItems: 'center', gap: 10,
      padding: '8px 0',
      borderBottom: '1px solid var(--border)',
      fontSize: '0.85rem',
    }}>
      <span style={{ color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
        {label}
      </span>
      <span style={{
        padding: '3px 8px', borderRadius: 6,
        background: 'rgba(239,68,68,0.08)', color: 'var(--text-secondary)',
        textDecoration: changed ? 'line-through' : 'none',
        opacity: changed ? 0.7 : 1,
      }}>
        {current || <em style={{ color: 'var(--text-muted)' }}>empty</em>}
      </span>
      {changed && (
        <>
          <span style={{ color: 'var(--primary)', fontWeight: 700, fontSize: '1rem' }}>→</span>
          <span style={{
            padding: '3px 8px', borderRadius: 6,
            background: 'rgba(34,197,94,0.12)', color: '#22c55e',
            fontWeight: 600,
          }}>
            {proposed}
          </span>
        </>
      )}
    </div>
  );
}

export default function LeadUpdateRequestsPage() {
  const { isManagerOrAdmin } = useAuth();
  const navigate = useNavigate();

  const [requests, setRequests] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [filter, setFilter]     = useState('pending');
  const [resolving, setResolving] = useState(null); // request id being resolved

  const load = async () => {
    setLoading(true);
    try {
      const params = filter ? { status: filter } : {};
      const data = await getLeadUpdateRequests(params);
      setRequests(data);
    } catch {
      toast.error('Failed to load update requests');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter]);

  const handleResolve = async (reqId, action) => {
    setResolving(reqId);
    try {
      await resolveLeadUpdateRequest(reqId, { status: action });
      toast.success(action === 'approved' ? '✅ Request approved — lead updated!' : '❌ Request rejected.');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to resolve request');
    } finally {
      setResolving(null);
    }
  };

  if (!isManagerOrAdmin) {
    return (
      <>
        <Navbar title="Lead Update Requests" />
        <div className="page-container">
          <p style={{ color: 'var(--text-muted)' }}>Access denied — managers and admins only.</p>
        </div>
      </>
    );
  }

  return (
    <>
      <Navbar title="Lead Update Requests" />
      <div className="page-container">
        {/* Back */}
        <button className="btn btn-ghost btn-sm" style={{ marginBottom: 20 }} onClick={() => navigate(-1)} id="lur-page-back-btn">
          <ArrowLeft size={14} /> Back
        </button>

        {/* Header */}
        <div className="page-header" style={{ marginBottom: 24 }}>
          <div>
            <h1 style={{ margin: 0, marginBottom: 4 }}>Lead Update Requests</h1>
            <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: '0.875rem' }}>
              Sales reps request contact field changes here — review the before/after diff and approve or reject.
            </p>
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          {['pending', 'approved', 'rejected', ''].map((s) => (
            <button
              key={s || 'all'}
              className={`btn btn-sm ${filter === s ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setFilter(s)}
              id={`lur-filter-${s || 'all'}`}
            >
              {s ? s.charAt(0).toUpperCase() + s.slice(1) : 'All'}
            </button>
          ))}
        </div>

        {/* Content */}
        {loading ? (
          <div className="loading-center"><div className="spinner" /> Loading…</div>
        ) : requests.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon"><FileEdit size={32} /></div>
            <div className="empty-state-title">No {filter || ''} requests</div>
            <div className="empty-state-subtitle">
              {filter === 'pending'
                ? 'All caught up! No pending update requests from your team.'
                : 'No requests match this filter.'}
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {requests.map((req) => {
              const ss = STATUS_STYLE[req.status] || STATUS_STYLE.pending;
              const isResolvingThis = resolving === req.id;
              return (
                <div key={req.id} className="glass-card" style={{ padding: 20 }}>
                  {/* Card header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <div style={{ fontWeight: 700, fontSize: '1rem' }}>
                          {req.lead_name || `Lead #${req.lead_id}`}
                        </div>
                        <span style={{
                          padding: '3px 10px', borderRadius: 20,
                          background: ss.bg, border: `1px solid ${ss.border}`,
                          color: ss.color, fontSize: '0.78rem', fontWeight: 700,
                        }}>
                          {ss.label}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                        <span><User size={11} style={{ marginRight: 4 }} />{req.requested_by_name || 'Unknown rep'}</span>
                        <span><Clock size={11} style={{ marginRight: 4 }} />{new Date(req.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</span>
                      </div>
                    </div>
                    {/* Action buttons — only for pending */}
                    {req.status === 'pending' && (
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          className="btn btn-sm"
                          style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.35)' }}
                          onClick={() => handleResolve(req.id, 'approved')}
                          disabled={!!resolving}
                          id={`lur-approve-${req.id}`}
                        >
                          {isResolvingThis ? <div className="spinner spinner-sm" /> : <CheckCircle size={14} />}
                          Approve
                        </button>
                        <button
                          className="btn btn-sm"
                          style={{ background: 'rgba(239,68,68,0.12)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)' }}
                          onClick={() => handleResolve(req.id, 'rejected')}
                          disabled={!!resolving}
                          id={`lur-reject-${req.id}`}
                        >
                          {isResolvingThis ? <div className="spinner spinner-sm" /> : <XCircle size={14} />}
                          Reject
                        </button>
                      </div>
                    )}
                    {req.status !== 'pending' && req.resolved_at && (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        Resolved: {new Date(req.resolved_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                      </div>
                    )}
                  </div>

                  {/* Reason */}
                  <div style={{
                    padding: '8px 12px', borderRadius: 7,
                    background: 'rgba(99,102,241,0.07)',
                    border: '1px solid rgba(99,102,241,0.15)',
                    fontSize: '0.83rem', color: 'var(--text-secondary)',
                    marginBottom: 14,
                  }}>
                    <strong>Reason:</strong> {req.reason}
                  </div>

                  {/* Diff table */}
                  <div style={{ borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', padding: '4px 12px' }}>
                    <DiffRow label="Email"   current={req.current_email}   proposed={req.proposed_email} />
                    <DiffRow label="Phone"   current={req.current_phone}   proposed={req.proposed_phone} />
                    <DiffRow label="Address" current={req.current_address} proposed={req.proposed_address} />
                    <DiffRow label="DOB"     current={req.current_dob}     proposed={req.proposed_dob ? String(req.proposed_dob) : null} />
                    <DiffRow
                      label="Source"
                      current={req.current_source_name || (req.current_source_id ? `Source #${req.current_source_id}` : null)}
                      proposed={req.proposed_source_id ? `Source #${req.proposed_source_id}` : null}
                    />
                  </div>

                  {/* View Lead link */}
                  <div style={{ marginTop: 12, textAlign: 'right' }}>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => navigate(`/leads/${req.lead_id}`)}
                      id={`lur-view-lead-${req.id}`}
                    >
                      View Lead →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
