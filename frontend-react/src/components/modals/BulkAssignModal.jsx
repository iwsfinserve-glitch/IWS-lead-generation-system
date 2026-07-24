import { useState, useEffect } from 'react';
import Modal from '../common/Modal';
import { bulkAssignLeads, getSalesReps } from '../../api/leadsApi';
import toast from 'react-hot-toast';

export default function BulkAssignModal({ onClose, onAssigned, selectedLeads }) {
  const [reps, setReps] = useState([]);
  const [targetRepId, setTargetRepId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [overwrite, setOverwrite] = useState(false);

  useEffect(() => {
    getSalesReps().then(setReps).catch(() => {});
  }, []);

  const assignedCount = selectedLeads.filter((l) => l.assigned_rep_id).length;
  const unassignedCount = selectedLeads.length - assignedCount;

  const handleSubmit = async () => {
    if (!targetRepId) {
      toast.error('Please select a target sales representative.');
      return;
    }
    
    setSubmitting(true);
    try {
      const res = await bulkAssignLeads({
        lead_ids: selectedLeads.map((l) => l.id),
        assigned_rep_id: parseInt(targetRepId),
        overwrite_existing: overwrite,
      });
      
      toast.success(`Assigned: ${res.assigned_count}, Transferred: ${res.transferred_count}, Skipped: ${res.skipped_count}`);
      onAssigned?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to assign leads.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Bulk Assign Leads" onClose={onClose} size="md">
      <div style={{ padding: '10px 0' }}>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: 20 }}>
          You have selected <strong>{selectedLeads.length}</strong> leads to assign.
        </p>

        <div className="form-group" style={{ marginBottom: 20 }}>
          <label className="form-label">Assign To</label>
          <select 
            className="form-select" 
            value={targetRepId} 
            onChange={(e) => setTargetRepId(e.target.value)}
          >
            <option value="">Select a sales rep…</option>
            {reps.filter(r => r.role === 'sales_rep').map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </div>

        {assignedCount > 0 && (
          <div style={{ padding: 15, background: 'rgba(245, 158, 11, 0.1)', borderLeft: '4px solid #f59e0b', borderRadius: 4, marginBottom: 20 }}>
            <h4 style={{ color: '#d97706', marginBottom: 10, fontSize: '0.95rem' }}>⚠️ Reassignment Warning</h4>
            <p style={{ fontSize: '0.85rem', marginBottom: 15 }}>
              <strong>{assignedCount}</strong> of the selected leads are already assigned to other representatives.
            </p>
            
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, fontSize: '0.85rem', cursor: 'pointer' }}>
              <input 
                type="radio" 
                name="overwrite_choice" 
                checked={!overwrite} 
                onChange={() => setOverwrite(false)} 
              />
              <strong>Skip Already Assigned</strong> (Only assign the {unassignedCount} unassigned leads)
            </label>
            
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', cursor: 'pointer' }}>
              <input 
                type="radio" 
                name="overwrite_choice" 
                checked={overwrite} 
                onChange={() => setOverwrite(true)} 
              />
              <strong>Transfer & Overwrite</strong> (Reassign all {selectedLeads.length} leads to the new rep)
            </label>
          </div>
        )}

        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
          <button 
            type="button" 
            className="btn btn-primary" 
            disabled={!targetRepId || submitting} 
            onClick={handleSubmit}
          >
            {submitting ? 'Assigning…' : 'Confirm Assignment'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
