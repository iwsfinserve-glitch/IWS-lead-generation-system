import { useState, useEffect } from 'react';
import { X, Send, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { createLeadUpdateRequest, getSources } from '../../api/leadsApi';

/**
 * LeadUpdateRequestModal
 * Allows a sales rep to request changes to a lead's contact fields.
 * Only changed fields are submitted. The request goes to the rep's manager for approval.
 */
export default function LeadUpdateRequestModal({ lead, onClose, onSubmitted }) {
  const [sources, setSources]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Proposed values — only populated fields will be sent
  const [email,    setEmail]    = useState('');
  const [phone,    setPhone]    = useState('');
  const [address,  setAddress]  = useState('');
  const [dob,      setDob]      = useState('');
  const [sourceId, setSourceId] = useState('');
  const [reason,   setReason]   = useState('');

  useEffect(() => {
    getSources().then(setSources).catch(() => {});
  }, []);

  const hasChanges = () => {
    if (email.trim()   && email.trim()   !== (lead.email || ''))           return true;
    if (phone.trim()   && phone.trim()   !== (lead.phone_number || ''))    return true;
    if (address.trim() && address.trim() !== (lead.address || ''))         return true;
    if (dob            && dob            !== (lead.dob || ''))              return true;
    if (sourceId       && parseInt(sourceId) !== lead.source_id)           return true;
    return false;
  };

  const handleSubmit = async () => {
    if (!hasChanges()) {
      toast.error('No changes detected — update at least one field.');
      return;
    }
    if (!reason.trim()) {
      toast.error('Please provide a reason for this update request.');
      return;
    }

    const payload = { lead_id: lead.id, reason: reason.trim() };
    if (email.trim()   && email.trim()   !== (lead.email || ''))        payload.proposed_email   = email.trim();
    if (phone.trim()   && phone.trim()   !== (lead.phone_number || '')) payload.proposed_phone   = phone.trim();
    if (address.trim() && address.trim() !== (lead.address || ''))      payload.proposed_address = address.trim();
    if (dob            && dob            !== (lead.dob || ''))           payload.proposed_dob     = dob;
    if (sourceId       && parseInt(sourceId) !== lead.source_id)        payload.proposed_source_id = parseInt(sourceId);

    setSubmitting(true);
    try {
      await createLeadUpdateRequest(payload);
      toast.success('Update request submitted! Your manager will be notified.');
      onSubmitted?.();
      onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        toast.error(detail);
      } else {
        toast.error('Failed to submit request. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 520 }}>
        {/* Header */}
        <div className="modal-header">
          <div>
            <div className="modal-title">✏️ Request Lead Update</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>
              {lead.name} — Changes require manager approval before being applied.
            </div>
          </div>
          <button className="modal-close" onClick={onClose} id="lead-update-req-close-btn">
            <X size={18} />
          </button>
        </div>

        {/* Info banner */}
        <div style={{
          display: 'flex', gap: 10, alignItems: 'flex-start',
          padding: '10px 14px',
          background: 'rgba(99,102,241,0.08)',
          border: '1px solid rgba(99,102,241,0.2)',
          borderRadius: 8, marginBottom: 20,
          fontSize: '0.82rem', color: 'var(--text-secondary)',
        }}>
          <AlertCircle size={15} color="var(--primary)" style={{ flexShrink: 0, marginTop: 1 }} />
          <span>
            Only fill in the fields you want to change. Leave fields blank to keep their current values.
            Your manager will see the before/after comparison before deciding.
          </span>
        </div>

        {/* Fields */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Email */}
          <div>
            <label className="form-label">
              Email <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(current: {lead.email || 'N/A'})</span>
            </label>
            <input
              type="email"
              className="form-input"
              placeholder="New email address…"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              id="lur-email"
            />
          </div>

          {/* Phone */}
          <div>
            <label className="form-label">
              Phone <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(current: {lead.phone_number || 'N/A'})</span>
            </label>
            <input
              type="tel"
              className="form-input"
              placeholder="New phone number…"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              id="lur-phone"
            />
          </div>

          {/* Address */}
          <div>
            <label className="form-label">
              Address <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(current: {lead.address || 'N/A'})</span>
            </label>
            <input
              type="text"
              className="form-input"
              placeholder="New address…"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              id="lur-address"
            />
          </div>

          {/* DOB */}
          <div>
            <label className="form-label">
              Date of Birth <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(current: {lead.dob || 'N/A'})</span>
            </label>
            <input
              type="date"
              className="form-input"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              id="lur-dob"
            />
          </div>

          {/* Source */}
          <div>
            <label className="form-label">
              Source <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(current: {lead.source_name || 'N/A'})</span>
            </label>
            <select
              className="form-select"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              id="lur-source"
            >
              <option value="">— keep current —</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {/* Reason */}
          <div>
            <label className="form-label">Reason <span style={{ color: 'var(--danger)' }}>*</span></label>
            <textarea
              className="form-textarea"
              placeholder="Explain why these details need to be updated…"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              id="lur-reason"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="modal-footer" style={{ marginTop: 24, display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost btn-sm" onClick={onClose} id="lur-cancel-btn">
            Cancel
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSubmit}
            disabled={submitting || !hasChanges() || !reason.trim()}
            id="lur-submit-btn"
          >
            {submitting ? (
              <><div className="spinner spinner-sm" /> Submitting…</>
            ) : (
              <><Send size={14} /> Submit Request</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
