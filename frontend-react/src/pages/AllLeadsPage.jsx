import { useState, useEffect, useCallback } from 'react';
import { Search, Plus, Filter } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import LeadCard from '../components/cards/LeadCard';
import Pagination from '../components/common/Pagination';
import CreateLeadModal from '../components/modals/CreateLeadModal';
import BulkImportModal from '../components/modals/BulkImportModal';
import BulkAssignModal from '../components/modals/BulkAssignModal';
import { getLeads, claimLead, getLeadsSummary, bulkDeleteLeads } from '../api/leadsApi';
import { getLeadTransferRequests, updateLeadTransfer } from '../api/usersApi';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';

const PAGE_SIZE = 15;

const TABS_MANAGER = ['All Leads', 'Unassigned', 'Active', 'Converted', 'Investors', 'Transfers'];
const TABS_REP     = ['All Leads', 'Unassigned', 'Active', 'Converted', 'Investors'];

export default function AllLeadsPage() {
  const { isManagerOrAdmin, user } = useAuth();
  const TABS = isManagerOrAdmin ? TABS_MANAGER : TABS_REP;

  const [tab, setTab]             = useState('All Leads');
  const [leads, setLeads]         = useState([]);
  const [summary, setSummary]     = useState({});
  const [transfers, setTransfers] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showBulkImport, setShowBulkImport] = useState(false);
  const [showBulkAssign, setShowBulkAssign] = useState(false);
  const [selectedLeadIds, setSelectedLeadIds] = useState(new Set());
  const [search, setSearch]       = useState('');
  const [page, setPage]           = useState(1);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [l, s] = await Promise.all([getLeads({ limit: 20000 }), getLeadsSummary().catch(() => ({}))]);
      setLeads(l);
      setSummary(s);
      if (isManagerOrAdmin) {
        const t = await getLeadTransferRequests({ status: 'pending' });
        setTransfers(t);
      }
    } catch {
      toast.error('Failed to load leads');
    } finally {
      setLoading(false);
    }
  }, [isManagerOrAdmin]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleClaim = async (leadId) => {
    try {
      await claimLead(leadId);
      toast.success('Lead claimed!');
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not claim lead');
    }
  };

  const handleTransfer = async (id, status) => {
    try {
      await updateLeadTransfer(id, { status });
      toast.success(status === 'approved' ? 'Transfer approved!' : 'Transfer rejected.');
      fetchData();
    } catch {
      toast.error('Action failed');
    }
  };

  const handleBulkDelete = async () => {
    if (!window.confirm(`Are you sure you want to permanently delete ${selectedLeadIds.size} leads? This action cannot be undone.`)) {
      return;
    }
    try {
      const res = await bulkDeleteLeads({ lead_ids: Array.from(selectedLeadIds) });
      toast.success(`Deleted ${res.deleted_count} leads.`);
      setSelectedLeadIds(new Set());
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete leads');
    }
  };

  // Filter leads by tab
  const tabLeads = () => {
    let base = leads;
    if (search.trim()) {
      const t = search.toLowerCase();
      base = base.filter((l) => l.name.toLowerCase().includes(t) || (l.profession || '').toLowerCase().includes(t));
    }
    switch (tab) {
      case 'Unassigned': return base.filter((l) => l.status === 'unassigned');
      case 'Active':     return base.filter((l) => ['in_progress', 'potential', 'non_potential'].includes(l.status));
      case 'Converted':  return base.filter((l) => l.status === 'converted_to_investor');
      case 'Investors':  return base.filter((l) => l.status === 'existing_investor');
      case 'Transfers':  return [];
      default:           return base;
    }
  };

  const filtered = tabLeads();
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const tabCount = (t) => {
    switch (t) {
      case 'All Leads':  return summary.total || leads.length;
      case 'Unassigned': return summary.unassigned || leads.filter((l) => l.status === 'unassigned').length;
      case 'Active':     return ((summary.in_progress || 0) + (summary.potential || 0) + (summary.non_potential || 0)) || leads.filter((l) => ['in_progress', 'potential', 'non_potential'].includes(l.status)).length;
      case 'Converted':  return summary.converted_to_investor || leads.filter((l) => l.status === 'converted_to_investor').length;
      case 'Investors':  return summary.existing_investor || leads.filter((l) => l.status === 'existing_investor').length;
      case 'Transfers':  return transfers.length;
      default: return 0;
    }
  };

  return (
    <>
      <Navbar title="All Leads" />
      <div className="page-container">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Lead Directory</h1>
            <p style={{ color: 'var(--text-muted)' }}>Manage and track all your leads in one place.</p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {isManagerOrAdmin && (
              <button className="btn btn-ghost" onClick={() => setShowBulkImport(true)}>
                Bulk Import
              </button>
            )}
            <button className="btn btn-primary" onClick={() => setShowCreate(true)} id="all-leads-create-btn">
              <Plus size={16} /> New Lead
            </button>
          </div>
        </div>

        {/* Search */}
        <div style={{ marginBottom: 20 }}>
          <div className="search-wrap" style={{ maxWidth: 400 }}>
            <Search size={15} className="search-icon" />
            <input
              className="search-input"
              placeholder="Search by name or profession…"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              id="all-leads-search"
            />
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          {TABS.map((t) => (
            <button 
              key={t} 
              className={`tab ${tab === t ? 'active' : ''}`} 
              onClick={() => { setTab(t); setPage(1); setSelectedLeadIds(new Set()); }} 
              id={`leads-tab-${t.toLowerCase().replace(/\s+/g,'-')}`}
            >
              {t} <span style={{ opacity: 0.6, fontSize: '0.75em', marginLeft: 4 }}>({tabCount(t)})</span>
            </button>
          ))}
        </div>

        {/* Transfer requests tab */}
        {tab === 'Transfers' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {transfers.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">✅</div>
                <div className="empty-state-title">No pending transfer requests</div>
              </div>
            ) : transfers.map((r) => (
              <div key={r.id} className="glass-card" style={{ padding: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 700 }}>{r.lead_name}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
                    <b>{r.from_user_name}</b> → <b>{r.to_user_name}</b>
                  </div>
                  {r.reason && <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>{r.reason}</div>}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary btn-sm" onClick={() => handleTransfer(r.id, 'approved')} id={`approve-transfer-${r.id}`}>Approve</button>
                  <button className="btn btn-danger btn-sm"  onClick={() => handleTransfer(r.id, 'rejected')} id={`reject-transfer-${r.id}`}>Reject</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <>
            {loading ? (
              <div className="loading-center"><div className="spinner" /> Loading leads…</div>
            ) : filtered.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🎯</div>
                <div className="empty-state-title">No leads found</div>
                <p>Try adjusting your search or filters.</p>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Showing {paginated.length} of {filtered.length} leads
                  </div>
                  {isManagerOrAdmin && (
                    <label style={{ fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                      <input 
                        type="checkbox" 
                        className="form-input" 
                        style={{ width: 14, height: 14 }}
                        checked={paginated.length > 0 && paginated.every(l => selectedLeadIds.has(l.id))}
                        onChange={(e) => {
                          const newSet = new Set(selectedLeadIds);
                          if (e.target.checked) {
                            paginated.forEach(l => newSet.add(l.id));
                          } else {
                            paginated.forEach(l => newSet.delete(l.id));
                          }
                          setSelectedLeadIds(newSet);
                        }}
                      /> Select All on Page
                    </label>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {paginated.map((l) => (
                    <LeadCard
                      key={l.id}
                      lead={l}
                      showClaimBtn={tab === 'Unassigned' || tab === 'All Leads'}
                      onClaim={handleClaim}
                      selectable={isManagerOrAdmin}
                      isSelected={selectedLeadIds.has(l.id)}
                      onSelect={(id, checked) => {
                        const newSet = new Set(selectedLeadIds);
                        if (checked) newSet.add(id);
                        else newSet.delete(id);
                        setSelectedLeadIds(newSet);
                      }}
                    />
                  ))}
                </div>
                <Pagination total={filtered.length} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
              </>
            )}
          </>
        )}
      </div>

      {selectedLeadIds.size > 0 && isManagerOrAdmin && (
        <div style={{
          position: 'fixed',
          bottom: 24, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--bg-elevated)', border: '1px solid var(--border)',
          borderRadius: 50, padding: '12px 24px',
          display: 'flex', alignItems: 'center', gap: 20,
          boxShadow: '0 8px 30px rgba(0,0,0,0.12)', zIndex: 100
        }}>
          <span style={{ fontWeight: 600 }}>{selectedLeadIds.size} leads selected</span>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelectedLeadIds(new Set())}>Clear</button>
            {user?.role === 'admin' && (
              <button className="btn btn-danger btn-sm" onClick={handleBulkDelete}>Delete</button>
            )}
            <button className="btn btn-primary btn-sm" onClick={() => setShowBulkAssign(true)}>Bulk Assign</button>
          </div>
        </div>
      )}

      {showCreate && <CreateLeadModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); fetchData(); }} />}
      {showBulkImport && <BulkImportModal onClose={() => setShowBulkImport(false)} onImported={() => { setShowBulkImport(false); fetchData(); }} />}
      {showBulkAssign && (
        <BulkAssignModal 
          onClose={() => setShowBulkAssign(false)} 
          selectedLeads={leads.filter(l => selectedLeadIds.has(l.id))}
          onAssigned={() => { setShowBulkAssign(false); setSelectedLeadIds(new Set()); fetchData(); }} 
        />
      )}
    </>
  );
}
