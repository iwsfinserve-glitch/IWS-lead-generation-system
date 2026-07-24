import { useState } from 'react';
import Modal from '../common/Modal';
import { useAuth } from '../../context/AuthContext';
import { createDueDateRequest, updateTask } from '../../api/tasksApi';
import toast from 'react-hot-toast';

export default function RequestDueDateModal({ task, onClose, onRequested }) {
  const { user, isManagerOrAdmin } = useAuth();
  const [newDue, setNewDue] = useState(task?.due || '');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);

  const canEditDirectly = isManagerOrAdmin || task?.assigned_by === user?.id || !task?.assigned_by;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newDue) { toast.error('New due date is required'); return; }
    if (new Date(newDue) < new Date(new Date().toDateString())) { toast.error('Due date cannot be in the past'); return; }
    if (!canEditDirectly && reason.trim().length < 5) { toast.error('A detailed reason (min 5 chars) is required for extension requests'); return; }
    setSaving(true);
    try {
      if (canEditDirectly) {
        await updateTask(task.id, { due: newDue });
        toast.success('Due date updated!');
      } else {
        await createDueDateRequest({ task_id: task.id, requested_date: newDue, reason: reason.trim() });
        toast.success('Extension request submitted!');
      }
      onRequested?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Request failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={canEditDirectly ? "Update Due Date" : "Request Due Date Extension"} onClose={onClose}>
      <form onSubmit={handleSubmit} id="request-due-date-form">
        <div style={{ marginBottom: 16, padding: '12px 16px', background: 'rgba(255,255,255,0.04)', borderRadius: 8 }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{task?.title}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Current due: {task?.due || 'None'}</div>
        </div>
        <div className="form-group">
          <label className="form-label">Requested New Due Date *</label>
          <input type="date" className="form-input" value={newDue}
            onChange={(e) => setNewDue(e.target.value)} id="new-due-date" />
        </div>
        {!canEditDirectly && (
          <div className="form-group">
            <label className="form-label">Reason</label>
            <textarea className="form-textarea" placeholder="Why do you need more time?" value={reason}
              onChange={(e) => setReason(e.target.value)} id="due-date-reason" />
          </div>
        )}
        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose} id="due-date-cancel">Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving} id="due-date-submit">
            {saving ? 'Saving…' : (canEditDirectly ? 'Update Due Date' : 'Submit Request')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
