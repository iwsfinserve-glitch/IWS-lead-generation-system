import { useState, useEffect } from 'react';
import Modal from '../common/Modal';
import { getLeads } from '../../api/leadsApi';
import { createAppointment } from '../../api/appointmentsApi';
import toast from 'react-hot-toast';

export default function ScheduleAppointmentModal({ leadId, onClose, onCreated }) {
  const [leads, setLeads]   = useState([]);
  const [form, setForm] = useState({
    lead_id: leadId || '',
    title: '',
    date: new Date().toISOString().slice(0, 10),
    start_time: '10:00',
    end_time: '11:00',
    mode: 'online',
    location: '',
    note: '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!leadId) {
      getLeads({ limit: 500 }).then(setLeads).catch(() => {});
    }
  }, [leadId]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.lead_id) { toast.error('Title and lead are required'); return; }

    const start = new Date(`${form.date}T${form.start_time}`);
    let end     = new Date(`${form.date}T${form.end_time}`);
    if (end <= start) end = new Date(start.getTime() + 60 * 60 * 1000);

    setSaving(true);
    try {
      await createAppointment({
        lead_id:    parseInt(form.lead_id),
        title:      form.title.trim(),
        note:       form.note.trim() || null,
        mode:       form.mode,
        location:   form.location.trim() || null,
        start_time: start.toISOString(),
        end_time:   end.toISOString(),
      });
      onCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create appointment');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Schedule Appointment" onClose={onClose}>
      <form onSubmit={handleSubmit} id="schedule-appointment-form">
        {!leadId && (
          <div className="form-group">
            <label className="form-label">Lead *</label>
            <select className="form-select" value={form.lead_id} onChange={(e) => set('lead_id', e.target.value)} id="appt-lead-select">
              <option value="">Select lead…</option>
              {leads.map((l) => <option key={l.id} value={l.id}>{l.name} (ID: {l.id})</option>)}
            </select>
          </div>
        )}
        <div className="form-group">
          <label className="form-label">Title *</label>
          <input className="form-input" placeholder="e.g. Follow-up call" value={form.title}
            onChange={(e) => set('title', e.target.value)} id="appt-title" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">Date</label>
            <input type="date" className="form-input" value={form.date}
              onChange={(e) => set('date', e.target.value)} id="appt-date" />
          </div>
          <div className="form-group">
            <label className="form-label">Start Time</label>
            <input type="time" className="form-input" value={form.start_time}
              onChange={(e) => set('start_time', e.target.value)} id="appt-start-time" />
          </div>
          <div className="form-group">
            <label className="form-label">End Time</label>
            <input type="time" className="form-input" value={form.end_time}
              onChange={(e) => set('end_time', e.target.value)} id="appt-end-time" />
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">Mode</label>
            <select className="form-select" value={form.mode} onChange={(e) => set('mode', e.target.value)} id="appt-mode">
              <option value="online">Online</option>
              <option value="in_person">In Person</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Location</label>
            <input className="form-input" placeholder="Google Meet / Office address" value={form.location}
              onChange={(e) => set('location', e.target.value)} id="appt-location" />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">Notes</label>
          <textarea className="form-textarea" placeholder="Agenda or details…" value={form.note}
            onChange={(e) => set('note', e.target.value)} id="appt-note" />
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose} id="appt-cancel">Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving} id="appt-submit">
            {saving ? 'Scheduling…' : 'Schedule Appointment'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
