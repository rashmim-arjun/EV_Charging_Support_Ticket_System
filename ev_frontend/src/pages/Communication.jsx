import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Badge, Empty, ErrorBox, PageHead, Pager, Spinner } from '../components/ui'
import { titleCase } from '../format'

const COMPONENTS = ['app', 'csms', 'charger', 'connector', 'vehicle', 'bms', 'payment', 'network']
const componentName = type => ['bms', 'csms'].includes(type) ? type.toUpperCase() : titleCase(type)
const OPERATIONS = ['Authorize', 'RequestStartTransaction', 'ChargeParameterDiscoveryReq', 'SetChargingProfile', 'StatusNotification', 'MeterValues', 'PaymentCapture', 'TransactionEvent.Ended']
const tone = status => ['faulted', 'error', 'dropped', 'lost', 'failed', 'conflicting'].includes(status) ? 'red' : ['degraded', 'delayed', 'duplicated', 'timeout', 'inconclusive'].includes(status) ? 'amber' : status === 'unknown' ? 'gray' : 'green'

export default function Communication() {
  const [query] = useSearchParams()
  const meta = useAsync(() => api.communicationTemplates(), [])
  const [runId, setRunId] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState(query.get('session') || '')
  const [tab, setTab] = useState('timeline')
  const [filter, setFilter] = useState('')
  const [component, setComponent] = useState('')
  const [highlight, setHighlight] = useState('')
  const [form, setForm] = useState({ seed: 42, per_template: 1, scenario: '', injection: '', operation: 'RequestStartTransaction', delay_ms: 7000 })
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)
  const [message, setMessage] = useState('')
  const [report, setReport] = useState(null)
  const sessions = useAsync(() => api.communicationSessions({ run_id: runId, page, page_size: 20 }), [runId, page])
  const detail = useAsync(() => selected ? api.communicationSession(selected) : Promise.resolve(null), [selected])
  useEffect(() => {
    if (sessions.data?.items.length && !selected) setSelected(sessions.data.items[0].session_id)
  }, [sessions.data, selected])
  useEffect(() => { setFilter(''); setComponent(''); setHighlight(''); setTab('timeline') }, [selected])
  useEffect(() => {
    if (tab === 'timeline' && highlight) document.getElementById('event-' + highlight)?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [tab, highlight])
  const change = key => e => setForm({ ...form, [key]: e.target.value })
  const valid = form.seed !== '' && Number.isInteger(Number(form.seed)) && Number(form.seed) >= 0 && Number(form.seed) <= 2147483647 && Number.isInteger(Number(form.per_template)) && Number(form.per_template) >= 1 && Number(form.per_template) <= 20
  const act = async (name, fn) => {
    setBusy(name); setError(null); setMessage('')
    try { await fn() } catch (e) { setError(e) } finally { setBusy('') }
  }
  const generate = e => {
    e.preventDefault()
    act('generate', async () => {
      const result = await api.generateCommunication({ seed: Number(form.seed), per_template: Number(form.per_template), split: 'test',
        scenarios: form.scenario ? [form.scenario] : null,
        injections: form.injection ? [{ kind: form.injection, operation: form.operation, delay_ms: Number(form.delay_ms) }] : [] })
      if (result.run_id === runId) sessions.reload()
      setRunId(result.run_id); setPage(1); setSelected(result.session_ids[0] || ''); setTab('timeline')
      setMessage(`${result.inserted} sessions added; ${result.total} sessions in this run.${result.warnings.length ? ` ${result.warnings.length} sessions did not reach a requested injection point.` : ''}`)
    })
  }
  const showEvent = id => { setFilter(''); setComponent(''); setHighlight(id); setTab('timeline') }
  const showComponent = type => { setFilter(''); setComponent(type); setHighlight(''); setTab('timeline') }
  const current = detail.data?.session.session_id === selected ? detail.data : null
  const componentEvents = Object.fromEntries(COMPONENTS.map(type => [type, current?.events.filter(e => e.component_type === type) || []]))
  const missingComponents = COMPONENTS.filter(type => !componentEvents[type].length)
  const filteredEvents = current?.events.filter(e => (!component || e.component_type === component) && (!filter || JSON.stringify(e).toLowerCase().includes(filter.toLowerCase()))) || []

  return <>
    <PageHead title="Communication monitoring" sub="Coordinated synthetic EV charging sessions across eight component actors" />
    <div className="alert info">Simulation only. Health reflects the selected historical session. Messages are OCPP / ISO 15118 inspired; protocol compliance is not implemented.</div>
    <form className="card" onSubmit={generate}>
      <h2>Generate a coordinated dataset</h2>
      <ErrorBox error={meta.error} onRetry={meta.reload} />
      <div className="row">
        <label className="field">Simulation seed<input type="number" min="0" max="2147483647" required value={form.seed} onChange={change('seed')} /></label>
        <label className="field">Sessions per scenario<input type="number" min="1" max="20" required value={form.per_template} onChange={change('per_template')} /></label>
        <label className="field">Scenario<select value={form.scenario} onChange={change('scenario')} disabled={!!busy || meta.loading}><option value="">All normal and fault scenarios</option>{meta.data?.scenarios.map(s => <option key={s} value={s}>{s === 'none' ? 'Successful charging' : titleCase(s)}</option>)}</select></label>
      </div>
      <details><summary>Optional additional fault injection</summary><p className="muted small">Use a successful scenario to inspect a single injected fault. Combining mechanisms can require further investigation. Injections apply only if their operation is reached.</p>
        <div className="row"><label className="field">Injection type<select value={form.injection} onChange={e => setForm({ ...form, injection: e.target.value, operation: e.target.value === 'stale' ? 'StatusNotification' : form.operation })}><option value="">Scenario default only</option>{['drop', 'delay', 'duplicate', 'stale', 'timeout', 'retry'].map(x => <option key={x}>{x}</option>)}</select></label>
          <label className="field">Message operation<select value={form.operation} onChange={change('operation')}>{OPERATIONS.map(x => <option key={x}>{x}</option>)}</select></label>
          <label className="field">Injected delay (ms)<input type="number" min="1" max="120000" value={form.delay_ms} onChange={change('delay_ms')} /></label></div>
      </details>
      <button className="btn primary" disabled={!!busy || !valid || meta.loading || !!meta.error}>{busy === 'generate' ? 'Generating sessions…' : 'Generate sessions'}</button>
    </form>
    <ErrorBox error={error} />{message && <div className="alert ok" role="status">{message}</div>}
    <div className="card" style={{ marginTop: 16 }}>
      <h2>Select a charging session</h2>
      <ErrorBox error={sessions.error} onRetry={sessions.reload} />
      {sessions.loading ? <Spinner /> : sessions.error ? null : !sessions.data?.items.length ? <Empty>No simulated communication sessions yet. Generate a dataset to inspect its events.</Empty> : <>
        <label className="field">Charging session<select value={selected} disabled={!!busy} onChange={e => setSelected(e.target.value)}>{sessions.data.items.map(s => <option key={s.session_id} value={s.session_id}>{s.session_id} · {titleCase(s.status)} · {s.event_count} events</option>)}</select></label>
        <Pager page={page} pageSize={20} total={sessions.data.total} onChange={setPage} />
      </>}
      {runId && <button className="btn sm" onClick={() => { setRunId(''); setPage(1) }}>Show all runs</button>}
    </div>
    <ErrorBox error={detail.error} onRetry={detail.reload} />
    {selected && detail.loading && !current ? <Spinner /> : current && <>
      <div className="card"><div className="page-head"><div><h2 className="mono">{selected}</h2><div className="muted small">Trace: {current.session.trace_id} · {current.events.length} observed events</div></div>
        <button className="btn primary" disabled={!!busy} onClick={() => act('diagnose', async () => { await api.diagnoseCommunication(selected); setTab('diagnosis'); detail.reload() })}>{busy === 'diagnose' ? 'Correlating evidence…' : 'Diagnose session'}</button></div>
        {missingComponents.length > 0 && <div className="alert warn">No logs were captured for: {missingComponents.map(componentName).join(', ')}. Their activity cannot be verified for this session. Other sessions may have these records.</div>}
        <div className="grid g4">{COMPONENTS.map(type => {
          const health = current.components.find(c => c.component_type === type)
          const records = componentEvents[type]
          const latest = records[records.length - 1]
          return <div className="comm-health" key={type} role="group" aria-label={`${componentName(type)} component logs`}>
            <strong>{componentName(type)}</strong>
            <div><Badge tone={tone(health?.health || 'unknown')}>{health?.health || 'unknown'}</Badge></div>
            <div className="small muted">Connection: {health?.connection || 'unknown'}</div>
            <div className="mono small">{current.session.components[type]}</div>
            <div className="small">{records.length} recorded {records.length === 1 ? 'event' : 'events'}</div>
            {latest ? <div className="small muted">Last recorded (UTC): <time className="mono small" dateTime={latest.timestamp}>{latest.timestamp}</time></div>
              : <div className="small muted">No records captured for this component.</div>}
            {records.length > 0 && records.every(e => e.event_type === 'component.health') && <div className="small muted">Only a health check is recorded; no activity logs were captured.</div>}
            <div><button className="btn sm" onClick={() => showComponent(type)}>View {componentName(type)} logs ({records.length})</button></div>
          </div>
        })}</div><p className="muted small">{current.scope}</p>
      </div>
      <p><Link className="btn primary" to={`/new?session=${encodeURIComponent(selected)}&app=${encodeURIComponent(current.session.app_id)}`}>Open support ticket for this session</Link></p>
      <div className="tabs">{[['timeline', `Session logs (${current.events.length})`], ['flow', `Message flow (${current.flows.length})`], ['anomalies', `Communication failures & conflicts (${current.anomalies.length})`], ['diagnosis', 'Root-cause diagnosis']].map(([key, text]) => <button key={key} className={`tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>{text}</button>)}</div>
      {tab === 'timeline' && <div className="card"><h2>Chronological session logs</h2>
        <div className="row"><label className="field">Component filter<select value={component} onChange={e => setComponent(e.target.value)}><option value="">All components</option>{COMPONENTS.map(c => <option key={c} value={c}>{componentName(c)}</option>)}</select></label><label className="field">Search events<input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Event, message or correlation ID" /></label></div>
        <p className="muted small">Timestamps are UTC and retain milliseconds. Shared trace, correlation and message IDs connect each request to transport and receiver observations.</p>
        {!filteredEvents.length ? <Empty>
          <p>{component && !componentEvents[component].length
            ? `No ${componentName(component)} records were captured for this session. This component's activity cannot be verified from the available logs.`
            : filter || component ? 'No events match these filters.' : 'No event records were captured for this session.'}</p>
          {(filter || component) && <button className="btn sm" onClick={() => showComponent('')}>Show all session logs</button>}
        </Empty> : <div className="table-wrap comm-log"><table><thead><tr><th>UTC timestamp</th><th>Component</th><th>Event</th><th>Severity / status</th><th>Correlation / payload</th></tr></thead><tbody>{filteredEvents.map(e => <tr key={e.event_id} id={'event-' + e.event_id} className={highlight === e.event_id ? 'comm-highlight' : ''}>
          <td className="mono">{e.timestamp}</td><td>{titleCase(e.component_type)}<div className="muted mono">{e.component_id}</div></td><td>{e.event_type}<div className="muted small">{e.message}</div><div className="mono">{e.event_id}</div></td><td><Badge tone={tone(e.severity)}>{e.severity}</Badge><div>{e.status}</div></td>
          <td><details><summary className="mono">{e.correlation_id}</summary><div className="mono">Message: {e.message_id || 'local event'}</div><pre>{JSON.stringify(e.payload, null, 2)}</pre></details></td></tr>)}</tbody></table></div>}
      </div>}
      {tab === 'flow' && <div className="card"><h2>Cross-component message flow</h2><p className="muted small">Each arrow is a sent message, including responses. Red indicates dropped delivery or conflicting observations; amber indicates delays or duplication. Select an arrow to inspect its correlation.</p><MessageFlow flows={current.flows} onSelect={id => { setTab('timeline'); setFilter(id); setComponent('') }} /></div>}
      {tab === 'anomalies' && <div className="card"><h2>Detected communication failures and conflicts</h2>{!current.anomalies.length ? <Empty>No communication anomalies detected in the available observations.</Empty> : current.anomalies.map((a, i) => <div className="ev conflicting" key={i}><Badge tone={tone(a.severity)}>{titleCase(a.code)}</Badge> <strong>{a.component_type ? titleCase(a.component_type) : 'Component unresolved'}</strong><p>{a.description}</p><div className="chips">{a.event_ids.map(id => <button className="btn sm mono" key={id} onClick={() => showEvent(id)}>{id}</button>)}</div></div>)}</div>}
      {tab === 'diagnosis' && <div className="card"><h2>Root-cause diagnosis</h2>{!current.diagnosis ? <Empty>Run diagnosis to correlate this session and inspect its supporting evidence.</Empty> : <>
        <Badge tone={tone(current.diagnosis.classification)}>{titleCase(current.diagnosis.classification)}</Badge><h3 style={{ marginTop: 12 }}>{current.diagnosis.root_cause === 'none' ? 'Successful charging: no fault established' : current.diagnosis.root_cause ? titleCase(current.diagnosis.root_cause) : 'Inconclusive: insufficient or conflicting evidence'}</h3>
        <p>Localized component: <strong>{current.diagnosis.component_type ? titleCase(current.diagnosis.component_type) : 'No fault localized'}</strong> · {current.diagnosis.diagnostic_checks} diagnostic checks</p>
        <p>Evidence score: {current.diagnosis.evidence_strength.toFixed(3)}{current.diagnosis.confidence != null && <> · Synthetic calibrated confidence: {(current.diagnosis.confidence * 100).toFixed(1)}%</>}</p><p className="muted small">{current.diagnosis.confidence_scope}</p>
        {current.diagnosis.unresolved_questions.map(q => <div className="alert warn" key={q}>{q}</div>)}
        {current.diagnosis.evidence.map((e, i) => <div className={`ev ${e.kind === 'conflicting' ? 'conflicting' : 'matching'}`} key={i}><p>{e.description}</p><div className="chips">{e.event_ids.map(id => <button className="btn sm mono" key={id} onClick={() => showEvent(id)}>{id}</button>)}</div></div>)}
        {current.diagnosis.case_id && <Link className="btn primary" to={`/cases/${current.diagnosis.case_id}`}>Open case for reviewer feedback & learning</Link>}
      </>}</div>}
    </>}
    <div className="card" style={{ marginTop: 20 }}><h2>Three-agent communication evaluation</h2><p className="muted small">Uses independent train, validation and test scenario/configuration groups in a scratch database. Compares the existing fixed baseline, current adaptive agent and extended agent.</p>
      <button className="btn" disabled={!!busy || !valid} onClick={() => act('evaluation', async () => setReport(await api.runCommunicationEvaluation({ seed: Number(form.seed), per_template: Math.min(15, Number(form.per_template)) }))) }>{busy === 'evaluation' ? 'Evaluating held-out sessions…' : 'Run communication evaluation'}</button>
      {report && <><p>{report.dataset_size} sessions · train {report.split_sizes.train} / validation {report.split_sizes.validation} / test {report.split_sizes.test}</p><div className="table-wrap"><table><thead><tr><th>Method</th><th>Root accuracy %</th><th>Category accuracy %</th><th>Macro F1</th><th>Checks</th><th>Communication detection %</th><th>Localization %</th><th>ECE</th></tr></thead><tbody>{Object.entries(report.metrics).map(([name, m]) => <tr key={name}><td>{titleCase(name)}</td><td>{m.root_cause_accuracy_pct}</td><td>{m.category_accuracy_pct}</td><td>{m.macro_f1}</td><td>{m.avg_checks_per_session}</td><td>{m.communication_failure_detection_pct}</td><td>{m.component_localization_accuracy_pct}</td><td>{m.calibration.ece}</td></tr>)}</tbody></table></div><details><summary>Evaluation limitations</summary><ul>{report.limitations.map(l => <li key={l}>{l}</li>)}</ul></details></>}
    </div>
  </>
}

