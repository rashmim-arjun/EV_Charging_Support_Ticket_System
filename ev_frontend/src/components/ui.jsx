import { titleCase } from '../format'

export function Badge({ tone = 'gray', children }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function Spinner() { return <div className="spinner" role="status" aria-label="Loading" /> }

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="alert error" role="alert">
      <strong>{error.code ? titleCase(error.code) : 'Error'}:</strong> {error.message}
      {onRetry && <> <button className="btn sm" style={{ marginLeft: 10 }} onClick={onRetry}>Retry</button></>}
    </div>
  )
}

export function Stat({ label, value, sub }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export function Empty({ children }) { return <div className="empty">{children}</div> }

export function PageHead({ title, sub, children }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{sub && <div className="muted">{sub}</div>}</div>
      <div>{children}</div>
    </div>
  )
}

export function BeliefBars({ beliefs, categories }) {
  const label = (id) => categories?.find((c) => c.id === id)?.label || titleCase(id)
  const rows = Object.entries(beliefs || {}).sort((a, b) => b[1] - a[1])
  if (!rows.length) return <div className="muted">No belief scores recorded.</div>
  const max = Math.max(...rows.map((r) => r[1]), 0.0001)
  return rows.map(([id, v]) => (
    <div className="belief" key={id}>
      <span>{label(id)}</span>
      <div className="bar"><i style={{ width: `${(v / max) * 100}%` }} /></div>
      <span className="mono">{v.toFixed(2)}</span>
    </div>
  ))
}

export function Pager({ page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="pager">
      <span className="muted small">{total} result{total === 1 ? '' : 's'} · page {page} of {pages}</span>
      <button className="btn sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>← Prev</button>
      <button className="btn sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next →</button>
    </div>
  )
}

export const SimulatedBanner = () => (
  <div className="banner">
    ⚠ Demo charging logs are simulated. Review and complaint provenance is labelled by <code>data_origin</code>.
    Results do not describe any real charging network or company.
  </div>
)
