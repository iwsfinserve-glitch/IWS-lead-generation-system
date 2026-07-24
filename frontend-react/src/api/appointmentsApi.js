import api from './axiosInstance';

// Backend route: GET /api/v1/appointments/ (trailing slash required)
export const getAppointments = (params = {}) =>
  api.get('/appointments/', { params }).then((r) => r.data);

export const getAppointment = (id) =>
  api.get(`/appointments/${id}`).then((r) => r.data);

export const createAppointment = (data) =>
  api.post('/appointments/', data).then((r) => r.data);

export const updateAppointment = (id, data) =>
  api.patch(`/appointments/${id}`, data).then((r) => r.data);

export const deleteAppointment = (id) =>
  api.delete(`/appointments/${id}`).then((r) => r.data);
