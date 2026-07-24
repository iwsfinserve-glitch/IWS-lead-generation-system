import { useNavigate } from 'react-router-dom';
import { Phone, Mail, User, ChevronRight } from 'lucide-react';
import { StatusBadge } from '../common/StatusBadge';

export default function LeadCard({ lead, onClaim, showClaimBtn, selectable, isSelected, onSelect }) {
  const navigate = useNavigate();

  return (
    <div
      className={`lead-card ${isSelected ? 'selected' : ''}`}
      onClick={(e) => {
        // If clicking on the card (but not the checkbox itself), and it's selectable, we might want to navigate or toggle.
        // Usually, clicking anywhere navigates, and clicking checkbox selects.
        navigate(`/leads/${lead.id}`);
      }}
      id={`lead-card-${lead.id}`}
      style={isSelected ? { border: '1px solid var(--primary)', backgroundColor: 'var(--bg-card-hover)' } : {}}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        {selectable && (
          <div onClick={(e) => e.stopPropagation()} style={{ marginTop: 2 }}>
            <input 
              type="checkbox" 
              className="form-input" 
              style={{ width: 18, height: 18, cursor: 'pointer' }}
              checked={isSelected || false}
              onChange={(e) => {
                onSelect?.(lead.id, e.target.checked);
              }}
            />
          </div>
        )}
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span className="lead-name">{lead.name}</span>
            <StatusBadge status={lead.status || 'unassigned'} />
            {lead.source_priority === 'high' && (
              <span className="badge" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)', fontSize: '0.65rem' }}>High Priority</span>
            )}
          </div>
          <div className="lead-meta">
            {lead.profession && <span><User size={12} style={{ display: 'inline', marginRight: 3 }} />{lead.profession}</span>}
            {lead.age !== null && lead.age !== undefined && <span>Age: {lead.age}</span>}
            {lead.phone_number && <span><Phone size={12} style={{ display: 'inline', marginRight: 3 }} />{lead.phone_number}</span>}
            {lead.email && <span><Mail size={12} style={{ display: 'inline', marginRight: 3 }} />{lead.email}</span>}
            {lead.source_name && <span>Source: {lead.source_name}</span>}
            {lead.assigned_rep_name && <span>Rep: {lead.assigned_rep_name}</span>}
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {showClaimBtn && !lead.assigned_rep_id && (
          <button
            className="btn btn-primary btn-sm"
            id={`claim-lead-btn-${lead.id}`}
            onClick={(e) => { e.stopPropagation(); onClaim?.(lead.id); }}
          >
            Claim
          </button>
        )}
        <ChevronRight size={16} color="var(--text-muted)" />
      </div>
    </div>
  );
}