export function MessageFlow({ flows, onSelect }) {
  if (!flows.length) return <Empty>No cross-component messages were observed.</Empty>
  const x = type => 75 + COMPONENTS.indexOf(type) * 125
  return <div className="comm-flow" aria-label="Cross-component message diagram"><svg width="1050" height={60 + flows.length * 34} role="img" aria-label="Chronological messages between component columns">
    <defs><marker id="comm-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="context-stroke" /></marker></defs>
    {COMPONENTS.map(c => <g key={c}><text x={x(c)} y="18" textAnchor="middle" fontWeight="bold">{titleCase(c)}</text><line x1={x(c)} x2={x(c)} y1="28" y2={60 + flows.length * 34} stroke="#e3e8ef" /></g>)}
    {flows.map((f, i) => { const y = 55 + i * 34; const color = ['dropped', 'conflicting'].includes(f.status) ? '#b42318' : ['delayed', 'duplicated', 'missing'].includes(f.status) ? '#b54708' : '#1849a9'; return <g key={f.flow_id || f.message_id} role="button" tabIndex="0" aria-label={`Inspect ${f.operation} from ${f.source} to ${f.target}`} onClick={() => onSelect(f.correlation_id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onSelect(f.correlation_id) }} style={{ cursor: 'pointer' }}>
      <title>{f.operation}: {f.source} → {f.target}; {f.status}; {f.latency_ms ?? '?'} ms; {f.correlation_id}</title><line x1={x(f.source)} x2={x(f.target)} y1={y} y2={y} stroke={color} strokeWidth="2" strokeDasharray={f.status === 'dropped' ? '5,4' : undefined} markerEnd="url(#comm-arrow)" /><text x={(x(f.source) + x(f.target)) / 2} y={y - 5} textAnchor="middle" fontSize="10" fill={color}>{f.operation}</text>
    </g> })}
  </svg></div>
}
