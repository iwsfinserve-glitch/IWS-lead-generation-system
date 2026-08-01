import { useState, useEffect, useCallback } from 'react';
import { CheckSquare, Download, Plus, Search, Target, X } from 'lucide-react';
import Navbar from '../components/layout/Navbar';
import LeadCard from '../components/cards/LeadCard';
import Pagination from '../components/common/Pagination';
import CreateLeadModal from '../components/modals/CreateLeadModal';
import BulkImportModal from '../components/modals/BulkImportModal';
import BulkAssignModal from '../components/modals/BulkAssignModal';
import { getLeads, claimLead, getLeadsSummary, bulkDeleteLeads, getSources } from '../api/leadsApi';
import { getLeadTransferRequests, updateLeadTransfer, getUsers } from '../api/usersApi';
import { useAuth } from '../context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';

const TABS_MANAGER = ['All', 'My Clients', 'Unassigned', 'Active', 'Non-Potential', 'Converted', 'Investors', 'Transfers'];
const TABS_REP     = ['All', 'My Clients', 'Unassigned', 'Active', 'Non-Potential', 'Converted'];
const TABS_ADMIN   = ['All', 'Unassigned', 'Active', 'Non-Potential', 'Converted', 'Investors', 'Transfers'];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'unassigned',            label: 'Unassigned' },
  { value: 'in_progress',           label: 'In Progress' },
  { value: 'potential',             label: 'Potential' },
  { value: 'non_potential',         label: 'Non-Potential' },
  { value: 'converted_to_investor', label: 'Converted' },
  { value: 'existing_investor',     label: 'Existing Investor' },
];

