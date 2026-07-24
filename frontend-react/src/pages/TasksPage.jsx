import { useState, useEffect, useCallback } from 'react';
import { Plus, CheckCircle2, Clock, AlertCircle } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import Pagination from '../components/common/Pagination';
import CreateTaskModal from '../components/modals/CreateTaskModal';
import RequestDueDateModal from '../components/modals/RequestDueDateModal';
import { getTasks, updateTask, getDueDateRequests, updateDueDateRequest } from '../api/tasksApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

const PAGE_SIZE = 15;

function TaskCard({ task, onComplete, onExtend, onApproveExt, onRejectExt, isManagerOrAdmin, isSelf }) {
  const isPending   = task.status === 'needsAction';
  const isCompleted = task.status === 'completed';
  const targetEnd   = task.end_time ? new Date(task.end_time) : (task.due ? new Date(`${task.due}T23:59:59`) : null);
  const isOverdue   = isPending && targetEnd && targetEnd < new Date();

  const formattedEndTime = task.end_time
    ? new Date(task.end_time).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
    : null;

  return (
    <div className="glass-card" style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, alignItems: 'start', borderLeft: `3px solid ${isOverdue ? 'var(--danger)' : isCompleted ? 'var(--success)' : 'var(--primary)'}` }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
          {isCompleted ? <CheckCircle2 size={16} color="var(--success)" /> : isOverdue ? <AlertCircle size={16} color="var(--danger)" /> : <Clock size={16} color="var(--primary-light)" />}
          <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{task.title}</span>
          {isOverdue && <span className="badge badge-non-pot">Overdue</span>}
          {isCompleted && <span className="badge badge-converted">Done</span>}
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {formattedEndTime ? (
            <span>⏰ End: {formattedEndTime}</span>
          ) : task.due ? (
            <span>📅 Due: {task.due}</span>
          ) : null}
          {task.user_name  && <span>🧑 {task.user_name}</span>}
          {task.assigned_by_name && <span>👤 Assigned by: {task.assigned_by_name}</span>}
        </div>
        {task.notes && <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 6, fontStyle: 'italic' }}>{task.notes}</div>}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
        {isPending && isSelf && (
          <>
            <button className="btn btn-primary btn-sm" onClick={() => onComplete(task.id)} id={`task-complete-${task.id}`}>
              <CheckCircle2 size={13} /> Done
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => onExtend(task)} id={`task-extend-${task.id}`}>
              Extend
            </button>
          </>
        )}
        {isPending && !isSelf && isManagerOrAdmin && (
          <button className="btn btn-primary btn-sm" onClick={() => onComplete(task.id)} id={`task-complete-mgr-${task.id}`}>
            <CheckCircle2 size={13} /> Done
          </button>
        )}
      </div>
    </div>
  );
}


function ExtRequestCard({ req, onApprove, onReject }) {
  const reqTimeStr = req.requested_end_time
    ? new Date(req.requested_end_time).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
    : req.requested_due_date;
  const isPending = req.status === 'pending';

  return (
    <div className="glass-card" style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, alignItems: 'center' }}>
      <div>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{req.task_title || `Task #${req.task_id}`}</div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Requested by: <b>{req.requested_by_name || 'Unknown'}</b> · New due: <b>{reqTimeStr}</b>
        </div>
        {req.reason && <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 4, fontStyle: 'italic' }}>{req.reason}</div>}
      </div>
      <div>
        {isPending ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={() => onApprove(req.id)} id={`ext-approve-${req.id}`}>Approve</button>
            <button className="btn btn-danger btn-sm"  onClick={() => onReject(req.id)}  id={`ext-reject-${req.id}`}>Reject</button>
          </div>
        ) : (
          <span className={`badge ${req.status === 'approved' ? 'badge-converted' : 'badge-non-pot'}`}>
            {req.status.toUpperCase()}
          </span>
        )}
      </div>
    </div>
  );
}

