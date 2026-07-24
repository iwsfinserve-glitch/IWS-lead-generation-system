import { useState, useEffect } from 'react';
import Modal from '../common/Modal';
import { getLeads } from '../../api/leadsApi';
import { getUsers } from '../../api/usersApi';
import { createTask } from '../../api/tasksApi';
import { useAuth } from '../../context/AuthContext';
import toast from 'react-hot-toast';

export default function CreateTaskModal({ leadId, onClose, onCreated }) {
  const { isManagerOrAdmin, user } = useAuth();
  const [leads, setLeads] = useState([]);
  const [reps, setReps]   = useState([]);
  const [form, setForm] = useState({
    lead_id: leadId || '',
    title: '',
    notes: '',
    due: '',
    assigned_to_id: '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!leadId) getLeads({ limit: 500 }).then(setLeads).catch(() => {});
    if (isManagerOrAdmin) {
      getUsers().then((u) => setReps(u.filter((x) => x.role === 'sales_rep'))).catch(() => {});
    }
  }, [leadId, isManagerOrAdmin]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.lead_id) { toast.error('Title and lead are required'); return; }
    setSaving(true);
    try {
      const selectedLead = leads.find(l => l.id === parseInt(form.lead_id));
      const leadContext = selectedLead ? `[Lead: ${selectedLead.name}] ` : '';
      const payload = {
        title:   leadContext + form.title.trim(),
        notes:   form.notes.trim() || null,
        due:     form.due || null,
        user_id: form.assigned_to_id ? parseInt(form.assigned_to_id) : (isManagerOrAdmin ? null : user?.id),
      };
      if (isManagerOrAdmin && !payload.user_id) {
          toast.error("Please assign the task to a user.");
          setSaving(false);
          return;
      }
      await createTask(payload);
      onCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create task');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Create Task" onClose={onClose}>
      <form onSubmit={handleSubmit} id="create-task-form">
        {!leadId && (
          <div className="form-group">
            <label className="form-label">Lead *</label>
            <select className="form-select" value={form.lead_id} onChange={(e) => set('lead_id', e.target.value)} id="task-lead-select">
              <option value="">Select lead…</option>
              {leads.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </div>
        )}
        <div className="form-group">
          <label className="form-label">Title *</label>
          <input className="form-input" placeholder="e.g. Follow up with client" value={form.title}
            onChange={(e) => set('title', e.target.value)} id="task-title" />
        </div>
        <div className="form-group">
          <label className="form-label">Due Date</label>
          <input type="date" className="form-input" value={form.due}
            onChange={(e) => set('due', e.target.value)} id="task-due" />
        </div>
        {isManagerOrAdmin && reps.length > 0 && (
          <div className="form-group">
            <label className="form-label">Assign To</label>
            <select className="form-select" value={form.assigned_to_id} onChange={(e) => set('assigned_to_id', e.target.value)} id="task-assignee-select">
              <option value="">Unassigned (self-assign)</option>
              {reps.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </div>
        )}
        <div className="form-group">
          <label className="form-label">Notes</label>
          <textarea className="form-textarea" placeholder="Task description…" value={form.notes}
            onChange={(e) => set('notes', e.target.value)} id="task-notes" />
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose} id="task-cancel">Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving} id="task-submit">
            {saving ? 'Creating…' : 'Create Task'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
