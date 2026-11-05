import { useState } from 'react'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Badge, Empty, ErrorBox, Spinner } from './ui'
import { fmtDate } from '../format'

const labels = {not_submitted:'Not submitted',submitted:'Submitted - not verified',
  under_review:'Under manual review',verified:'Verified by manual reviewer',rejected:'Rejected'}
const tones = {not_submitted:'gray',submitted:'blue',under_review:'amber',verified:'green',rejected:'red'}

export default function PaymentPanel({ caseId, reviewers = [], onChange }) {
  const loaded = useAsync(() => api.getPayment(caseId), [caseId])
  const [current,setCurrent] = useState(null)
  const [reference,setReference] = useState('')
  const [file,setFile] = useState(null)
  const [fileKey,setFileKey] = useState(0)
  const [reviewerId,setReviewerId] = useState('')
  const [reason,setReason] = useState('')
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState(null)
  const payment = current || loaded.data
  const authorized = reviewers.filter(r => r.active && r.role === 'payment_reviewer')
  const selectedReviewer = authorized.some(r => r.reviewer_id === reviewerId)
  const reload = () => { setCurrent(null);setError(null);loaded.reload() }
  const act = async fn => {
    setBusy(true);setError(null)
    try { const result = await fn();if(result) setCurrent(result);onChange?.() }
    catch(e) { setError(e) }
    finally { setBusy(false) }
  }
  const submit = e => {
    e.preventDefault()
    const value = reference.trim()
    if (!value && !file) { setError(new Error('Provide a transaction reference or a payment screenshot.'));return }
    if (value && !/^[A-Za-z0-9][A-Za-z0-9._/\-]{5,99}$/.test(value)) {
      setError(new Error('Use a transaction reference of 6-100 letters, digits, dots, slashes, underscores or hyphens.'));return
    }
    if (file && (!['image/png','image/jpeg'].includes(file.type) || file.size>2*1024*1024 || file.size===0)) {
      setError(new Error('Upload a non-empty PNG or JPEG screenshot, at most 2 MB.'));return
    }
    const form = new FormData()
    form.append('version',payment.version)
    if(value) form.append('transaction_reference',value)
    if(file) form.append('proof',file)
    act(async () => {
      const result = await api.submitPayment(caseId,form)
      setReference('');setFile(null);setFileKey(key => key+1)
      return result
    })
  }
  const review = e => {
    e.preventDefault()
    const decision = e.nativeEvent.submitter?.value
    if (!selectedReviewer || reason.trim().length<5 || !decision) return
    act(async () => {
      const result = await api.reviewPayment(caseId,{version:payment.version,decision,reason:reason.trim()},reviewerId)
      setReason('');return result
    })
  }
  const download = submission => act(async () => {
    const blob = await api.paymentProof(caseId,submission.submission_id,reviewerId)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href=url;anchor.download=submission.proof.name;anchor.click()
    setTimeout(() => URL.revokeObjectURL(url),1000)
  })
  return <section className="card payment-panel" aria-label="Payment verification">
    <div className="section-head"><h2>Payment verification</h2>
      {payment && <Badge tone={tones[payment.status]}>{labels[payment.status]}</Badge>}</div>
    <p className="small muted">A transaction reference or screenshot is a customer submission, not confirmation of payment. Verification is a manual reviewer decision, separate from charging diagnosis and ticket resolution.</p>
    {loaded.loading && !payment && <Spinner />}
    <ErrorBox error={error || loaded.error} onRetry={reload} />
    {busy && <p role="status">Saving or loading payment information...</p>}
    {payment && <>
      <button type="button" className="btn sm" disabled={busy || loaded.loading} onClick={reload}>Reload payment status</button>
      {!payment.submission ? <Empty>No payment proof has been submitted for this ticket.</Empty> : <div className="payment-summary">
        <p><strong>Transaction reference:</strong> <span className="mono">{payment.submission.transaction_reference || 'Not provided'}</span></p>
        <p><strong>{payment.submission.source==='legacy_claim'?'Imported for review':'Submitted'}:</strong> {fmtDate(payment.submission.submitted_at)}</p>
        <p><strong>Screenshot:</strong> {payment.submission.proof ? `${payment.submission.proof.name} (${payment.submission.proof.size} bytes)` : 'Not uploaded'}</p>
        {payment.submission.source==='legacy_claim' && <p className="alert warn">Historical payment claim retained. This does not establish payment success; manual review is required. The original submission time is unknown.</p>}
        {payment.reviewer_id && <div className={payment.status==='rejected'?'alert error':'alert'}>
          <strong>{payment.status==='under_review'?'Review started by':'Reviewer decision by'}:</strong> {payment.reviewer_id} at {fmtDate(payment.reviewed_at)}
          <p>{payment.status==='rejected'?'Rejection reason':'Review reason'}: {payment.reason}</p>
        </div>}
      </div>}
      {['not_submitted','rejected'].includes(payment.status) && <form onSubmit={submit} aria-label="Submit payment proof">
        <h3>{payment.status==='rejected'?'Submit corrected payment proof':'Submit payment proof'}</h3>
        <fieldset disabled={busy || loaded.loading}>
          <label className="field">Transaction reference<input maxLength={100} value={reference} onChange={e => setReference(e.target.value)} placeholder="UPI / bank transaction reference" /></label>
          <label className="field">Payment screenshot (optional)<input key={fileKey} type="file" accept="image/png,image/jpeg" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
          <p className="small muted">Provide a reference, a screenshot, or both. PNG/JPEG, maximum 2 MB. Remove unrelated account details before uploading. Submitting proof does not verify the payment.</p>
          <button className="btn primary" disabled={busy}>{busy?'Submitting...':'Submit payment information'}</button>
        </fieldset>
      </form>}
      <details className="payment-review"><summary>Manual reviewer actions</summary>
        <p className="small muted">Local demo identity selection only; no production login. Only active payment reviewers can record decisions.</p>
        <form onSubmit={review} aria-label="Review payment">
          <fieldset disabled={busy || loaded.loading}>
            <label className="field">Payment reviewer<select required value={reviewerId} onChange={e => setReviewerId(e.target.value)}>
              <option value="">Select a local payment reviewer</option>
              {authorized.map(r => <option key={r.reviewer_id} value={r.reviewer_id}>{r.name} ({r.reviewer_id})</option>)}
            </select></label>
            {!authorized.length && <p>No active payment reviewer is configured. A reviewer with the payment_reviewer role must be enabled locally.</p>}
            {payment.submission?.proof && <button type="button" className="btn" disabled={!selectedReviewer} onClick={() => download(payment.submission)}>Download submitted screenshot</button>}
            {['submitted','under_review'].includes(payment.status) ? <>
              <label className="field">Manual review reason<textarea required minLength={5} maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} placeholder="Record what you checked and the reason for this manual decision" /></label>
              <div className="row">
                {payment.status==='submitted' ? <button className="btn" value="under_review" disabled={!selectedReviewer || reason.trim().length<5}>Start manual review</button> : <>
                  <button className="btn primary" value="verified" disabled={!selectedReviewer || reason.trim().length<5}>Verify payment manually</button>
                  <button className="btn" value="rejected" disabled={!selectedReviewer || reason.trim().length<5}>Reject payment</button>
                </>}
              </div>
            </> : <p className="small muted">{payment.status==='not_submitted'?'Payment information must be submitted before review.':'This decision is recorded. A rejected submission can be corrected using the customer form.'}</p>}
          </fieldset>
        </form>
      </details>
      <details className="payment-history"><summary>Payment submission and review history ({payment.history.length})</summary>
        {!payment.history.length && <Empty>No payment review decisions recorded.</Empty>}
        {payment.history.map(h => <div className="rec" key={h.id}><div><strong>{h.action.replaceAll('_',' ')}</strong>
          <div className="small muted">{fmtDate(h.created_at)} - {h.actor}</div><p>{h.reason}</p>
          <details><summary>Audited payment values</summary><pre>{JSON.stringify({before:h.before,after:h.after},null,2)}</pre></details></div></div>)}
        {payment.submissions.length>1 && <><h3>Previous submissions retained</h3>{payment.submissions.slice(1).map(s => <p key={s.submission_id}>
          {fmtDate(s.submitted_at)} - {s.transaction_reference || 'Screenshot only'}{s.proof ? ` - ${s.proof.name}` : ''}
        </p>)}</>}
      </details>
      <p className="small muted">{payment.scope}</p>
    </>}
  </section>
}
