export default function MetricCard({ label, value, icon: Icon, color, subtitle }) {
  return (
    <div className="metric-card">
      {Icon && (
        <div className="metric-icon">
          <Icon size={40} color={color || 'var(--primary-light)'} />
        </div>
      )}
      <div className="metric-value" style={color ? { background: `linear-gradient(135deg, ${color}, var(--primary-light))`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' } : {}}>
        {value ?? '—'}
      </div>
      <div className="metric-label">{label}</div>
      {subtitle && <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>{subtitle}</div>}
    </div>
  );
}
