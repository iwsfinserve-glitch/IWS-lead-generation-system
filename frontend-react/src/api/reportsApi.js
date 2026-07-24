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
