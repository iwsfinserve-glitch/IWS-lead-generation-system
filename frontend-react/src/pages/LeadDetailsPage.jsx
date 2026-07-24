import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Phone, Mail, MapPin, User, Calendar, Edit, Trash2, Zap, Lock } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import { StatusBadge, STATUS_DISPLAY, STATUS_COLOR } from '../components/common/StatusBadge';
import { getLead, getLeadTimeline, addTimelineNote, updateLead, deleteLead, claimLead, getSalesReps } from '../api/leadsApi';
import { getLeadAIScore, triggerLeadAIScore, getLeadAIContactTiming } from '../api/aiApi';

import { createLeadTransfer } from '../api/usersApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import ScheduleAppointmentModal from '../components/modals/ScheduleAppointmentModal';
import CreateTaskModal from '../components/modals/CreateTaskModal';

const EVENT_STYLES = {
  status_change:      { border: '#2196F3', bg: 'rgba(33,150,243,0.07)', icon: '🔄' },
  note:               { border: '#4CAF50', bg: 'rgba(76,175,80,0.07)',  icon: '📝' },
  lead_created:       { border: '#9C27B0', bg: 'rgba(156,39,176,0.07)', icon: '✨' },
  appointment_booked: { border: '#FF9800', bg: 'rgba(255,152,0,0.07)',  icon: '📅' },
};

const ALL_STATUSES = [
  { api: 'unassigned', label: 'Unassigned' },
  { api: 'new', label: 'New' },
  { api: 'in_progress', label: 'In Progress' },
  { api: 'potential', label: 'Potential' },
  { api: 'non_potential', label: 'Non-Potential' },
  { api: 'converted_to_investor', label: 'Converted to Investor' },
  { api: 'existing_investor', label: 'Existing Investor' },
];

// ── AI Insights Section ──────────────────────────────────────────────
function AIInsightsSection({ leadId }) {
  const [score, setScore]   = useState(null);
  const [timing, setTiming] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const loadInsights = async () => {
    try {
      const [s, t] = await Promise.all([
        getLeadAIScore(leadId).catch((e) => e.response?.status === 404 ? null : Promise.reject(e)),
        getLeadAIContactTiming(leadId).catch(() => null),
      ]);
      setScore(s);
      setTiming(t);
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadInsights(); }, [leadId]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const s = await triggerLeadAIScore(leadId);
      setScore(s);
      toast.success('AI score generated!');
    } catch {
      toast.error('AI generation failed');
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return <div style={{ padding: 20, color: 'var(--text-muted)' }}>Fetching AI insights…</div>;

  const labelColors = { hot: '#ef4444', warm: '#f59e0b', cold: '#3b82f6' };

  return (
    <div>
      <h3 style={{ marginBottom: 14, fontSize: '1rem' }}>AI Insights</h3>

      {score ? (
        <div className="ai-card" style={{ borderLeftColor: labelColors[score.label?.toLowerCase()] || 'var(--primary)' }}>
          <div className="ai-card-header">
            <span className="ai-card-title">{score.label?.toUpperCase()} LEAD</span>
            <span className="badge" style={{ background: labelColors[score.label?.toLowerCase()] || 'var(--primary)', color: '#fff', border: 'none' }}>
              Score: {Math.round(score.score)}/100
            </span>
          </div>
          {score.reasoning && <p style={{ fontSize: '0.87rem', color: 'var(--text-secondary)', fontStyle: 'italic', marginBottom: 8 }}>"{score.reasoning}"</p>}
          {score.key_signals?.length > 0 && (
            <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 8 }}>
              <strong>Key signals:</strong> {score.key_signals.join(', ')}
            </div>
          )}
          {score.suggested_next_action && (
            <div style={{ padding: '8px 12px', background: 'rgba(99,102,241,0.1)', borderRadius: 6, fontSize: '0.83rem', borderLeft: '3px solid var(--primary)' }}>
              <strong>Suggested action:</strong> {score.suggested_next_action}
            </div>
          )}
        </div>
      ) : (
        <div style={{ marginBottom: 12 }}>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: 10 }}>
            No AI score yet. Click to generate insights based on this lead's history.
          </p>
          <button className="btn btn-primary btn-sm" onClick={handleGenerate} disabled={generating} id="generate-ai-score-btn">
            {generating ? '⏳ Generating…' : '⚡ Generate AI Score'}
          </button>
        </div>

      )}

      {timing?.has_sufficient_data ? (
        <div className="ai-card">
          <div className="ai-card-header">
            <span className="ai-card-title">Best Time to Contact</span>
            <span className="badge badge-manager">Confidence: {(timing.confidence || 'medium').toUpperCase()}</span>
          </div>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            <strong>Days:</strong> {(timing.suggested_days || []).join(', ') || 'N/A'} &nbsp;|&nbsp;
            <strong>Window:</strong> {timing.suggested_window || 'Flexible'}
          </div>
          {timing.reasoning && <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 6, fontStyle: 'italic' }}>{timing.reasoning}</p>}
        </div>
      ) : timing ? (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>{timing.reasoning}</p>
      ) : null}
    </div>
  );
}