export default function TasksPage() {
  const { user, isManagerOrAdmin, isSalesRep } = useAuth();
  const [tasks, setTasks]         = useState([]);
  const [extReqs, setExtReqs]     = useState([]);
  const [loading, setLoading]     = useState(true);
  const [tab, setTab]             = useState('pending');
  const [page, setPage]           = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [extTask, setExtTask]     = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [t, e] = await Promise.all([
        getTasks({ limit: 500 }),
        isManagerOrAdmin ? getDueDateRequests({ status: 'pending' }) : Promise.resolve([]),
      ]);
      setTasks(t);
      setExtReqs(e);
    } catch { toast.error('Failed to load tasks'); }
    finally { setLoading(false); }
  }, [isManagerOrAdmin]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleComplete = async (id) => {
    try {
      await updateTask(id, { status: 'completed' });
      toast.success('Task completed!');
      fetchAll();
    } catch { toast.error('Failed to update task'); }
  };

  const handleExtRequest = (task) => setExtTask(task);

  const handleApproveExt = async (id) => {
    try {
      await updateDueDateRequest(id, { status: 'approved' });
      toast.success('Extension approved!');
      setExtReqs((prev) => prev.filter((r) => r.id !== id));
      fetchAll();
    } catch { toast.error('Failed'); }
  };

  const handleRejectExt = async (id) => {
    try {
      await updateDueDateRequest(id, { status: 'rejected' });
      toast.success('Extension rejected.');
      setExtReqs((prev) => prev.filter((r) => r.id !== id));
      fetchAll();
    } catch { toast.error('Failed'); }
  };

  const pending   = tasks.filter((t) => t.status === 'needsAction');
  const completed = tasks.filter((t) => t.status === 'completed');

  const TABS = [
    { key: 'pending',   label: 'Pending',   data: pending },
    { key: 'completed', label: 'Completed',  data: completed },
    ...(isManagerOrAdmin ? [{ key: 'extensions', label: 'Extension Requests', data: extReqs }] : []),
  ];

  const activeTab  = TABS.find((t) => t.key === tab) || TABS[0];
  const tabData    = activeTab.data;
  const paginated  = tabData.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <>
      <Navbar title="Tasks" />
      <div className="page-container">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Tasks</h1>
            <p style={{ color: 'var(--text-muted)' }}>{pending.length} pending · {completed.length} completed</p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)} id="create-task-btn">
            <Plus size={16} /> New Task
          </button>
        </div>

        {/* Tabs */}
        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={`tab ${tab === t.key ? 'active' : ''}`}
              onClick={() => { setTab(t.key); setPage(1); }} id={`task-tab-${t.key}`}>
              {t.label} <span style={{ opacity: 0.6, fontSize: '0.75em', marginLeft: 4 }}>({t.data.length})</span>
            </button>
          ))}
        </div>

        {loading ? (
          <div className="loading-center"><div className="spinner" /> Loading…</div>
        ) : tab === 'extensions' ? (
          extReqs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">✅</div>
              <div className="empty-state-title">No pending extension requests</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {extReqs.map((r) => <ExtRequestCard key={r.id} req={r} onApprove={handleApproveExt} onReject={handleRejectExt} />)}
            </div>
          )
        ) : paginated.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">✅</div>
            <div className="empty-state-title">No {tab} tasks</div>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {paginated.map((t) => (
                <TaskCard
                  key={t.id}
                  task={t}
                  isManagerOrAdmin={isManagerOrAdmin}
                  isSelf={String(t.user_id) === String(user?.id)}
                  onComplete={handleComplete}
                  onExtend={handleExtRequest}
                />
              ))}
            </div>
            <Pagination total={tabData.length} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </div>

      {showCreate && <CreateTaskModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); fetchAll(); }} />}
      {extTask && <RequestDueDateModal task={extTask} onClose={() => setExtTask(null)} onRequested={() => { setExtTask(null); fetchAll(); }} />}
    </>
  );
}
