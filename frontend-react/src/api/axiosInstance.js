import axios from 'axios';

const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').trim();
let normalizedBaseUrl = rawBaseUrl;
if (normalizedBaseUrl && !normalizedBaseUrl.startsWith('http://') && !normalizedBaseUrl.startsWith('https://')) {
  normalizedBaseUrl = `https://${normalizedBaseUrl}`;
}

const API_PREFIX = normalizedBaseUrl ? `${normalizedBaseUrl.replace(/\/+$/, '')}/api/v1` : '/api/v1';

const axiosInstance = axios.create({
  baseURL: API_PREFIX,
  timeout: 90000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Request interceptor: attach JWT ────────────────────────────────
axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor: handle 401 gracefully ────────────────────
// Strategy: on a 401, try one token refresh. If the refresh itself
// fails (or there is no refresh_token), just dispatch a custom event
// so AuthContext can cleanly log the user out — NO hard redirect here.
// Hard redirects from the interceptor cause the "logged out on click" bug.

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) prom.reject(error);
    else prom.resolve(token);
  });
  failedQueue = [];
};

const dispatchLogout = () => {
  // Fire a custom event that AuthContext listens to — keeps routing inside React
  window.dispatchEvent(new CustomEvent('auth:logout'));
};

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Format FastAPI 422 validation error arrays into a single string to prevent React toast crash
    if (error.response?.status === 422 && Array.isArray(error.response.data?.detail)) {
      const details = error.response.data.detail;
      error.response.data.detail = details.map(d => {
          const loc = d.loc?.filter(l => l !== 'body' && l !== 'query').join('.') || '';
          return loc ? `${loc}: ${d.msg}` : d.msg;
      }).join(', ');
    }

    const originalRequest = error.config;

    // Only attempt refresh on 401; all other errors pass through normally
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    const refreshToken = localStorage.getItem('refresh_token');

    // No refresh token available — signal logout cleanly
    if (!refreshToken) {
      dispatchLogout();
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return axiosInstance(originalRequest);
      }).catch((err) => Promise.reject(err));
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const res = await axios.post(`${API_PREFIX}/auth/refresh`, { refresh_token: refreshToken });
      const newToken = res.data.access_token;
      localStorage.setItem('access_token', newToken);
      if (res.data.refresh_token) {
        localStorage.setItem('refresh_token', res.data.refresh_token);
      }
      axiosInstance.defaults.headers.common.Authorization = `Bearer ${newToken}`;
      processQueue(null, newToken);
      originalRequest.headers.Authorization = `Bearer ${newToken}`;
      return axiosInstance(originalRequest);
    } catch (refreshErr) {
      processQueue(refreshErr, null);
      dispatchLogout();  // Clean logout via React, not window.location
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }
  }
);

export default axiosInstance;
