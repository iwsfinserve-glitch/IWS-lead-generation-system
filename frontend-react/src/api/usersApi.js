import api from './axiosInstance';

// Users are managed via /auth router
export const getUsers = () =>
  api.get('/auth/users').then((r) => r.data);

/** Get the current logged-in user's own profile — no admin required */
export const getMe = () =>
  api.get('/auth/me').then((r) => r.data);

// No single-user GET endpoint exists — fetch all and find by ID
export const getUser = async (id) => {
  const users = await api.get('/auth/users').then((r) => r.data);
  const found = users.find((u) => String(u.id) === String(id));
  if (!found) throw new Error(`User ${id} not found`);
  return found;
};

export const createUser = (data) =>
  api.post('/auth/register', data).then((r) => r.data);

export const updateUser = (id, data) =>
  api.patch(`/auth/users/${id}`, data).then((r) => r.data);

export const deleteUser = (id) =>
  api.delete(`/auth/users/${id}`).then((r) => r.data);

// Lead transfer requests (prefix: /lead-transfer-requests)
export const getLeadTransferRequests = (params = {}) =>
  api.get('/lead-transfer-requests/', { params }).then((r) => r.data);

export const createLeadTransfer = (data) =>
  api.post('/lead-transfer-requests/', data).then((r) => r.data);

export const updateLeadTransfer = (id, data) =>
  api.patch(`/lead-transfer-requests/${id}`, data).then((r) => r.data);

/**
 * Returns the list of users eligible to receive a lead transfer,
 * filtered by the current user's role (see backend /auth/transfer-targets).
 */
export const getTransferTargets = () =>
  api.get('/auth/transfer-targets').then((r) => r.data);

/**
 * Directly transfer a lead to another user (manager/admin only).
 * No approval required — the reassignment happens immediately.
 */
export const createDirectLeadTransfer = (data) =>
  api.post('/lead-transfer-requests/direct', data).then((r) => r.data);

