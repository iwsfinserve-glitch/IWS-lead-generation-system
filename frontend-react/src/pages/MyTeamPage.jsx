import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/layout/Navbar';
import MetricCard from '../components/common/MetricCard';
import { RoleBadge } from '../components/common/StatusBadge';
import { getUsers } from '../api/usersApi';
import { getLeads, getLeadsSummary } from '../api/leadsApi';
import { CheckSquare, ChevronRight, Target, TrendingUp, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

export default function MyTeamPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [teamMembers, setTeamMembers] = useState([]);
  const [repLeadCounts, setRepLeadCounts]   = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getUsers()
      .then(async (allUsers) => {
        const direct = allUsers.filter((u) => u.manager_id === user.id);
        setTeamMembers(direct);

        const counts = {};
        await Promise.all(
          direct.map(async (rep) => {
            try {
              const leads = await getLeads({ assigned_rep_id: rep.id, limit: 1000 });
              counts[rep.id] = {
                total: leads.length,
                active: leads.filter((l) => ['in_progress', 'potential'].includes(l.status)).length,
                converted: leads.filter((l) => l.status === 'converted_to_investor').length,
              };
            } catch {
              counts[rep.id] = { total: 0, active: 0, converted: 0 };
            }
          })
        );
        setRepLeadCounts(counts);
      })
      .catch(() => toast.error('Failed to load team'))
      .finally(() => setLoading(false));
  }, [user.id]);

  const totalLeads     = Object.values(repLeadCounts).reduce((s, c) => s + c.total, 0);
  const totalActive    = Object.values(repLeadCounts).reduce((s, c) => s + c.active, 0);
  const totalConverted = Object.values(repLeadCounts).reduce((s, c) => s + c.converted, 0);

  if (loading) return <div className="loading-center"><div className="spinner" /> Loading...</div>;

  return (
    <>
      <Navbar title="My Team" />
      <div className="page-container">
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ marginBottom: 4 }}>My Sales Team</h1>
          <p style={{ color: 'var(--text-muted)' }}>
            Overview of your {teamMembers.length} direct report{teamMembers.length !== 1 ? 's' : ''} and their lead pipeline.
          </p>
        </div>

        <div className="metrics-grid">
          <MetricCard label="Team Members" value={teamMembers.length}  icon={Users}       />
          <MetricCard label="Total Leads"  value={totalLeads}          icon={Target}      color="var(--accent)" />
          <MetricCard label="Active"       value={totalActive}         icon={TrendingUp}  color="var(--warning)" />
          <MetricCard label="Converted"    value={totalConverted}      icon={CheckSquare} color="var(--success)" />
        </div>


        {teamMembers.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon"><Users size={48} /></div>
            <div className="empty-state-title">No direct reports yet</div>
            <div className="empty-state-desc">Sales reps assigned to you will appear here.</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
            {teamMembers.map((member) => {
              const counts = repLeadCounts[member.id] || { total: 0, active: 0, converted: 0 };
              return (
                <div
                  key={member.id}
                  className="glass-card"
                  style={{ padding: 20, cursor: 'pointer', transition: 'transform 0.15s' }}
                  onClick={() => navigate(`/users/${member.id}`)}
                  id={`team-member-card-${member.id}`}
                  onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-2px)'}
                  onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                    <div style={{
                      width: 46, height: 46, borderRadius: '50%',
                      background: 'linear-gradient(135deg, var(--primary), var(--accent))',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontWeight: 700, color: '#fff', fontSize: '1rem', flexShrink: 0,
                    }}>
                      {member.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: 3 }}>{member.name}</div>
                      <RoleBadge role={member.role} />
                    </div>
                    <ChevronRight size={16} color="var(--text-muted)" />
                  </div>

                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 14 }}>
                    {member.username}
                    {member.phone_number && <span style={{ marginLeft: 8 }}>· {member.phone_number}</span>}
                  </div>

                  <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
                    gap: 8, borderTop: '1px solid var(--border)', paddingTop: 12,
                  }}>
                    {[
                      { label: 'Total Leads', value: counts.total,     color: 'var(--text-primary)' },
                      { label: 'Active',       value: counts.active,    color: 'var(--warning)' },
                      { label: 'Converted',    value: counts.converted, color: 'var(--success)' },
                    ].map(({ label, value, color }) => (
                      <div key={label} style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '1.25rem', fontWeight: 700, color }}>{value}</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}