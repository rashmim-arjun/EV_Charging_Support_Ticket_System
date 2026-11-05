import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Empty, ErrorBox, PageHead, Pager, Spinner } from '../components/ui'
import { titleCase } from '../format'
import TicketList from '../components/TicketList'

const PAGE = 15

export default function Cases() {
  const [flt, setFlt] = useState({ category: '', status: '', data_origin: '',ticket_state:'',priority:'' })
  const [page, setPage] = useState(1)
  const meta = useAsync(() => api.categories(), [])
  const list = useAsync(() => api.listCases({ ...flt, page, page_size: PAGE }), [flt, page])
  const set = (k) => (e) => { setFlt({ ...flt, [k]: e.target.value }); setPage(1) }
  const cats = meta.data || []

  return (
    <>
      <PageHead title="Support tickets" sub="Track complaints, investigations, priorities, ownership and resolutions">
        <Link to="/new" className="btn primary">➕ New complaint</Link>
      </PageHead>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          <label className="field">Ticket state<select value={flt.ticket_state} onChange={set('ticket_state')}><option value="">All ticket states</option>{['new','investigating','awaiting_evidence','assigned','escalated','resolved','closed'].map(s => <option key={s} value={s}>{titleCase(s)}</option>)}</select></label>
          <label className="field">Priority<select value={flt.priority} onChange={set('priority')}><option value="">All priorities</option>{['P0','P1','P2','P3'].map(s => <option key={s}>{s}</option>)}</select></label>
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
      {list.loading ? <Spinner /> : list.error ? null : !list.data?.items.length ? <div className="card"><Empty>No tickets match these filters.</Empty></div> : (
        <>
          <TicketList items={list.data.items} categories={cats} />
          <Pager page={list.data.page} pageSize={PAGE} total={list.data.total} onChange={setPage} />
        </>
      )}
    </>
  )
}
