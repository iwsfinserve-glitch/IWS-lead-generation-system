import api from './axiosInstance';

// GET /api/v1/tasks/?user_id=X&skip=X&limit=X
// Note: backend param is "user_id" (NOT "assigned_to_id")
export const getTasks = (params = {}) => {
  // Remap assigned_to_id → user_id for backend compatibility
  const { assigned_to_id, ...rest } = params;
  const backendParams = { ...rest };
  if (assigned_to_id !== undefined) backendParams.user_id = assigned_to_id;
  return api.get('/tasks/', { params: backendParams }).then((r) => r.data);
};

export const getTask = (id) =>
  api.get(`/tasks/${id}`).then((r) => r.data);

export const createTask = (data) =>
  api.post('/tasks/', data).then((r) => r.data);

export const updateTask = (id, data) =>
  api.patch(`/tasks/${id}`, data).then((r) => r.data);

export const deleteTask = (id) =>
  api.delete(`/tasks/${id}`).then((r) => r.data);

// Due-date extension requests (/api/v1/due-date-requests)
export const getDueDateRequests = (params = {}) =>
  api.get('/due-date-requests/', { params }).then((r) => r.data);

export const createDueDateRequest = (data) =>
  api.post('/due-date-requests/', data).then((r) => r.data);

export const updateDueDateRequest = (id, data) =>
  api.patch(`/due-date-requests/${id}`, data).then((r) => r.data);
