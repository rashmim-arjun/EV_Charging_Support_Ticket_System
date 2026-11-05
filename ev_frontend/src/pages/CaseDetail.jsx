import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Badge, BeliefBars, Empty, ErrorBox, PageHead, SimulatedBanner, Spinner } from '../components/ui'
import { EVIDENCE_TONE, ORIGIN_TONE, STATUS_TONE, diagnosisTitle, diagnosisTone, fmtDate, titleCase } from '../format'
import TicketPanel from '../components/TicketPanel'
import PaymentPanel from '../components/PaymentPanel'

const load = (id) => () => Promise.all([api.getCase(id), api.getTrace(id), api.categories(), api.reviewers()])

export default function CaseDetail() {
  const { caseId } = useParams()
  const { data, error, loading, reload } = useAsync(load(caseId), [caseId])
  const [tab, setTab] = useState('diagnosis')
  if (loading && !data) return <Spinner />
  if (error) return <><ErrorBox error={error} onRetry={reload} /><Link to="/cases">← Back to support tickets</Link></>
  const [full, trace, cats, reviewers] = data
  const { case: c, complaint } = full
  const catLabel = (id) => cats.find((x) => x.id === id)?.label || titleCase(id)
  const TABS = [['diagnosis', 'Diagnosis'], ['evidence', 'Evidence'], ['trace', `Agent trace (${trace.steps.length})`], ['review', 'Verify & learn']]

  return (
    <>
      <PageHead title={<span className="mono" style={{ fontSize: 20 }}>{c.case_id}</span>} sub={`${c.app_display_name || c.app_id} · ${fmtDate(c.created_at)}`}>
        <span className="chips">
          <Badge tone={STATUS_TONE[c.status]}>{titleCase(c.status)}</Badge>
          <Badge tone={ORIGIN_TONE[c.data_origin]}>{titleCase(c.data_origin)}</Badge>
        </span>
      </PageHead>
      <SimulatedBanner />
      <InvestigationSummary full={full} cats={cats} onEvidence={() => setTab('evidence')} />
      {full.ticket && <TicketPanel key={caseId} ticket={full.ticket} sessionId={complaint.reported_session_ref}
        onChange={reload} onResolve={() => setTab('review')} />}
      {full.ticket && <PaymentPanel key={'payment-'+caseId} caseId={caseId} reviewers={reviewers} onChange={reload} />}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Complaint (PII redacted)</h3>
        <p style={{ margin: '0 0 10px' }}>{c.complaint_text_redacted}</p>
        <div className="chips small muted">
          {complaint.complaint_ts && <span>🕒 {fmtDate(complaint.complaint_ts)}</span>}
          {complaint.reported_error && <span>⚠ Error: {complaint.reported_error}</span>}
          {complaint.reported_payment_status && <span>Customer-reported payment: {titleCase(complaint.reported_payment_status)} (unverified claim)</span>}
          {complaint.reported_session_ref && <span>Session: {complaint.reported_session_ref}</span>}
          {complaint.reported_station_id && <span>Station: {complaint.reported_station_id}</span>}
        </div>
      </div>

      <div className="tabs">
        {TABS.map(([k, l]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {tab === 'diagnosis' && <DiagnosisTab full={full} trace={trace} cats={cats} catLabel={catLabel} />}
      {tab === 'evidence' && <EvidenceTab full={full} />}
      {tab === 'trace' && <TraceTab trace={trace} cats={cats} />}
      {tab === 'review' && <ReviewTab key={caseId} full={full} cats={cats} reviewers={reviewers} catLabel={catLabel} onChange={reload} />}
    </>
  )
}

function InvestigationSummary({ full, cats, onEvidence }) {
  const diagnosis = full.diagnosis
  const ticket = full.ticket
  const healthy = diagnosis?.outcome === 'no_fault_established'
  const evidence = (full.evidence?.matching || []).find(item => item.supports_category === diagnosis?.primary_category)
  const reason = diagnosis?.explanation || evidence?.description || diagnosis?.unresolved_questions?.[0]
    || (diagnosis ? 'Available records do not establish a single fault.' : 'Ticket saved. Run an investigation to compare the available session logs.')
  const action = full.recommendations?.[0]?.action || (healthy
    ? 'No corrective work is indicated. Retain the session record and receipt, and review any new symptoms.'
    : diagnosis ? 'Review the missing or conflicting evidence before choosing a corrective action.' : 'Choose Investigate ticket below to check the available records.')
  return <section className="card investigation-summary" aria-label="Investigation summary">
    <div className="section-head"><h2>Investigation summary</h2><Badge tone={diagnosisTone(diagnosis)}>{healthy ? 'No fault established' : diagnosis ? titleCase(diagnosis.classification) : 'Pending'}</Badge></div>
    <p className="summary-title">{diagnosisTitle(diagnosis, cats)}</p>
    {ticket?.priority === 'P0' && <div className="alert warn">Immediate human safety review is required. The reported hazard is precautionary until verified.</div>}
    <div className="grid g3">
      <div><h3>Reason and evidence</h3><p>{reason}</p><button type="button" className="btn sm" onClick={onEvidence}>View supporting evidence</button></div>
      <div><h3>Recommended next action</h3><p>{action}</p></div>
      <div><h3>Responsible team</h3><p>{titleCase(ticket?.assigned_team || 'Support triage')}</p><div className="chips"><Badge tone={ticket?.priority === 'P0' ? 'red' : ticket?.priority === 'P1' ? 'amber' : 'blue'}>{ticket?.priority || 'Pending'}</Badge><Badge>{titleCase(ticket?.state || 'new')}</Badge></div></div>
    </div>
  </section>
}

function DiagnosisTab({ full, trace, cats, catLabel }) {
  const d = full.diagnosis
  if (!d) return <div className="card"><Empty>No diagnosis has been produced for this case.</Empty></div>
  return (
    <div className="grid g-main">
      <div>
        <div className="card">
          <div className="chips" style={{ marginBottom: 10 }}>
            <Badge tone={diagnosisTone(d)}>{d.outcome === 'no_fault_established' ? 'No fault established' : titleCase(d.classification)}</Badge>
            <Badge tone="gray">Strength: {d.evidence_strength_label}</Badge>
          </div>
          <h2 style={{ fontSize: 20 }}>{diagnosisTitle(d, cats)}</h2>
          <div className="muted small" style={{ marginBottom: 6 }}>Evidence score {(d.evidence_strength * 100).toFixed(0)}%</div>
          {d.confidence != null && <div className="muted small">Synthetic calibrated confidence {(d.confidence * 100).toFixed(0)}% (assertions only)</div>}
          {!d.primary_category && d.leading_hypothesis && <p className="muted small">Unverified leading hypothesis: {catLabel(d.leading_hypothesis)}</p>}
          <div className="bar"><i style={{ width: `${Math.min(100, d.evidence_strength * 100)}%` }} /></div>
          {d.contributing_categories.length > 0 && <>
            <h3 style={{ marginTop: 16 }}>Contributing categories</h3>
            <div className="chips">{d.contributing_categories.map((x) => <Badge key={x} tone="blue">{catLabel(x)}</Badge>)}</div>
          </>}
          <div className="muted small" style={{ marginTop: 14 }}>Stop reason: <strong>{titleCase(d.stop_reason)}</strong> · diagnosis v{d.version}</div>
        </div>

        {d.unresolved_questions.length > 0 && (
          <div className="card"><h2>Unresolved questions</h2>
            <ul style={{ margin: 0, paddingLeft: 20 }}>{d.unresolved_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
          </div>)}

        <div className="card"><h2>Recommended actions</h2>
          {full.recommendations.length === 0 ? <Empty>{d.outcome === 'no_fault_established' ? 'No corrective work is indicated by these observations. Retain the session record and receipt; review any new symptoms before closing the enquiry.' : 'No recommendations.'}</Empty> : full.recommendations.map((r) => (
            <div className="rec" key={r.id}>
              <div className="prio" title="Priority">{r.priority}</div>
              <div><strong>{r.action}</strong><div className="muted small">{r.rationale}</div></div>
            </div>))}
        </div>
      </div>
      <details className="card" style={{ alignSelf: 'start' }}>
        <summary>Agent belief scores</summary>
        <BeliefBars beliefs={trace.final_beliefs} categories={cats} />
      </details>
    </div>
  )
}

function EvidenceTab({ full }) {
  const groups = [['matching', 'Matching evidence', 'Supports the diagnosis'], ['conflicting', 'Conflicting evidence', 'Contradicts a hypothesis'],
    ['missing', 'Missing information', 'Needed to be more certain'], ['neutral', 'Neutral observations', '']]
  const total = groups.reduce((n, [k]) => n + (full.evidence[k]?.length || 0), 0)
  if (!total) return <div className="card"><Empty>No evidence was collected.</Empty></div>
  return (
    <div className="grid g2">
      {groups.map(([k, title, sub]) => (
        <div className="card" key={k} style={{ marginTop: 0 }}>
          <h2>{title} <Badge tone={EVIDENCE_TONE[k]}>{full.evidence[k]?.length || 0}</Badge></h2>
          {sub && <div className="muted small" style={{ marginTop: -8, marginBottom: 10 }}>{sub}</div>}
          {!full.evidence[k]?.length ? <div className="muted">None</div> : full.evidence[k].map((e) => (
            <div className={`ev ${k}`} key={e.id}>
              <div>{e.description}</div>
              <div className="small muted">
                #{e.id} · {e.tool_name && <>tool: {e.tool_name} · </>}weight {e.weight.toFixed(2)}
                {e.supports_category && <> · {titleCase(e.supports_category)}</>}
                {e.source_table && <> · source: {e.source_table}{e.source_ref ? ` (${e.source_ref})` : ''}</>}
              </div>
            </div>))}
        </div>))}
    </div>
  )
}

function TraceTab({ trace, cats }) {
  if (!trace.steps.length) return <div className="card"><Empty>No agent steps were recorded.</Empty></div>
  return (
    <div className="card">
      <h2>Agent reasoning trace</h2>
      <p className="muted small" style={{ marginTop: -6 }}>Each step shows why the agent chose a tool (information gain + learned prior − cost), what it found, and how its beliefs changed.</p>
      <div className="timeline">
        {trace.steps.map((s) => {
          const scores = (s.candidate_scores || []).slice(0, 6).map((x) => ({ tool: x.tool, score: x.score }))
          const after = s.state_changes?.beliefs_after
          return (
            <div className={`step ${s.replanned ? 'replan' : ''}`} data-n={s.step_no} key={s.step_no}>
              <div><span className="tool">{titleCase(s.tool_name)}</span> {s.replanned && <Badge tone="amber">Re-planned</Badge>}
                <span className="small muted"> · {fmtDate(s.created_at)}</span></div>
              <div className="muted small">{s.selection_reason}</div>
              <div style={{ marginTop: 6 }}><strong>Outcome:</strong> {s.outcome_summary}</div>
              <details><summary>Tool selection scores</summary>
                <ResponsiveContainer width="100%" height={Math.max(120, scores.length * 28)}>
                  <BarChart data={scores} layout="vertical" margin={{ left: 40 }}>
                    <XAxis type="number" /><YAxis type="category" dataKey="tool" width={150} tick={{ fontSize: 11 }} />
                    <Tooltip /><Bar dataKey="score" fill="#2e6cf6" radius={[0, 5, 5, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </details>
              {after && <details><summary>Beliefs after this step</summary><BeliefBars beliefs={after} categories={cats} /></details>}
              <details><summary>Raw tool result</summary><pre>{JSON.stringify(s.result, null, 2)}</pre></details>
            </div>)
        })}
      </div>
      <div className="muted small">Stopped because: <strong>{titleCase(trace.stop_reason)}</strong></div>
    </div>
  )
}

function ReviewTab({ full, cats, reviewers, catLabel, onChange }) {
  const res = full.resolution
  const caseId = full.case.case_id
  const [form, setForm] = useState({ reviewer_id: '', verified_root_cause: full.diagnosis?.primary_category || '',
    verified_contributing: [], corrective_action: '', resolution_notes: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [preview, setPreview] = useState(null)
  const [msg, setMsg] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const toggle = (id) => setForm({ ...form, verified_contributing: form.verified_contributing.includes(id)
    ? form.verified_contributing.filter((x) => x !== id) : [...form.verified_contributing, id] })

  const run = async (fn, after) => {
    setBusy(true); setErr(null); setMsg(null)
    try { const r = await fn(); after?.(r) } catch (ex) { setErr(ex) } finally { setBusy(false) }
  }
  const submit = (e) => { e.preventDefault()
    const body = { ...form }; if (!body.resolution_notes) delete body.resolution_notes
    run(() => api.submitResolution(caseId, body), () => { setMsg('Resolution recorded.'); onChange() }) }

  if (!res) return (
    <form className="card" onSubmit={submit}>
      <h2>Reviewer verification</h2>
      <p className="muted small" style={{ marginTop: -6 }}>Record the verified root cause. This outcome is the ground truth the agent learns from.</p>
      <ErrorBox error={err} />{msg && <div className="alert ok">{msg}</div>}
      <div className="row">
        <label className="field">Reviewer *
          <select required value={form.reviewer_id} onChange={set('reviewer_id')}><option value="">Select…</option>
            {reviewers.map((r) => <option key={r.reviewer_id} value={r.reviewer_id} disabled={!r.active}>{r.name} ({titleCase(r.role)}){r.active ? '' : ' — inactive'}</option>)}</select></label>
        <label className="field">Verified root cause *
          <select required value={form.verified_root_cause} onChange={set('verified_root_cause')}><option value="">Select…</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}<option value="no_fault_established">No fault established after review</option><option value="inconclusive">Inconclusive after human review</option></select></label>
      </div>
      <div className="field">Contributing causes<span className="hint">optional</span>
        <div className="chips" style={{ marginTop: 8 }}>
          {cats.filter((c) => c.id !== form.verified_root_cause).map((c) => (
            <label key={c.id} style={{ fontWeight: 500, display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="checkbox" style={{ width: 'auto', margin: 0 }} checked={form.verified_contributing.includes(c.id)} onChange={() => toggle(c.id)} />{c.label}
            </label>))}
        </div>
      </div>
      <label className="field">Corrective action *<textarea required minLength={3} maxLength={2000} value={form.corrective_action} onChange={set('corrective_action')} style={{ minHeight: 80 }} /></label>
      <label className="field">Notes<span className="hint">optional</span><textarea maxLength={4000} value={form.resolution_notes} onChange={set('resolution_notes')} style={{ minHeight: 70 }} /></label>
      <button className="btn primary" disabled={busy}>{busy ? 'Saving…' : '✔ Submit verified resolution'}</button>
    </form>
  )

  const contributing = JSON.parse(res.verified_contributing_json || '[]')
  return (
    <>
      <div className="card">
        <h2>Verified resolution</h2>
        <div className="grid g3" style={{ marginBottom: 12 }}>
          <div><div className="muted small">Verified root cause</div><strong>{catLabel(res.verified_root_cause)}</strong></div>
          <div><div className="muted small">Agent predicted</div><strong>{res.agent_prediction_category ? catLabel(res.agent_prediction_category) : '—'}</strong></div>
          <div><div className="muted small">Prediction</div>{res.verified_root_cause === 'no_fault_established' || res.verified_root_cause === 'inconclusive' ? <Badge tone={res.verified_root_cause === 'no_fault_established' ? 'green' : 'amber'}>{res.verified_root_cause === 'no_fault_established' ? 'No fault established' : 'Inconclusive after review'}</Badge> : res.prediction_correct ? <Badge tone="green">Correct</Badge> : <Badge tone="red">Incorrect</Badge>}</div>
        </div>
        {contributing.length > 0 && <div className="chips" style={{ marginBottom: 10 }}>{contributing.map((x) => <Badge key={x} tone="blue">{catLabel(x)}</Badge>)}</div>}
        <div><strong>Corrective action:</strong> {res.corrective_action}</div>
        {res.resolution_notes && <div className="muted" style={{ marginTop: 6 }}>{res.resolution_notes}</div>}
        <div className="muted small" style={{ marginTop: 8 }}>Reviewer {res.reviewer_id} · {fmtDate(res.resolved_at)}</div>
      </div>

      <div className="card">
        <h2>Continuous learning</h2>
        <p className="muted small" style={{ marginTop: -6 }}>Preview how this verified outcome would adjust rule weights and tool priors, then apply. Every change is logged and reversible on the Knowledge page.</p>
        <ErrorBox error={err} />{msg && <div className="alert ok">{msg}</div>}
        {res.learning_applied ? <div className="alert ok">Learning from this case has already been applied.</div> : (
          <div className="chips">
            <button className="btn" disabled={busy} onClick={() => run(() => api.previewLearning(caseId), setPreview)}>👁 Preview changes</button>
            <button className="btn primary" disabled={busy} onClick={() => run(() => api.applyLearning(caseId), () => { setMsg('Learning applied.'); setPreview(null); onChange() })}>🧠 Apply learning</button>
          </div>)}
        {preview && (preview.changes.length === 0 ? <div className="alert info" style={{ marginTop: 12 }}>No changes would be made.</div> : (
          <div className="table-wrap" style={{ marginTop: 14 }}><table>
            <thead><tr><th>Change</th><th>Target</th><th>Old</th><th>New</th><th>Reason</th></tr></thead>
            <tbody>{preview.changes.map((ch, i) => (
              <tr key={i}><td><Badge tone="blue">{titleCase(ch.change_type)}</Badge></td>
                <td className="small">{ch.tool_name || ch.signal_key || '—'}<div className="muted">{ch.category && titleCase(ch.category)}</div></td>
                <td className="mono">{ch.old_value ?? '—'}</td><td className="mono">{ch.new_value ?? '—'}</td><td className="small">{ch.reason}</td></tr>))}
            </tbody></table></div>))}
      </div>
    </>
  )
}
