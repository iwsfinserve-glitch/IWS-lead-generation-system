import api from './axiosInstance';

export const login = (email, password) => {
  // Backend uses OAuth2PasswordRequestForm — must send as form-encoded
  const form = new URLSearchParams();
  form.append('username', email);
  form.append('password', password);
  return api.post('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  }).then((r) => r.data);
};

export const getMe = () =>
  api.get('/auth/me').then((r) => r.data);

export const refreshToken = (refresh_token) =>
  api.post('/auth/refresh', { refresh_token }).then((r) => r.data);

export const getGoogleStatus = () =>
  api.get('/auth/google/status').then((r) => r.data);

export const getGoogleConnectUrl = async () => {
  const token = localStorage.getItem('access_token');
  // Ensure we use the absolute backend URL so the browser navigates directly to the backend
  // instead of the frontend React router catching the route and redirecting to the dashboard.
  const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').trim();
  let normalizedBaseUrl = rawBaseUrl;
  if (normalizedBaseUrl && !normalizedBaseUrl.startsWith('http://') && !normalizedBaseUrl.startsWith('https://')) {
    normalizedBaseUrl = `https://${normalizedBaseUrl}`;
  }
  const prefix = normalizedBaseUrl ? `${normalizedBaseUrl.replace(/\/+$/, '')}/api/v1` : '/api/v1';
  return `${prefix}/auth/google/connect?token=${token}`;
};

export const googleDisconnect = () =>
  api.delete('/auth/google/disconnect').then((r) => r.data);

export const googleSync = () =>
  api.post('/auth/google/sync-appointments').then((r) => r.data);
