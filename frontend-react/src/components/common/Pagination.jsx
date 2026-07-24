export default function Pagination({ total, page, pageSize = 15, onPage }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  const pages = [];
  // Show first, last and window around current page
  const window = 2;
  const shown = new Set([1, totalPages]);
  for (let i = Math.max(2, page - window); i <= Math.min(totalPages - 1, page + window); i++) {
    shown.add(i);
  }
  const sorted = [...shown].sort((a, b) => a - b);

  let prev = 0;
  for (const p of sorted) {
    if (p - prev > 1) pages.push('...');
    pages.push(p);
    prev = p;
  }

  return (
    <div className="pagination">
      <button
        className="page-btn"
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        id="pagination-prev-btn"
      >
        ‹
      </button>

      {pages.map((p, i) =>
        p === '...' ? (
          <span key={`dots-${i}`} style={{ color: 'var(--text-muted)', padding: '0 4px' }}>…</span>
        ) : (
          <button
            key={p}
            className={`page-btn ${p === page ? 'active' : ''}`}
            onClick={() => onPage(p)}
            id={`pagination-page-${p}-btn`}
          >
            {p}
          </button>
        )
      )}

      <button
        className="page-btn"
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        id="pagination-next-btn"
      >
        ›
      </button>

      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginLeft: 8 }}>
        {total} total
      </span>
    </div>
  );
}
