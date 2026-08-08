import api from './axiosInstance';

// Reports use /reports/* prefix
// Periodic leads endpoint is /reports/leads-periodic
// Lead journey is /reports/lead-journey/{id}
// User performance is /reports/user-performance/{id}
// Team performance is /reports/team-performance

export const getLeadJourneyReport = (leadId) =>
  api.get(`/reports/lead-journey/${leadId}`).then((r) => r.data);

export const getPeriodicLeadsReport = (params = {}) =>
  api.get('/reports/leads-periodic', { params }).then((r) => r.data);

export const getUserPerformanceReport = (userId, params = {}) =>
  api.get(`/reports/user-performance/${userId}`, { params }).then((r) => r.data);

export const getTeamPerformanceReport = (params = {}) =>
  api.get('/reports/team-performance', { params }).then((r) => r.data);

// Returns RBAC-filtered leads for the Lead Journey dropdown
// - sales_rep: their assigned leads only
// - manager: their team's leads
// - admin: all leads with status != unassigned
export const getJourneyLeads = () =>
  api.get('/reports/journey-leads').then((r) => r.data);
