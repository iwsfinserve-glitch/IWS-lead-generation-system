# Implementation Plan — Streamlit → React Frontend Migration
### Lead Management CRM

Replace the Streamlit frontend with a React (Vite) single-page application. Preserve 100% of existing features — role-based access (Admin, Manager, Sales Rep), AI insights, report generation, Google Calendar sync — while eliminating the auth/cookie-sync/iframe-reload issues inherent to Streamlit.

The FastAPI + PostgreSQL backend is complete and unchanged in behavior. This is a frontend replacement, not a backend rewrite — no API contract changes.

---

## Target Frontend Stack

| Concern | Choice |
|---|---|
| Framework | React 18 + Vite |
| Routing | `react-router-dom` v6, with protected + role-based route guards |
| Auth/state | React Context (`AuthContext`) — JWT access/refresh tokens in `localStorage`, Axios interceptors handle attach + auto-refresh on 401 |
| Styling | Tailwind CSS + a small custom CSS layer for the glassmorphism dashboard look |
| Icons | `lucide-react` |
| Charts | `recharts` |
| Toasts/alerts | `react-hot-toast` |
| Report downloads | Native blob download of the `.docx` files the backend already returns — **not** a format change to CSV |

---

## Decisions to confirm before build starts

1. **Token storage.** Plan is JWT in `localStorage` with Axios interceptor auto-refresh via `/api/v1/auth/refresh`. This is simpler than httpOnly cookies but has a larger XSS surface — confirm this tradeoff is acceptable rather than defaulting to it silently.
2. **CORS origins.** `ALLOWED_ORIGINS` needs `http://localhost:5173` (Vite dev) and `http://localhost:3000` added. Confirm the production frontend domain so it can be added in the same change.
3. **UI theme.** Dark mode, light mode, or a hybrid glassmorphism default? Pick one now — leaving this open causes the generator to guess per-page and produces visual inconsistency across pages.

---

## Backend Changes Required

- **`backend/app/core/config.py`** — update `ALLOWED_ORIGINS` default to include the Vite dev origins.
- **`backend/.env`** — set `ALLOWED_ORIGINS="http://localhost:5173,http://localhost:3000,http://localhost:8501,http://localhost:8000"`.
- No route, schema, or response-shape changes. React consumes existing endpoints as-is, including the four `.docx` report endpoints.

---

## React Frontend Directory Structure

```
frontend-react/
├── index.html
├── package.json
├── vite.config.js
├── tailwind.config.js
├── src/
│   ├── main.jsx
│   ├── App.jsx
│   ├── index.css
│   ├── api/
│   │   ├── axiosInstance.js
│   │   ├── authApi.js
│   │   ├── leadsApi.js
│   │   ├── appointmentsApi.js
│   │   ├── tasksApi.js
│   │   ├── reportsApi.js
│   │   ├── notificationsApi.js
│   │   ├── aiApi.js
│   │   └── usersApi.js
│   ├── context/
│   │   ├── AuthContext.jsx
│   │   └── NotificationContext.jsx
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.jsx
│   │   │   ├── Navbar.jsx
│   │   │   └── ProtectedRoute.jsx
│   │   ├── common/
│   │   │   ├── MetricCard.jsx
│   │   │   ├── StatusBadge.jsx
│   │   │   ├── Pagination.jsx
│   │   │   └── Modal.jsx
│   │   ├── cards/
│   │   │   ├── LeadCard.jsx
│   │   │   ├── TaskCard.jsx
│   │   │   ├── AppointmentCard.jsx
│   │   │   └── UserCard.jsx
│   │   ├── modals/
│   │   │   ├── CreateLeadModal.jsx
│   │   │   ├── ScheduleAppointmentModal.jsx
│   │   │   ├── CreateTaskModal.jsx
│   │   │   ├── TransferLeadModal.jsx
│   │   │   ├── RequestDueDateModal.jsx
│   │   │   └── ManageUserModal.jsx
│   │   └── ai/
│   │       ├── AIScoreCard.jsx
│   │       ├── AIContactTimingCard.jsx
│   │       └── AIClassificationCard.jsx
│   └── pages/
│       ├── LoginPage.jsx
│       ├── DashboardPage.jsx
│       ├── AllLeadsPage.jsx
│       ├── LeadDetailsPage.jsx
│       ├── AppointmentsPage.jsx
│       ├── TasksPage.jsx
│       ├── ReportsPage.jsx
│       └── UserDetailsPage.jsx
```

---

## Quick Reference: Page Mapping

