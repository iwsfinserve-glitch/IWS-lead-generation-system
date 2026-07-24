export const STATUS_DISPLAY = {
  new: 'New',
  in_progress: 'In Progress',
  potential: 'Potential',
  non_potential: 'Non-Potential',
  converted_to_investor: 'Converted',
  existing_investor: 'Existing Investor',
  unassigned: 'Unassigned',
};

export const STATUS_BADGE_CLASS = {
  new: 'badge-new',
  in_progress: 'badge-progress',
  potential: 'badge-potential',
  non_potential: 'badge-non-pot',
  converted_to_investor: 'badge-converted',
  existing_investor: 'badge-investor',
  unassigned: 'badge-unassigned',
};

export const STATUS_COLOR = {
  new: '#3b82f6',
  in_progress: '#f59e0b',
  potential: '#8b5cf6',
  non_potential: '#ef4444',
  converted_to_investor: '#10b981',
  existing_investor: '#059669',
  unassigned: '#64748b',
};

export const ROLE_BADGE = {
  admin: 'badge-admin',
  manager: 'badge-manager',
  sales_rep: 'badge-sales-rep',
};

export const ROLE_LABEL = {
  admin: 'Admin',
  manager: 'Manager',
  sales_rep: 'Sales Rep',
};

export function StatusBadge({ status }) {
  const cls = STATUS_BADGE_CLASS[status] || 'badge-unassigned';
  const label = STATUS_DISPLAY[status] || status;
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function RoleBadge({ role }) {
  const cls = ROLE_BADGE[role] || 'badge-unassigned';
  const label = ROLE_LABEL[role] || role;
  return <span className={`badge ${cls}`}>{label}</span>;
}