export default function AllLeadsPage() {
  const { isManagerOrAdmin, isAdmin, isManager, user } = useAuth();
  const TABS = isAdmin ? TABS_ADMIN : isManager ? TABS_MANAGER : TABS_REP;

  const [searchParams, setSearchParams] = useSearchParams();
  const tab          = searchParams.get('tab') || 'All';
  const search       = searchParams.get('search') || '';
  const filterStatus = searchParams.get('status') || '';
  const filterSource = searchParams.get('source') || '';
  const filterRep    = searchParams.get('rep') || '';
  const pageParam    = parseInt(searchParams.get('page') || '1', 10);
  const page         = isNaN(pageParam) ? 1 : pageParam;

  const updateParams = (newParams) => {
    // Need to use searchParams.entries() but React Router updates are batched/async, 
    // so consecutive updateParams calls in the same render cycle can overwrite each other.
    // Instead of using searchParams.entries(), we can pass a function to setSearchParams!
    setSearchParams(prev => {
      const current = Object.fromEntries(prev.entries());
      Object.keys(newParams).forEach(k => {
        if (newParams[k] === '' || newParams[k] === null || newParams[k] === undefined) {
          delete current[k];
        } else {
          current[k] = newParams[k];
        }
      });
      return current;
    }, { replace: true });
  };
  const setTab = (val) => updateParams({ tab: val, page: 1 });
  const setSearch = (val) => updateParams({ search: val, page: 1 });
  const setFilterStatus = (val) => updateParams({ status: val, page: 1 });
  const setFilterSource = (val) => updateParams({ source: val, page: 1 });
  const setFilterRep = (val) => updateParams({ rep: val, page: 1 });
  const setPage = (val) => updateParams({ page: val });

  const [pageSize, setPageSize]   = useState(15);
  const [leads, setLeads]         = useState([]);
  const [summary, setSummary]     = useState({});
  const [transfers, setTransfers] = useState([]);
  const [sources, setSources]     = useState([]);
  const [reps, setReps]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showBulkImport, setShowBulkImport] = useState(false);
  const [showBulkAssign, setShowBulkAssign] = useState(false);
  const [selectedLeadIds, setSelectedLeadIds] = useState(new Set());
  
  // Local state for search to avoid lag on every keystroke
  const [localSearch, setLocalSearch] = useState(search);
  useEffect(() => { setLocalSearch(search); }, [search]);
  useEffect(() => {
    const handler = setTimeout(() => {
      if (localSearch !== search) {
        setSearch(localSearch);
      }
    }, 400);
    return () => clearTimeout(handler);
  }, [localSearch, search]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [l, s, src, usersRes] = await Promise.all([
        getLeads({ limit: 20000 }),
        getLeadsSummary().catch(() => ({})),
        getSources().catch(() => []),
        getUsers().catch(() => []),
      ]);
      setLeads(l);
      setSummary(s);
      setSources(src);
      setReps(usersRes.filter(u => u.role === 'manager' || u.role === 'sales_rep'));
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
      setTransfers((prev) => prev.filter((t) => t.id !== id));
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

  const resetFilters = () => {
    updateParams({ search: '', status: '', source: '', rep: '', page: 1 });
  };

  const hasActiveFilters = search.trim() || filterStatus || filterSource || filterRep;

  // Filter leads by tab + search + status + source
  const tabLeads = () => {
    let base = leads;
    // Text search: name, profession, email, phone, source name
    if (search.trim()) {
      const t = search.toLowerCase();
      base = base.filter((l) =>
        l.name.toLowerCase().includes(t) ||
        (l.profession || '').toLowerCase().includes(t) ||
        (l.email || '').toLowerCase().includes(t) ||
        (l.phone_number || '').toLowerCase().includes(t) ||
        (l.source_name || '').toLowerCase().includes(t)
      );
    }
    // Status filter
    if (filterStatus) {
      base = base.filter((l) => l.status === filterStatus);
    }
    // Source filter
    if (filterSource) {
      base = base.filter((l) => String(l.source_id) === filterSource);
    }
    // Assigned Rep filter
    if (filterRep) {
      if (filterRep === 'unassigned') {
        base = base.filter((l) => !l.assigned_rep_id);
      } else {
        base = base.filter((l) => String(l.assigned_rep_id) === filterRep);
      }
    }
    let result = [];
    switch (tab) {
      case 'My Clients':
        // Sales reps see their assigned leads AND existing investors
        if (!isManagerOrAdmin) {
          result = base.filter((l) => l.assigned_rep_id === user?.id || l.status === 'existing_investor' && l.assigned_rep_id === user?.id);
        } else {
          result = base.filter((l) => l.assigned_rep_id === user?.id);
        }
        break;
      case 'Unassigned': result = base.filter((l) => l.status === 'unassigned'); break;
      case 'Active':     result = base.filter((l) => ['in_progress', 'potential'].includes(l.status)); break;
      case 'Non-Potential': result = base.filter((l) => l.status === 'non_potential'); break;
      case 'Converted':  result = base.filter((l) => l.status === 'converted_to_investor'); break;
      case 'Investors':  result = base.filter((l) => l.status === 'existing_investor'); break;
      case 'Transfers':  result = []; break;
      default:           result = base; break;
    }
    return result.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  };

  const filtered = tabLeads();
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);

  const tabCount = (t) => {
    switch (t) {
      case 'All':  return summary.total || leads.length;
      case 'My Clients':   return !isManagerOrAdmin
        ? leads.filter((l) => l.assigned_rep_id === user?.id).length
        : leads.filter((l) => l.assigned_rep_id === user?.id).length;
      case 'Unassigned': return summary.unassigned || leads.filter((l) => l.status === 'unassigned').length;
      case 'Active':     return ((summary.in_progress || 0) + (summary.potential || 0)) || leads.filter((l) => ['in_progress', 'potential'].includes(l.status)).length;
      case 'Non-Potential': return summary.non_potential || leads.filter((l) => l.status === 'non_potential').length;
      case 'Converted':  return summary.converted_to_investor || leads.filter((l) => l.status === 'converted_to_investor').length;
      case 'Investors':  return summary.existing_investor || leads.filter((l) => l.status === 'existing_investor').length;
      case 'Transfers':  return transfers.filter((t) => t.status === 'pending').length;
      default: return 0;
    }
  };

  const handleExportMyClients = () => {
    const myClients = leads
      .filter((l) => l.assigned_rep_id === user?.id)
      .sort((a, b) => (a.name || '').localeCompare(b.name || ''));

    if (myClients.length === 0) {
      toast.error('No clients to export.');
      return;
    }

    const STATUS_LABELS = {
      unassigned: 'Unassigned',
      in_progress: 'In Progress',
      potential: 'Potential',
      non_potential: 'Non-Potential',
      converted_to_investor: 'Converted to Investor',
      existing_investor: 'Existing Investor',
    };

    const rows = myClients.map((l) => ({
      'Name':             l.name || '',
      'Email':            l.email || '',
      'Phone':            l.phone_number || '',
      'Profession':       l.profession || '',
      'Address':          l.address || '',
      'Date of Birth':    l.date_of_birth || '',
      'Age':              l.age != null ? l.age : '',
      'Source':           l.source_name || '',
      'Status':           STATUS_LABELS[l.status] || l.status || '',
      'Last Contact Date': l.last_contact_date || '',
      'Assigned Rep':     l.assigned_rep_name || '',
    }));

    const headers = Object.keys(rows[0]);
    const csvContent = [
      headers.join(','),
      ...rows.map(row =>
        headers.map(h => `"${String(row[h]).replace(/"/g, '""')}"`).join(',')
      )
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `my-clients-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${myClients.length} clients to CSV!`);
  };

  return (
    <>
      <Navbar title="All Leads" />
      <div className="page-container">
        {/* Header */}
        <div className="page-header">
          <div>
            <h1 style={{ marginBottom: 4 }}>Lead Directory</h1>
            <p style={{ color: 'var(--text-muted)' }}>Manage and track all your leads in one place.</p>
          </div>
          <div className="page-header-actions">
            {tab === 'My Clients' && (
              <button className="btn btn-ghost" onClick={handleExportMyClients} id="export-my-clients-btn">
                <Download size={16} /> Export CSV
              </button>
            )}
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

        {/* Filter Toolbar */}
        <div className="filter-toolbar">
          {/* Text Search */}
          <div className="search-wrap">
            <Search size={15} className="search-icon" />
            <input
              className="search-input"
              placeholder="Search by name, profession, source…"
              value={localSearch}
              onChange={(e) => setLocalSearch(e.target.value)}
              id="all-leads-search"
            />
          </div>

          {/* Status Filter */}
          <select
            className="form-select filter-select"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            id="all-leads-filter-status"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Source Filter */}
          <select
            className="form-select filter-select"
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            id="all-leads-filter-source"
          >
            <option value="">All Sources</option>
            {sources.map((s) => (
              <option key={s.id} value={String(s.id)}>{s.name}</option>
            ))}
          </select>

          {/* Assigned Rep Filter */}
          {isManagerOrAdmin && (
            <select
              className="form-select filter-select"
              value={filterRep}
              onChange={(e) => setFilterRep(e.target.value)}
              id="all-leads-filter-rep"
            >
              <option value="">All Reps</option>
              <option value="unassigned">Unassigned</option>
              {reps.map((r) => (
                <option key={r.id} value={String(r.id)}>{r.name}</option>
              ))}
            </select>
          )}

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={resetFilters}
              id="all-leads-clear-filters"
              style={{ whiteSpace: 'nowrap' }}
            >
              <X size={14} /> Clear
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="tabs">
          {TABS.map((t) => (
            <button 
              key={t} 
              className={`tab ${tab === t ? 'active' : ''}`} 
              onClick={() => setTab(t)}
              id={`all-leads-tab-${t.toLowerCase().replace(' ', '-')}`}
            >
              {t} <span style={{ opacity: 0.6, fontSize: '0.75em', marginLeft: 4 }}>({tabCount(t)})</span>
            </button>
          ))}
        </div>

        {/* Transfer requests tab */}
        {tab === 'Transfers' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {transfers.filter((r) => r.status === 'pending').length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon"><CheckSquare size={48} /></div>
                <div className="empty-state-title">No pending transfer requests</div>
              </div>
            ) : transfers.filter((r) => r.status === 'pending').map((r) => (
              <div key={r.id} className="glass-card transfer-card">
                <div>
                  <div style={{ fontWeight: 700 }}>{r.lead_name}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
                    <b>{r.from_user_name}</b> → <b>{r.to_user_name}</b>
                  </div>
                  {r.reason && <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>{r.reason}</div>}
                </div>
                <div className="transfer-actions">
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
                <div className="empty-state-icon"><Target size={48} /></div>
                <div className="empty-state-title">No leads found</div>
                <p>Try adjusting your search or filters.</p>
              </div>
            ) : (
              <>
                <div className="results-bar">
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span>Showing {paginated.length} of {filtered.length} leads
                    {hasActiveFilters && <span style={{ marginLeft: 6, color: 'var(--primary)', fontWeight: 600 }}>· Filtered</span>}</span>
                    <select 
                      className="form-select" 
                      style={{ padding: '4px 24px 4px 8px', fontSize: '0.75rem', width: 'auto', minHeight: 0 }}
                      value={pageSize}
                      onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                    >
                      <option value="15">15 per page</option>
                      <option value="30">30 per page</option>
                      <option value="50">50 per page</option>
                      <option value="100">100 per page</option>
                    </select>
                  </div>
                  {isManagerOrAdmin && (
                    <label className="select-all-label">
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
                      showClaimBtn={tab === 'Unassigned' || tab === 'All'}
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
                <Pagination total={filtered.length} page={page} pageSize={pageSize} onPage={setPage} />
              </>
            )}
          </>
        )}
      </div>

      {selectedLeadIds.size > 0 && isManagerOrAdmin && (
        <div className="bulk-action-bar">
          <span style={{ fontWeight: 600 }}>{selectedLeadIds.size} leads selected</span>
          <div className="bulk-action-buttons">
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
