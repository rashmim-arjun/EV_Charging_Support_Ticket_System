import { Link } from 'react-router-dom'
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from 'recharts'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Empty, ErrorBox, PageHead, SimulatedBanner, Spinner, Stat } from '../components/ui'
import { pct, titleCase } from '../format'
import TicketList from '../components/TicketList'

const COLORS = ['#12b76a', '#2e6cf6', '#f79009', '#7a5af8', '#e5484d', '#06aed4', '#667085']

async function load() {
  const [recent, open, review, resolved, perf, rec, cats, queue] = await Promise.all([
    api.listCases({ page_size: 6 }),
    api.listCases({ page_size: 1, status: 'open' }),
    api.listCases({ page_size: 1, status: 'awaiting_review' }),
    api.listCases({ page_size: 1, status: 'resolved' }),
    api.performance({ data_origin: 'simulated' }),
    api.recurring(),
    api.categories(),
    api.ticketSummary(),
  ])
  return { recent, open, review, resolved, perf, rec, cats, queue }
}

export default function Dashboard() {
  const { data, error, loading, reload } = useAsync(load, [])
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  const { recent, open, review, resolved, perf, rec, cats, queue } = data

  const label = (id) => cats.find((c) => c.id === id)?.label || titleCase(id)
  const byCat = {}
  rec.by_app_category.forEach((r) => { byCat[r.category] = (byCat[r.category] || 0) + r.count })
  const catData = Object.entries(byCat).map(([id, n]) => ({ name: label(id), n })).sort((a, b) => b.n - a.n)
  const originData = Object.entries(rec.data_origin_counts).map(([k, v]) => ({ name: titleCase(k), value: v }))

  return (
    <>
      <PageHead title="Dashboard" sub="Customer support tickets, evidence-based investigation and auditable internal escalation" />
      <SimulatedBanner />
      <div className="card"><h2>Customer support workflow</h2><p>Create a complaint, inspect its diagnosis and supporting logs, then track the response in Support tickets. Record a verified resolution before closing the ticket.</p>
        <div className="row"><Link className="btn primary" to="/new">Open support ticket</Link><Link className="btn" to="/cases">Manage support tickets</Link><Link className="btn" to="/communication">Supporting communication logs</Link></div></div>

      <div className="card" style={{ marginTop: 16 }} aria-label="Ticket queue">
        <h2>Ticket queue</h2>
        <div className="grid g4">
          <Stat label="Open escalated" value={queue.open_escalated} sub="local escalation records" />
          <Stat label="Awaiting evidence" value={queue.open_awaiting_evidence} sub="more logs or human review needed" />
          <Stat label="In triage queue" value={queue.open_in_triage} sub="no unique supported owner" />
          <Stat label="Human overrides" value={queue.human_overrides} sub="tickets with audited overrides" />
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          Open by priority: {['P0','P1','P2','P3'].map(p => `${p} ${queue.open_by_priority?.[p] || 0}`).join(' · ')}.
          {' '}{queue.delivery_scope}</p>
      </div>

      <div className="grid g4">
        <Stat label="Total tickets" value={recent.total} sub={`${open.total} awaiting first investigation`} />
        <Stat label="Awaiting review" value={review.total} sub="needs a verified outcome" />
        <Stat label="Resolved / closed" value={resolved.total} sub="includes labelled simulated reviews" />
        <Stat label="Demo evaluation accuracy" value={pct(perf.primary_accuracy_pct)}
          sub={perf.total_resolved_cases ? `${perf.total_resolved_cases} reviewed simulated tickets; no real-world accuracy claim` : 'No reviewed simulated tickets yet'} />
      </div>
      {perf.small_sample_warning && perf.total_resolved_cases > 0 &&
        <div className="alert warn" style={{ marginTop: 16 }}>{perf.sample_size_note}</div>}

      <div className="grid g-main" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Failure categories (diagnosed complaints)</h2>
          {catData.length === 0 ? <Empty>No diagnosed cases yet. Submit a complaint to get started.</Empty> : (
            <ResponsiveContainer width="100%" height={Math.max(220, catData.length * 34)}>
              <BarChart data={catData} layout="vertical" margin={{ left: 30 }}>
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={230} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="n" name="Cases" fill="#12b76a" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="card">
          <h2>Data origin</h2>
          {originData.length === 0 ? <Empty>No data.</Empty> : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={originData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                  {originData.map((_, i) => <Cell key={i} fill={COLORS[(i + 3) % COLORS.length]} />)}
                </Pie>
                <Tooltip /><Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="section-head"><h2>Recent support tickets</h2><Link className="btn sm" to="/cases">View all tickets</Link></div>
        <p className="muted small">Showing the latest {recent.items.length} of {recent.total} tickets. Open Support tickets to browse the complete queue.</p>
        {recent.items.length === 0 ? <Empty>No tickets yet.</Empty> : <TicketList items={recent.items} categories={cats} />}
      </div>
    </>
  )
}