| Streamlit page | React page | Key features |
|---|---|---|
| `0_Login.py` | `LoginPage.jsx` | Email/password form, quick-login demo buttons (Admin/Manager/Sales Rep), inline validation, redirect to `/dashboard` |
| `1_Dashboard.py` | `DashboardPage.jsx` | Role-based metric cards; Sales Rep: leads + appointments/tasks panels; Manager: reports directory; Admin: user directory + create-user modal |
| `2_Appointments.py` | `AppointmentsPage.jsx` | Month/List toggle, Google Calendar sync status banner, connect/sync/disconnect, filters, schedule modal |
| `3_Tasks.py` | `TasksPage.jsx` | Pending/Completed tabs, extension-request tab, self-assign vs. admin-assign task modals, approve/reject extensions |
| `4_Reports.py` | `ReportsPage.jsx` | 4 report types (Periodic Leads, User Performance, Team Performance, Lead Journey), recharts breakdowns, `.docx` download per report |
| `5_User_Details.py` | `UserDetailsPage.jsx` | Profile overview, edit-user modal, tabs for assigned leads/tasks/appointments |
| `6_All_Leads.py` | `AllLeadsPage.jsx` | Tabs (Active, Unassigned + claim action, Converted, Investors, Transfer Requests, Full Directory), filters, create-lead modal |
| `7_Lead_Details.py` | `LeadDetailsPage.jsx` | Full profile header, status/transfer/claim/book/add-task actions, timeline + notes, AI Insights (score, contact timing, classification) |

---

## Detailed Component & Page Plan

**Core API & Auth Layer**
- `axiosInstance.js` — base URL `http://localhost:8000/api/v1`, attaches `Authorization: Bearer <token>`, retries once after a silent `/auth/refresh` on 401.
- `AuthContext.jsx` — holds `user`, `token`; exposes `login()`, `logout()`, session hydration via `/auth/me` on load, and `isAdmin` / `isManager` / `isSalesRep` helpers.

**LoginPage** — form + demo quick-fill buttons, loading state, error toast on failure.

**DashboardPage** — role-branches the same route into three views (see mapping table); each view is its own component composed from `MetricCard` + role-specific list/table.

**AllLeadsPage / LeadDetailsPage** — tab state lives in the page, filters (status/source/rep/search) drive a single query hook shared across tabs; Lead Details renders `AIScoreCard`, `AIContactTimingCard`, `AIClassificationCard` from live data, not placeholders.

**AppointmentsPage** — calendar/list view toggle; Google Calendar banner reads `/auth/google/status` and exposes connect/sync/disconnect actions; schedule modal covers lead select, title, date, start/end time, mode, location, notes.

**TasksPage** — pending/completed/extension-request tabs; self-assign modal for Sales Reps, assign-to modal for Admin/Manager; extension approval flow for Admin/Manager.

**ReportsPage** — 4 tabs as in the mapping table; each tab renders a chart + narrative summary and triggers a `.docx` blob download — this must hit the existing report endpoints unchanged.

**UserDetailsPage** — profile header, edit modal, tabbed sub-views for leads/tasks/appointments tied to that user.

---

## Phased Execution Order

Build in this order — each phase should be a separate generation pass, not one single dump:

1. **Setup & core infra** — Vite init, dependencies (`react-router-dom`, `axios`, `lucide-react`, `recharts`, `react-hot-toast`), Tailwind config, global CSS design tokens.
2. **Auth context & API client** — `axiosInstance.js`, `AuthContext.jsx`, `ProtectedRoute.jsx`.
3. **Layout & navigation** — `Sidebar.jsx`, `Navbar.jsx`, role-based menu items.
4. **Core CRM pages** — `LoginPage`, `DashboardPage`, `AllLeadsPage`, `LeadDetailsPage` (including the AI insight cards).
5. **Secondary modules** — `AppointmentsPage` (Google Calendar), `TasksPage`, `ReportsPage`, `UserDetailsPage`.
6. **Verification & cleanup** — full manual pass below, then remove/archive the Streamlit `frontend/` code.

---

## Verification Plan

**Automated**
- `npm run build` — zero compile errors.
- `curl http://localhost:8000/health` — backend up, and confirm CORS headers on a React-origin request.

**Manual, end to end**
1. Log in as Admin, Manager, and Sales Rep with demo credentials; confirm JWT persists across a page refresh.
2. Multi-user isolation: one browser window logged in as Admin, an Incognito window logged in as Sales Rep — confirm each shows strictly its own data (no session bleed).
3. Dashboard & navigation: role-specific metric cards, sidebar, search/filtering.
4. Leads: create a lead, claim an unassigned lead, change status, add a timeline note.
5. AI Insights: open Lead Details, confirm score, best contact timing, and classification load from live data.
6. Appointments & Tasks: create an appointment, create a task, request a due-date extension, approve it as Manager/Admin.
7. Reports: generate all 4 report types and confirm the `.docx` download actually executes and opens.
8. Google Calendar: check connection status, connect, sync, disconnect.