// ── Main Lead Details Page ───────────────────────────────────────────
export default function LeadDetailsPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, isAdmin, isManagerOrAdmin } = useAuth();

  const [lead, setLead]           = useState(null);
  const [timeline, setTimeline]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [note, setNote]           = useState('');
  const [addingNote, setAddingNote] = useState(false);

  const [newStatus, setNewStatus]       = useState('');
  const [newLastContact, setNewLastContact] = useState('');
  const [newDob, setNewDob]             = useState('');
  const [saving, setSaving]             = useState(false);

  const [reps, setReps]     = useState([]);
  const [transferTo, setTransferTo] = useState('');
  const [transferReason, setTransferReason] = useState('');
  const [transferring, setTransferring] = useState(false);

  const [showApptModal, setShowApptModal] = useState(false);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    Promise.all([getLead(id), getLeadTimeline(id)])
      .then(([l, t]) => {
        setLead(l);
        setTimeline(t);
        setNewStatus(l.status);
        setNewLastContact(l.last_contact || '');
        setNewDob(l.dob || '');
      })
      .catch(() => toast.error('Failed to load lead'))
      .finally(() => setLoading(false));

    getSalesReps().then(setReps).catch(() => {});
  }, [id]);

  const canUpdate = user && (isManagerOrAdmin || String(lead?.assigned_rep_id) === String(user.id));

  const handleSave = async () => {
    setSaving(true);
    try {
      const updates = {};
      if (newStatus !== lead.status) updates.status = newStatus;
      if (newLastContact !== (lead.last_contact || '')) updates.last_contact = newLastContact;
      if (newDob !== (lead.dob || '')) updates.dob = newDob || null;
      if (Object.keys(updates).length === 0) { toast('No changes to save.'); return; }
      await updateLead(id, updates);
      toast.success('Lead updated!');
      const updated = await getLead(id);
      setLead(updated);
      const t = await getLeadTimeline(id);
      setTimeline(t);
    } catch {
      toast.error('Update failed');
    } finally {
      setSaving(false);
    }
  };

  const handleAddNote = async () => {
    if (!note.trim()) { toast.error('Note cannot be empty'); return; }
    setAddingNote(true);
    try {
      await addTimelineNote(id, { event_type: 'note', event_metadata: { note: note.trim() } });
      setNote('');
      toast.success('Note added!');
      const t = await getLeadTimeline(id);
      setTimeline(t);
    } catch {
      toast.error('Failed to add note');
    } finally {
      setAddingNote(false);
    }
  };

  const handleClaim = async () => {
    try {
      await claimLead(id);
      toast.success('Lead claimed!');
      const updated = await getLead(id);
      setLead(updated);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Claim failed');
    }
  };

  const handleTransfer = async () => {
    if (!transferTo) { toast.error('Select a rep'); return; }
    setTransferring(true);
    try {
      await createLeadTransfer({ lead_id: parseInt(id), to_user_id: parseInt(transferTo), reason: transferReason || undefined });
      toast.success('Transfer request submitted!');
      setTransferTo('');
      setTransferReason('');
    } catch {
      toast.error('Transfer request failed');
    } finally {
      setTransferring(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteLead(id);
      toast.success('Lead deleted');
      navigate('/leads');
    } catch {
      toast.error('Delete failed');
      setDeleting(false);
    }
  };

  if (loading) return (
    <>
      <Navbar title="Lead Details" />
      <div className="loading-center" style={{ height: 'calc(100vh - 60px)' }}>
        <div className="spinner spinner-lg" />
      </div>
    </>
  );

  if (!lead) return null;

  const statusColor = STATUS_COLOR[lead.status] || '#64748b';
  const otherReps = reps.filter((r) => r.id !== user?.id);

  const formatTimelineBody = (entry) => {
    const meta = entry.event_metadata || {};
    switch (entry.event_type) {
      case 'status_change':
        return `${STATUS_DISPLAY[meta.old_status] || meta.old_status} → ${STATUS_DISPLAY[meta.new_status] || meta.new_status}${meta.note ? ` — ${meta.note}` : ''}`;
      case 'note':
        return meta.note || '';
      case 'lead_created':
        return `Lead created from ${meta.source || 'unknown'}${meta.referred_by ? ` (Referred by ${meta.referred_by})` : ''}`;
      case 'appointment_booked':
        return `Appointment: ${meta.title || ''}${meta.mode ? ` · ${meta.mode.replace('_',' ')}` : ''}`;
      default:
        return entry.event_type.replace(/_/g, ' ');
    }
  };

  return (
    <>
      <Navbar title="Lead Details" />
      <div className="page-container">
        {/* Back */}
        <button className="btn btn-ghost btn-sm" style={{ marginBottom: 16 }} onClick={() => navigate('/leads')} id="lead-details-back-btn">
          <ArrowLeft size={14} /> Back to All Leads
        </button>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 6, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0 }}>{lead.name}</h1>
          {lead.profession && <span style={{ color: 'var(--text-secondary)', fontSize: '1.1rem' }}>{lead.profession}</span>}
          <StatusBadge status={lead.status} />
        </div>

        {/* Contact info */}
        <div className="glass-card" style={{ padding: '18px 20px', marginBottom: 24, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {[
            { icon: Mail, label: 'Email', value: lead.email },
            { icon: Phone, label: 'Phone', value: lead.phone_number },
            { icon: User, label: 'Source', value: lead.source_name },
            { icon: User, label: 'Assigned Rep', value: lead.assigned_rep_name || 'Unassigned' },
            { icon: Calendar, label: 'Last Contact', value: lead.last_contact || 'N/A' },
            { icon: MapPin, label: 'Address', value: lead.address || 'N/A' },
            { icon: Calendar, label: 'Date of Birth', value: lead.dob || 'N/A' },
            { icon: User, label: 'Age', value: lead.age !== null ? `${lead.age} years` : 'N/A' },
          ].map(({ icon: Icon, label, value }) => (
            <div key={label}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)', marginBottom: 4, display: 'flex', gap: 5, alignItems: 'center' }}>
                <Icon size={12} /> {label}
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{value || 'N/A'}</div>
            </div>
          ))}
        </div>

        {/* Admin delete/edit */}
        {isAdmin && (
          <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
            {!confirmDelete ? (
              <button className="btn btn-danger btn-sm" onClick={() => setConfirmDelete(true)} id="lead-delete-btn">
                <Trash2 size={14} /> Delete Lead
              </button>
            ) : (
              <>
                <span style={{ color: 'var(--warning)', fontSize: '0.875rem', alignSelf: 'center' }}>Permanently delete this lead?</span>
                <button className="btn btn-danger btn-sm" onClick={handleDelete} disabled={deleting} id="lead-delete-confirm-btn">
                  {deleting ? 'Deleting…' : 'Yes, Delete'}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(false)} id="lead-delete-cancel-btn">Cancel</button>
              </>
            )}
          </div>
        )}

        {/* Two-column layout */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 24, alignItems: 'start' }}>
          {/* Left — Timeline + Actions */}
          <div>
            {/* Actions */}
            {canUpdate ? (
              <div className="glass-card" style={{ padding: 20, marginBottom: 20 }}>
                <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>Actions</h3>

                <div style={{ marginBottom: 16 }}>
                  <label className="form-label">Change Status</label>
                  <select className="form-select" value={newStatus} onChange={(e) => setNewStatus(e.target.value)} id="lead-status-select">
                    {ALL_STATUSES.map((s) => <option key={s.api} value={s.api}>{s.label}</option>)}
                  </select>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label className="form-label">Last Contact Date</label>
                  <input type="date" className="form-input" value={newLastContact} onChange={(e) => setNewLastContact(e.target.value)} id="lead-last-contact-input" />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label className="form-label">Date of Birth</label>
                  <input type="date" className="form-input" value={newDob} onChange={(e) => setNewDob(e.target.value)} id="lead-dob-input" />
                </div>
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving} id="lead-save-btn">
                  {saving ? 'Saving…' : 'Save Changes'}
                </button>

                <hr className="divider" />

                {/* Quick actions */}
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary btn-sm" onClick={() => setShowApptModal(true)} id="lead-book-appt-btn">
                    <Calendar size={14} /> Book Appointment
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setShowTaskModal(true)} id="lead-add-task-btn">
                    <Edit size={14} /> Add Task
                  </button>
                </div>

                {/* Transfer */}
                {otherReps.length > 0 && (
                  <>
                    <hr className="divider" />
                    <h4 style={{ marginBottom: 12, fontSize: '0.9rem' }}>Transfer Lead</h4>
                    <select className="form-select" value={transferTo} onChange={(e) => setTransferTo(e.target.value)} style={{ marginBottom: 8 }} id="lead-transfer-select">
                      <option value="">Select rep…</option>
                      {otherReps.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                    <textarea
                      className="form-textarea"
                      placeholder="Reason (optional)"
                      value={transferReason}
                      onChange={(e) => setTransferReason(e.target.value)}
                      style={{ marginBottom: 8 }}
                      id="lead-transfer-reason"
                    />
                    <button className="btn btn-secondary btn-sm" onClick={handleTransfer} disabled={transferring} id="lead-transfer-btn">
                      {transferring ? 'Submitting…' : 'Request Transfer'}
                    </button>
                  </>
                )}
              </div>
            ) : (
              <div className="glass-card" style={{ padding: 20, marginBottom: 20 }}>
                {(!lead.assigned_rep_id || lead.status === 'unassigned') ? (
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ color: 'var(--warning)', fontWeight: 700, fontSize: '1rem', marginBottom: 8 }}>⚡ Unassigned Lead</div>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 14 }}>Claim it to assign it to yourself and begin working.</p>
                    <button className="btn btn-primary btn-full" onClick={handleClaim} id="lead-claim-btn">⚡ Claim This Lead</button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <Lock size={18} color="var(--text-muted)" style={{ marginTop: 2 }} />
                    <div>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>Read-Only Mode</div>
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        This lead is assigned to <strong>{lead.assigned_rep_name || 'another rep'}</strong>. Only the assigned rep or a manager can modify it.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Timeline */}
            <div className="glass-card" style={{ padding: 20 }}>
              <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>Interaction History</h3>

              {canUpdate && (
                <div style={{ marginBottom: 20 }}>
                  <textarea
                    className="form-textarea"
                    placeholder="Add a note or interaction…"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    id="lead-note-textarea"
                  />
                  <button className="btn btn-primary btn-sm" style={{ marginTop: 8 }} onClick={handleAddNote} disabled={addingNote} id="lead-add-note-btn">
                    {addingNote ? 'Adding…' : 'Add Note'}
                  </button>
                </div>
              )}

              {timeline.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>No timeline entries yet.</p>
              ) : (
                <div className="timeline">
                  {timeline.map((entry) => {
                    const style = EVENT_STYLES[entry.event_type] || { border: '#999', bg: 'rgba(100,116,139,0.07)', icon: '•' };
                    return (
                      <div key={entry.id} className="timeline-entry" style={{ borderLeftColor: style.border, background: style.bg }}>
                        <div className="timeline-entry-header">
                          <span className="timeline-event-type" style={{ color: style.border }}>
                            {style.icon} {entry.event_type.replace(/_/g,' ')}
                          </span>
                          <span className="timeline-ts">{entry.created_at?.slice(0,16).replace('T',' ')}</span>
                        </div>
                        <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                          {formatTimelineBody(entry)}
                        </div>
                        {entry.created_by_name && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>by {entry.created_by_name}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right — AI Insights */}
          <div className="glass-card" style={{ padding: 20 }}>
            <AIInsightsSection leadId={id} />
          </div>
        </div>
      </div>

      {showApptModal && <ScheduleAppointmentModal leadId={id} onClose={() => setShowApptModal(false)} onCreated={() => { setShowApptModal(false); toast.success('Appointment booked!'); }} />}
      {showTaskModal && <CreateTaskModal leadId={id} onClose={() => setShowTaskModal(false)} onCreated={() => { setShowTaskModal(false); toast.success('Task added!'); }} />}
    </>
  );
}
