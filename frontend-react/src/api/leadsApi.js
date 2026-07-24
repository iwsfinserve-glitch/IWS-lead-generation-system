import api from './axiosInstance';

export const getLeads = (params = {}) =>
  api.get('/leads/', { params }).then((r) => r.data);

export const getLead = (id) =>
  api.get(`/leads/${id}`).then((r) => r.data);

export const createLead = (data) =>
  api.post('/leads/', data).then((r) => r.data);

export const updateLead = (id, data) =>
  api.patch(`/leads/${id}`, data).then((r) => r.data);

export const deleteLead = (id) =>
  api.delete(`/leads/${id}`).then((r) => r.data);

export const claimLead = (id) =>
  api.patch(`/leads/${id}/claim`).then((r) => r.data);

export const getLeadTimeline = (id) =>
  api.get(`/leads/${id}/timeline`).then((r) => r.data);

export const addTimelineNote = (id, data) =>
  api.post(`/leads/${id}/timeline`, data).then((r) => r.data);

export const getLeadsSummary = () =>
  api.get('/leads/summary').then((r) => r.data);

export const getSources = () =>
  api.get('/sources/').then((r) => r.data);

// Sales reps list is on the auth router
export const getSalesReps = () =>
  api.get('/auth/sales-reps').then((r) => r.data);

export const bulkImportLeads = (formData) =>
  api.post('/leads/bulk-import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((r) => r.data);

export const bulkAssignLeads = (data) =>
  api.post('/leads/bulk-assign', data).then((r) => r.data);

export const bulkDeleteLeads = (data) =>
  api.post('/leads/bulk-delete', data).then((r) => r.data);


