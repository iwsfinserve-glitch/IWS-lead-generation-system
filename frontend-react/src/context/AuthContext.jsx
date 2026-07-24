import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { login as apiLogin, getMe } from '../api/authApi';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [token, setToken]     = useState(null);
  const [loading, setLoading] = useState(true);

  const clearAuth = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setToken(null);
    setUser(null);
  }, []);

  // Hydrate from localStorage on first mount
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    if (!storedToken) {
      setLoading(false);
      return;
    }

    setToken(storedToken);
    getMe()
      .then((u) => setUser(u))
      .catch((err) => {
        // Only clear tokens on a confirmed 401 — not on network errors
        if (err.response?.status === 401) {
          clearAuth();
        }
        // On network/server errors, keep the token so the user isn't
        // logged out just because the backend is slow to start
      })
      .finally(() => setLoading(false));
  }, [clearAuth]);

  // Listen for logout events dispatched by the axios interceptor
  useEffect(() => {
    const handler = () => clearAuth();
    window.addEventListener('auth:logout', handler);
    return () => window.removeEventListener('auth:logout', handler);
  }, [clearAuth]);

  const login = useCallback(async (email, password) => {
    const data = await apiLogin(email, password);
    const { access_token, refresh_token } = data;

    localStorage.setItem('access_token', access_token);
    // refresh_token is Optional in the backend schema — guard against null/undefined
    if (refresh_token) {
      localStorage.setItem('refresh_token', refresh_token);
    }

    setToken(access_token);
    const me = await getMe();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(() => {
    clearAuth();
  }, [clearAuth]);

  const isAdmin          = user?.role === 'admin';
  const isManager        = user?.role === 'manager';
  const isSalesRep       = user?.role === 'sales_rep';
  const isManagerOrAdmin = isAdmin || isManager;

  return (
    <AuthContext.Provider value={{
      user, token, loading,
      login, logout,
      isAdmin, isManager, isSalesRep, isManagerOrAdmin,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
