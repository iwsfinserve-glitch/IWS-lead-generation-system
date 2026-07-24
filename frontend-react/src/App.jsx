import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/layout/ProtectedRoute';
import Sidebar from './components/layout/Sidebar';

import LoginPage        from './pages/LoginPage';
import DashboardPage    from './pages/DashboardPage';
import AllLeadsPage     from './pages/AllLeadsPage';
import LeadDetailsPage  from './pages/LeadDetailsPage';
import AppointmentsPage from './pages/AppointmentsPage';
import TasksPage        from './pages/TasksPage';
import ReportsPage      from './pages/ReportsPage';
import UserDetailsPage  from './pages/UserDetailsPage';
import UsersPage        from './pages/UsersPage';

// Layout wrapper for authenticated pages
function AppLayout() {
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="main-content">
        <Outlet />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: 'var(--bg-card-solid)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
              fontSize: '0.875rem',
              fontFamily: 'var(--font-sans)',
            },
            success: { iconTheme: { primary: 'var(--success)', secondary: '#fff' } },
            error:   { iconTheme: { primary: 'var(--danger)',  secondary: '#fff' } },
          }}
        />

        <Routes>
          {/* Public */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protected layout */}
          <Route element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }>
            <Route path="/dashboard"        element={<DashboardPage />} />
            <Route path="/leads"            element={<AllLeadsPage />} />
            <Route path="/leads/:id"        element={<LeadDetailsPage />} />
            <Route path="/appointments"     element={<AppointmentsPage />} />
            <Route path="/tasks"            element={<TasksPage />} />
            <Route path="/reports"          element={<ReportsPage />} />
            <Route path="/users"            element={
              <ProtectedRoute roles={['admin', 'manager']}>
                <UsersPage />
              </ProtectedRoute>
            } />
            <Route path="/users/:id"        element={<UserDetailsPage />} />
          </Route>

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
