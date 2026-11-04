import { useRef, useState } from 'react'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Badge, Empty, ErrorBox, PageHead, Spinner } from '../components/ui'
import { ORIGIN_TONE, titleCase } from '../format'

export default function Reviews() {
  const [flt, setFlt] = useState({ data_origin: '' })
  const [page, setPage] = useState(1)
  const pageSize = 25
  const list = useAsync(() => api.listReviews({ ...flt, limit: pageSize, offset: (page - 1) * pageSize }), [flt, page])
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [result, setResult] = useState(null)
  const input = useRef()

  const upload = async () => {
    if (!file || file.size > 2 * 1024 * 1024) { setErr(new Error('Choose a CSV or JSON file up to 2 MB.')); return }
    setBusy(true); setErr(null); setResult(null)
    try { setResult(await api.importReviews(file)); setFile(null); input.current.value = ''; setPage(1); list.reload() }
    catch (ex) { setErr(ex) } finally { setBusy(false) }
  }
  return (
    <>
      <PageHead title="Review import" sub="Import legally collected charging reviews (CSV or JSON). Text is PII-redacted on ingest." />
      <div className="card">
        <h2>Upload</h2>
        <p className="muted small" style={{ marginTop: -6 }}>CSV needs columns <code>text</code> and <code>data_origin</code> (optional: source, source_ref, review_date, problem_category). Max 2 MB.</p>
        <ErrorBox error={err} />
        <div className="chips">
          <input ref={input} aria-label="Review file" disabled={busy} type="file" accept=".csv,.json" onChange={(e) => setFile(e.target.files[0] || null)} style={{ maxWidth: 360 }} />
          <button className="btn primary" disabled={!file || busy} onClick={upload}>{busy ? 'Importing…' : '📥 Import'}</button>
        </div>
        {result && <div className={`alert ${result.skipped ? 'warn' : 'ok'}`} style={{ marginTop: 14 }}>
          Imported <strong>{result.imported}</strong>, skipped <strong>{result.skipped}</strong>.
          {result.errors?.length > 0 && <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{result.errors.slice(0, 8).map((e, i) => <li key={i}>{e}</li>)}</ul>}
        </div>}
      </div>

      <div className="card"><h2>Stored reviews</h2>
        <div className="row" style={{ marginBottom: 12 }}>
          <label className="field" style={{ margin: 0 }}>Origin<select value={flt.data_origin} onChange={(e) => { setFlt({ ...flt, data_origin: e.target.value }); setPage(1) }}><option value="">Any</option>{['simulated', 'manual_test', 'real_public_review'].map((o) => <option key={o} value={o}>{titleCase(o)}</option>)}</select></label>
        </div>
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading ? <Spinner /> : list.error ? null : !list.data?.length ? <Empty>No reviews match these filters.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>#</th><th>Review (redacted)</th><th>Category</th><th>Origin</th></tr></thead>
            <tbody>{list.data.map((r) => (<tr key={r.review_id}><td className="mono">{r.review_id}</td><td className="clip">{r.redacted_text}</td>
              <td>{r.problem_category ? titleCase(r.problem_category) : '—'}</td><td><Badge tone={ORIGIN_TONE[r.data_origin]}>{titleCase(r.data_origin)}</Badge></td></tr>))}</tbody>
          </table></div>)}
        {!list.error && <div className="pager"><span>Page {page}</span><button className="btn sm" disabled={page === 1 || list.loading} onClick={() => setPage(page - 1)}>Previous reviews</button><button className="btn sm" disabled={list.loading || !list.data || list.data.length < pageSize} onClick={() => setPage(page + 1)}>Next reviews</button></div>}
      </div>
    </>
  )
}
