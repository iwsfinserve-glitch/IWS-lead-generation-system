import api from './axiosInstance';

export const getNotifications = (params = {}) =>
  api.get('/notifications/', { params }).then((r) => r.data);

export const getUnreadCount = () =>
  api.get('/notifications/unread-count').then((r) => r.data);

export const markNotificationRead = (id) =>
  api.patch(`/notifications/${id}/read`).then((r) => r.data);

export const markAllRead = () =>
  api.patch('/notifications/read-all').then((r) => r.data);

export const deleteNotification = (id) =>
  api.delete(`/notifications/${id}`).then((r) => r.data);

