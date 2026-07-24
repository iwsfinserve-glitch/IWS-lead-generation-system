import { useState, useEffect } from 'react';
import Modal from '../common/Modal';
import { createLead } from '../../api/leadsApi';
import { getSources } from '../../api/leadsApi';
import { getUsers } from '../../api/usersApi';
import { useAuth } from '../../context/AuthContext';
import toast from 'react-hot-toast';

export default function CreateLeadModal({ onClose, onCreated }) {
  const { isManagerOrAdmin } = useAuth();
  const [sources, setSources] = useState([]);
  const [reps, setReps]       = useState([]);
  const [form, setForm] = useState({
    name: '', email: '', phone_number: '', profession: '',
    address: '', dob: '', source_id: '', assigned_rep_id: '', note: '',
  });

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSources().then(setSources).catch(() => {});
    if (isManagerOrAdmin) {
      getUsers().then((u) => setReps(u.filter((x) => x.role === 'sales_rep'))).catch(() => {});
    }
  }, [isManagerOrAdmin]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.phone_number.trim() || !form.profession.trim()) { 
      toast.error('Name, Email, Phone, and Profession are required'); 
      return; 
    }
    setSaving(true);
    try {
      const payload = { ...form };
      if (payload.source_id) payload.source_id = parseInt(payload.source_id);
      if (payload.assigned_rep_id) payload.assigned_rep_id = parseInt(payload.assigned_rep_id);
      Object.keys(payload).forEach((k) => { if (payload[k] === '') delete payload[k]; });
      await createLead(payload);
      toast.success('Lead created!');
      onCreated?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail[0].msg : 'Failed to create lead'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Create New Lead" onClose={onClose} size="lg">
      <form onSubmit={handleSubmit} id="create-lead-form">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div className="form-group">
            <label className="form-label">Full Name *</label>
            <input className="form-input" placeholder="John Doe" value={form.name}
              onChange={(e) => set('name', e.target.value)} id="create-lead-name" />
          </div>
          <div className="form-group">
            <label className="form-label">Profession</label>
            <input className="form-input" placeholder="Doctor, Engineer…" value={form.profession}
              onChange={(e) => set('profession', e.target.value)} id="create-lead-profession" />
          </div>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input className="form-input" type="email" placeholder="john@example.com" value={form.email}
              onChange={(e) => set('email', e.target.value)} id="create-lead-email" />
          </div>
          <div className="form-group">
            <label className="form-label">Phone</label>
            <input className="form-input" placeholder="+91 98765 43210" value={form.phone_number}
              onChange={(e) => set('phone_number', e.target.value)} id="create-lead-phone" />
          </div>
          <div className="form-group">
            <label className="form-label">Source</label>
            <select className="form-select" value={form.source_id} onChange={(e) => set('source_id', e.target.value)} id="create-lead-source">
              <option value="">Select source…</option>
              {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          {isManagerOrAdmin && (
            <div className="form-group">
              <label className="form-label">Assign To</label>
              <select className="form-select" value={form.assigned_rep_id} onChange={(e) => set('assigned_rep_id', e.target.value)} id="create-lead-rep">
                <option value="">Unassigned</option>
                {reps.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
          )}
          <div className="form-group" style={{ gridColumn: '1 / -1' }}>
            <label className="form-label">Address</label>
            <input className="form-input" placeholder="City, State" value={form.address}
              onChange={(e) => set('address', e.target.value)} id="create-lead-address" />
          </div>
          <div className="form-group" style={{ gridColumn: '1 / -1' }}>
            <label className="form-label">Date of Birth</label>
            <input className="form-input" type="date" value={form.dob}
              onChange={(e) => set('dob', e.target.value)} id="create-lead-dob" />
          </div>
          <div className="form-group" style={{ gridColumn: '1 / -1' }}>
            <label className="form-label">Initial Notes</label>
            <textarea className="form-textarea" placeholder="Any initial notes…" value={form.note}
              onChange={(e) => set('note', e.target.value)} id="create-lead-notes" />
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose} id="create-lead-cancel">Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving} id="create-lead-submit">
            {saving ? 'Creating…' : 'Create Lead'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
