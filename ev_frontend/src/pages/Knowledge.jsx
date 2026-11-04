import { useState } from 'react'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Badge, Empty, ErrorBox, PageHead, Spinner } from '../components/ui'
import { fmtDate, titleCase } from '../format'

export default function Knowledge() {
  const [tab, setTab] = useState('rules')
  const rules = useAsync(() => api.rules(), [])
  const priors = useAsync(() => api.priors(), [])
  const changes = useAsync(() => api.changes(), [])
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  const act = async (fn, ok) => {
    setBusy(true); setErr(null); setMsg(null)
    try { await fn(); setMsg(ok); changes.reload(); rules.reload(); priors.reload() }
    catch (ex) { setErr(ex) } finally { setBusy(false) }
  }
  const rollback = (id) => {
    const reason = window.prompt(`Roll back every learning change made AFTER change #${id}?\nEnter a reason:`, 'manual rollback')
    if (reason) act(() => api.rollback(id, reason), `Rolled back to change #${id}.`)
  }

  const TABS = [['rules', `Rules (${rules.data?.length ?? '…'})`], ['priors', `Tool priors (${priors.data?.length ?? '…'})`], ['changes', `Change log (${changes.data?.length ?? '…'})`]]
  return (
    <>
      <PageHead title="Knowledge & learning" sub="The agent's rule weights, learned tool priors, and an auditable log of every learning change" />
      <ErrorBox error={err || priors.error || changes.error} />{msg && <div className="alert ok">{msg}</div>}
      <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</button>)}</div>

      {tab === 'rules' && (rules.loading ? <Spinner /> : <><ErrorBox error={rules.error} />
        <div className="table-wrap"><table>
          <thead><tr><th>#</th><th>Category</th><th>Signal</th><th>Weight</th><th>Source</th><th>Status</th><th>v</th></tr></thead>
          <tbody>{rules.data?.map((r) => (
            <tr key={r.rule_id}><td className="mono">{r.rule_id}</td><td>{titleCase(r.category)}</td><td className="mono">{r.signal_key}</td>
              <td style={{ minWidth: 150 }}><div className="chips" style={{ flexWrap: 'nowrap' }}><div className="bar" style={{ flex: 1 }}><i style={{ width: `${r.weight * 100}%` }} /></div><span className="mono">{r.weight.toFixed(2)}</span></div></td>
              <td><Badge tone={r.source === 'seed' ? 'gray' : 'purple'}>{titleCase(r.source)}</Badge></td>
              <td>{r.active ? <Badge tone="green">Active</Badge> : <Badge tone="amber">Inactive</Badge>} <button className="btn sm" disabled={busy} onClick={() => act(() => api.activateRule(r.rule_id, !r.active), `Rule #${r.rule_id} updated.`)}>{r.active ? 'Deactivate' : 'Activate'}</button></td><td>{r.version}</td></tr>))}
          </tbody></table></div></>)}

      {tab === 'priors' && (priors.loading ? <Spinner /> : !priors.data?.length ?
        <div className="card"><Empty>No tool priors yet. They are learned from verified case outcomes.</Empty></div> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Tool</th><th>Category</th><th>Usefulness</th><th>Observations</th><th>Updated</th></tr></thead>
          <tbody>{priors.data.map((p, i) => (
            <tr key={i}><td>{titleCase(p.tool_name)}</td><td>{titleCase(p.category)}</td>
              <td style={{ minWidth: 150 }}><div className="chips" style={{ flexWrap: 'nowrap' }}><div className="bar" style={{ flex: 1 }}><i style={{ width: `${p.usefulness_score * 100}%` }} /></div><span className="mono">{p.usefulness_score.toFixed(2)}</span></div></td>
              <td>{p.n_observations}</td><td className="small muted">{fmtDate(p.updated_at)}</td></tr>))}
          </tbody></table></div>))}

      {tab === 'changes' && (changes.loading ? <Spinner /> : !changes.data?.length ?
        <div className="card"><Empty>No learning changes yet. Verify a case and apply learning to see entries here.</Empty></div> : (
        <div className="table-wrap"><table>
          <thead><tr><th>#</th><th>When</th><th>Type</th><th>Target</th><th>Old → New</th><th>Reason</th><th></th></tr></thead>
          <tbody>{changes.data.map((c) => (
            <tr key={c.change_id} style={c.reverted ? { opacity: .55 } : null}>
              <td className="mono">{c.change_id}</td><td className="small muted">{fmtDate(c.created_at)}</td>
              <td><Badge tone="blue">{titleCase(c.change_type)}</Badge></td>
              <td className="small">{c.tool_name ? titleCase(c.tool_name) : c.rule_id ? `Rule #${c.rule_id}` : '—'}<div className="muted">{c.category && titleCase(c.category)}</div></td>
              <td className="mono small">{c.old_value_json ?? '—'} → {c.new_value_json ?? '—'}</td>
              <td className="small">{c.reason}</td>
              <td style={{ whiteSpace: 'nowrap' }}>{c.reverted || c.change_type === 'rollback' ? <Badge tone="gray">{c.reverted ? 'Reverted' : 'Audit entry'}</Badge> : <>
                <button className="btn sm" disabled={busy} onClick={() => act(() => api.revertChange(c.change_id), `Change #${c.change_id} reverted.`)}>Revert</button>{' '}
                <button className="btn sm danger" disabled={busy} onClick={() => rollback(c.change_id)}>Roll back to here</button></>}</td></tr>))}
          </tbody></table></div>))}
    </>
  )
}
