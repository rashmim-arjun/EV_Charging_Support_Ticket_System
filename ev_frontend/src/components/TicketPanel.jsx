import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Badge, ErrorBox, Spinner } from './ui'
import { fmtDate, titleCase } from '../format'

export default function TicketPanel({ ticket, sessionId, onChange, onResolve }) {
  const config = useAsync(() => api.ticketPolicy(), [])
  const [form,setForm] = useState({ state:ticket.state,assigned_team:ticket.assigned_team,priority:ticket.priority,
    supporting_teams:ticket.supporting_teams,actor:'support-operator',reason:'' })
  useEffect(() => {
    setForm(previous => ({ ...previous, state:ticket.state, assigned_team:ticket.assigned_team,
      priority:ticket.priority, supporting_teams:ticket.supporting_teams, reason:'' }))
  }, [ticket.version])
  const [error,setError] = useState(null)
  const [busy,setBusy] = useState(false)
  const change = key => e => setForm({ ...form,[key]:e.target.value })
  const act = async fn => { setBusy(true);setError(null);try { await fn();onChange() } catch(e) {setError(e)} finally {setBusy(false)} }
  if (config.loading) return <Spinner />
  if (config.error) return <ErrorBox error={config.error} onRetry={config.reload} />
  const d = ticket.decision || {}
  return <div className="card ticket-controls" role="region" aria-label="Ticket controls"><h2>Support ticket management</h2>
    <p className="mono">Ticket ID: {ticket.ticket_id}</p>
    <p className="small muted">Last updated: {fmtDate(ticket.updated_at)}{ticket.resolved_at ? ` · Resolved: ${fmtDate(ticket.resolved_at)}` : ''}</p>
    <div className="chips"><Badge tone={ticket.priority==='P0'?'red':ticket.priority==='P1'?'amber':'blue'}>{ticket.priority}</Badge>
      <Badge tone="blue">{titleCase(ticket.state)}</Badge><strong>Owner: {config.data.teams[ticket.assigned_team]}</strong></div>
    {d.investigation_notice && <div className="alert warn">{d.investigation_notice}</div>}
    <p className="muted small">Assignments and escalations are saved locally. No email, notification or external ticket is sent.</p>
    <div className="row" style={{marginBottom:12}}>
      {sessionId && <Link className="btn" to={`/communication?session=${encodeURIComponent(sessionId)}`}>Inspect correlated session logs</Link>}
      <button className="btn" disabled={busy || ['resolved','closed'].includes(ticket.state)} onClick={() => act(() => api.investigateTicket(ticket.case_id))}>{d.diagnosis_version?'Investigate again':'Investigate ticket'}</button>
      <button className="btn" onClick={onResolve}>Record verified resolution</button>
    </div>
    <details className="ticket-details"><summary>Assignment evidence and technical details</summary>
    <p>Supporting teams: {ticket.supporting_teams.map(t => config.data.teams[t]).join(', ') || 'None assigned'}</p>
    <p>Classification: {titleCase(d.verified_classification || d.classification || 'Pending investigation')} · Origin: {titleCase(d.originating_component || 'Unresolved')}</p>
    {d.reasons?.map((r,i) => <div className="small" key={i}>{r}</div>)}
    <div className="card inner" style={{marginTop:12}} aria-label="Diagnosis evidence summary">
      <h3>Evidence behind this assignment</h3>
      <p className="small">Affected components: {d.affected_components?.length ? d.affected_components.map(titleCase).join(', ') : 'None observed'}
        {d.requires_human_review ? ' · Human review required' : ''}{d.policy_version ? ` · Policy ${d.policy_version}` : ''}</p>
      {d.evidence?.length ? <div className="table-wrap"><table><thead><tr><th>Event ID</th><th>Component</th><th>Timestamp</th></tr></thead><tbody>
        {d.evidence.map(e => <tr key={e.event_id}><td className="mono">{e.event_id}</td><td>{titleCase(e.component_type)}</td><td>{fmtDate(e.timestamp)}</td></tr>)}
      </tbody></table></div> : <p className="small muted">No supporting log events are cited, so no specific component is asserted.</p>}
      {d.downstream_symptoms?.length > 0 && <p className="small"><strong>Possible downstream symptoms (not automatically root causes):</strong> {d.downstream_symptoms.map(titleCase).join(', ')}</p>}
      {d.contradictory_evidence?.length > 0 && <><h3>Contradictory evidence</h3><ul className="small">{d.contradictory_evidence.map((m,i) => <li key={i}>{m}</li>)}</ul></>}
      {d.missing_evidence?.length > 0 && <><h3>Missing evidence requested</h3><ul className="small">{d.missing_evidence.map((m,i) => <li key={i}>{m}</li>)}</ul></>}
    </div>
    </details>
    <ErrorBox error={error} />
    <details className="ticket-details"><summary>Update assignment or ticket state</summary>
    <form onSubmit={e => { e.preventDefault();act(() => api.updateTicket(ticket.case_id,{...form,version:ticket.version})) }}>
      <div className="row">
        <label className="field">Ticket state<select value={form.state} onChange={change('state')}>
          {[ticket.state,...(config.data.transitions[ticket.state] || [])].map(s => <option key={s} value={s}>{titleCase(s)}</option>)}</select></label>
        <label className="field">Assigned team<select value={form.assigned_team} onChange={change('assigned_team')}>
          {Object.entries(config.data.teams).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label className="field">Ticket priority<select value={form.priority} onChange={change('priority')}>
          {Object.entries(config.data.priorities).map(([id,name]) => <option key={id} value={id}>{id}: {name}</option>)}</select></label>
      </div>
      <label className="field">Supporting teams<select multiple value={form.supporting_teams} onChange={e => setForm({...form,supporting_teams:Array.from(e.target.selectedOptions,o => o.value)})}>
        {Object.entries(config.data.teams).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></label>
      <div className="row"><label className="field">Operator identity<input required maxLength={100} value={form.actor} onChange={change('actor')} /></label>
        <label className="field">Assignment / escalation reason<input required minLength={5} maxLength={2000} value={form.reason} onChange={change('reason')} placeholder="Explain the human decision" /></label></div>
      <button className="btn primary" disabled={busy}>{busy?'Saving…':'Save ticket decision'}</button>
    </form>
    </details>
    <details style={{marginTop:16}}><summary>Investigation and escalation history ({ticket.history.length})</summary>
      <div className="table-wrap"><table><thead><tr><th>Time</th><th>Action / actor</th><th>Reason / decision</th></tr></thead><tbody>
        {ticket.history.map(h => <tr key={h.id}><td>{fmtDate(h.created_at)}</td><td>{titleCase(h.action)}<div>{h.actor}</div></td><td>{h.reason}<details><summary>Audited values</summary><pre>{JSON.stringify({before:h.before,after:h.after},null,2)}</pre></details></td></tr>)}
      </tbody></table></div></details>
  </div>
}
