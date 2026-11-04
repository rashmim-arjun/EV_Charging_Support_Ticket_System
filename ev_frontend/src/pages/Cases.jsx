import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Badge, Empty, ErrorBox, PageHead, Pager, Spinner } from '../components/ui'
import { CLASS_TONE, ORIGIN_TONE, STATUS_TONE, fmtDate, titleCase } from '../format'

const PAGE = 15

export default function Cases() {
  const nav = useNavigate()
  const [flt, setFlt] = useState({ app_id: '', category: '', status: '', data_origin: '',ticket_state:'',priority:'' })
  const [page, setPage] = useState(1)
  const meta = useAsync(() => Promise.all([api.apps(), api.categories()]), [])
  const list = useAsync(() => api.listCases({ ...flt, page, page_size: PAGE }), [flt, page])
  const set = (k) => (e) => { setFlt({ ...flt, [k]: e.target.value }); setPage(1) }
  const [apps, cats] = meta.data || [[], []]

  return (
    <>
      <PageHead title="Cases" sub="Support tickets: complaint, investigation, priority, ownership and resolution">
        <Link to="/new" className="btn primary">➕ New complaint</Link>
      </PageHead>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          <label className="field">Ticket state<select value={flt.ticket_state} onChange={set('ticket_state')}><option value="">All ticket states</option>{['new','investigating','awaiting_evidence','assigned','escalated','resolved','closed'].map(s => <option key={s} value={s}>{titleCase(s)}</option>)}</select></label>
          <label className="field">Priority<select value={flt.priority} onChange={set('priority')}><option value="">All priorities</option>{['P0','P1','P2','P3'].map(s => <option key={s}>{s}</option>)}</select></label>
          <label className="field" style={{ margin: 0 }}>App
            <select value={flt.app_id} onChange={set('app_id')}><option value="">All apps</option>
              {apps.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select></label>
          <label className="field" style={{ margin: 0 }}>Category
            <select value={flt.category} onChange={set('category')}><option value="">All categories</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
          <label className="field" style={{ margin: 0 }}>Status
            <select value={flt.status} onChange={set('status')}><option value="">Any status</option>
              {['open', 'diagnosed', 'awaiting_review', 'resolved'].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select></label>
          <label className="field" style={{ margin: 0 }}>Data origin
            <select value={flt.data_origin} onChange={set('data_origin')}><option value="">Any origin</option>
              {['simulated', 'manual_test', 'real_public_review'].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select></label>
        </div>
      </div>

      <ErrorBox error={meta.error} onRetry={meta.reload} />
      <ErrorBox error={list.error} onRetry={list.reload} />
      {list.loading ? <Spinner /> : list.error ? null : !list.data?.items.length ? <div className="card"><Empty>No cases match these filters.</Empty></div> : (
        <>
          <div className="table-wrap"><table>
            <thead><tr><th>Ticket / case</th><th>Priority / owner</th><th>App</th><th>Complaint</th><th>Primary category</th><th>Result</th><th>Status</th><th>Origin</th><th>Created</th></tr></thead>
            <tbody>{list.data.items.map((c) => (
              <tr key={c.case_id} className="click" onClick={() => nav(`/cases/${c.case_id}`)}>
                <td className="mono"><Link to={`/cases/${c.case_id}`}>{c.case_id}</Link></td>
                <td>{c.ticket?.priority || 'Pending'}<div>{titleCase(c.ticket?.assigned_team || 'triage')}</div><div>{titleCase(c.ticket?.state || 'new')}</div></td>
                <td>{c.app_display_name || c.app_id}</td>
                <td className="clip">{c.complaint_text_redacted}</td>
                <td>{c.diagnosis?.primary_category ? titleCase(c.diagnosis.primary_category) : <span className="muted">—</span>}</td>
                <td>{c.diagnosis ? <Badge tone={CLASS_TONE[c.diagnosis.classification]}>{titleCase(c.diagnosis.classification)}</Badge> : <span className="muted">not run</span>}</td>
                <td><Badge tone={STATUS_TONE[c.status]}>{titleCase(c.status)}</Badge></td>
                <td><Badge tone={ORIGIN_TONE[c.data_origin]}>{titleCase(c.data_origin)}</Badge></td>
                <td className="small muted">{fmtDate(c.created_at)}</td>
              </tr>))}
            </tbody>
          </table></div>
          <Pager page={list.data.page} pageSize={PAGE} total={list.data.total} onChange={setPage} />
        </>
      )}
    </>
  )
}
