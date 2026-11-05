import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { ErrorBox, PageHead } from '../components/ui'

const STARTERS = [
  { label: 'Charging will not start', text: 'I connected my vehicle and tried to start charging, but the session did not begin. Please check what prevented it from starting.' },
  { label: 'Charging stopped early', text: 'My vehicle started charging, but the session stopped unexpectedly before I was finished. Please check why the charging was interrupted.' },
  { label: 'Payment or refund issue', text: 'I need help checking a payment or refund related to my charging visit. Please review the transaction and let me know the next steps.' },
  { label: 'Station status is wrong', text: 'The station status shown did not match what I found when I arrived to charge. Please check the station availability and update the information.' },
]
const SAMPLES = [
  { label: 'Session never started (matches seeded logs)', app_id: 'tata_power_ez_charge',
    session_ref: 'SSN-042-0001', station_id: 'STN-102', reported_error: 'E101', data_origin: 'simulated',
    complaint_text: 'I started a charge from the app at the station but it never started and showed a timeout error. Please check.' },
  { label: 'Vague complaint (agent asks for more info)', app_id: 'statiq', reported_payment_status: 'deducted',
    complaint_text: 'Money was deducted from my account but the charging session never started at the station. The app showed a timeout error.' },
]
function localNow() {
  const now = new Date()
  const pad = value => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`
}
const emptyForm = () => ({ app_id: '', complaint_text: '', complaint_ts: localNow(), reported_error: '',
  reported_payment_status: '', session_ref: '', station_id: '', user_ref: '', data_origin: 'manual_test' })

export default function NewCase() {
  const nav = useNavigate()
  const [query] = useSearchParams()
  const [f, setF] = useState(() => ({ ...emptyForm(), session_ref: query.get('session') || '',
    app_id: query.get('app') || '', data_origin: query.get('session') ? 'simulated' : 'manual_test' }))
  const [lookup, setLookup] = useState(f.session_ref)
  const context = useAsync(() => api.intakeContext({ session_ref: lookup || undefined }), [lookup])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = key => event => {
    const value = event.target.value
    setF(current => ({ ...current, [key]: value }))
  }
  useEffect(() => {
    const timer = setTimeout(() => setLookup(f.session_ref.trim()), 300)
    return () => clearTimeout(timer)
  }, [f.session_ref])
  useEffect(() => {
    const session = context.data?.session
    if (!session) return
    setF(current => current.session_ref.trim() === session.session_id && !current.station_id
      ? { ...current, station_id: session.station_id } : current)
  }, [context.data])

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setErr(null)
    try {
      const body = { ...f, session_ref: f.session_ref.trim(), station_id: f.station_id.trim() }
      Object.keys(body).forEach(key => { if (body[key] === '') delete body[key] })
      if (body.complaint_ts) body.complaint_ts = new Date(body.complaint_ts).toISOString()
      const res = event.nativeEvent.submitter?.value === 'save' ? await api.openTicket(body) : await api.submitCase(body)
      nav(`/cases/${res.case.case.case_id}`)
    } catch (error) { setErr(error); setBusy(false) }
  }
  const matched = context.data?.session?.session_id === f.session_ref.trim()
  return (
    <>
      <PageHead title="New complaint" sub="Tell us what happened. We will check the available records and recommend the next steps." />
      <div className="grid g-main">
        <form className="card" onSubmit={submit}>
          <ErrorBox error={err} />
          {err?.details?.ticket_id && <Link className="btn" to={`/cases/${err.details.ticket_id}`}>Open the saved ticket for investigation</Link>}
          {err?.code === 'validation_error' && err.details?.map((detail, index) =>
            <div className="alert warn" key={index}>{detail.loc?.slice(-1)[0]}: {detail.msg}</div>)}
          <label className="field" htmlFor="complaint" style={{ marginBottom: 0 }}>Complaint *</label>
          <textarea id="complaint" required minLength={10} maxLength={500} value={f.complaint_text}
            onChange={set('complaint_text')} aria-describedby="complaint-help complaint-count"
            placeholder="What went wrong? A sentence or two is enough. You can also choose a starter on this page." />
          <div className="row small muted" style={{ margin: '5px 0 16px' }}>
            <span id="complaint-help">10–500 characters. Personal details are redacted automatically.</span>
            <span id="complaint-count" className="auto" aria-live="polite">{f.complaint_text.length}/500</span>
          </div>
          <label className="field">When did it happen?<span className="hint">defaults to now · change for an earlier visit</span>
            <input type="datetime-local" value={f.complaint_ts} onChange={set('complaint_ts')} />
          </label>
          <div className="row">
            <label className="field">Session reference<span className="hint">optional · fills the station if found</span>
              <input value={f.session_ref} onChange={event => {
                const value = event.target.value
                setF(current => ({ ...current, session_ref: value, station_id: '', app_id: '' }))
              }} maxLength={100} placeholder="From your charging receipt" />
            </label>
            <label className="field">Station ID<span className="hint">optional</span>
              <input value={f.station_id} onChange={set('station_id')} maxLength={100} list="known-stations" placeholder="Choose or enter a station" />
              <datalist id="known-stations">{context.data?.stations?.map(station =>
                <option key={station.station_id} value={station.station_id}>{station.data_origin === 'simulated' ? 'Demo station' : 'Recorded station'}</option>)}</datalist>
            </label>
          </div>
          {matched && <p className="small muted" role="status">Session found. Recorded station: {context.data.session.station_id}. You can edit the station if needed.</p>}
          {context.error && <p className="small muted">Station suggestions are unavailable. You can still submit your complaint or enter a station yourself.</p>}
          <details style={{ margin: '0 0 18px' }}>
            <summary>Additional details (optional)</summary>
            <div className="row" style={{ marginTop: 12 }}>
              <label className="field">Error shown<input value={f.reported_error} onChange={set('reported_error')} placeholder="e.g. E101" maxLength={200} /></label>
              <label className="field">Customer-reported payment<select value={f.reported_payment_status} onChange={set('reported_payment_status')}>
                <option value="">Not specified</option><option value="deducted">Deducted</option>
                <option value="not_deducted">Not deducted</option><option value="refund_pending">Refund pending</option><option value="unknown">Unknown</option>
              </select><span className="hint">A customer report, not payment verification.</span></label>
            </div>
            <label className="field">User reference<span className="hint">pseudonymous</span><input value={f.user_ref} onChange={set('user_ref')} maxLength={100} /></label>
            <label className="field">Data origin<select value={f.data_origin} onChange={set('data_origin')}>
              <option value="manual_test">Manual test</option><option value="simulated">Simulated</option><option value="real_public_review">Real public review</option>
            </select></label>
          </details>
          <div className="row">
            <button className="btn primary" disabled={busy}>{busy ? 'Saving / investigating…' : '🔎 Run diagnosis'}</button>
            <button className="btn" type="submit" value="save" disabled={busy}>Save ticket before investigation</button>
          </div>
        </form>
        <div className="card" style={{ alignSelf: 'start' }}>
          <h2>Start with an issue</h2>
          <p className="muted small">Choose what happened to fill a short complaint, then edit it to match your visit.</p>
          {STARTERS.map(starter => <button key={starter.label} type="button" className="btn"
            style={{ display: 'block', width: '100%', marginBottom: 8, textAlign: 'left' }}
            onClick={() => setF(current => ({ ...current, complaint_text: starter.text }))}>{starter.label}</button>)}
          <p className="muted small">No session or station reference? You can still submit. We will ask for any evidence needed.</p>
          <p className="muted small">Station IDs can fill from your session. Location-based station detection is not available yet.</p>
          <details>
            <summary>Demo examples</summary>
            <p className="muted small">These examples use synthetic records. The first requires the seeded demo logs.</p>
            {SAMPLES.map(sample => <button key={sample.label} type="button" className="btn"
              style={{ display: 'block', width: '100%', marginBottom: 8, textAlign: 'left' }}
              onClick={() => setF({ ...emptyForm(), ...sample })}>{sample.label}</button>)}
          </details>
        </div>
      </div>
    </>
  )
}
