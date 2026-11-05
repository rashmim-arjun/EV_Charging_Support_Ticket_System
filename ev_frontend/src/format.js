export const titleCase = (s) =>
  (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const pct = (v, d = 1) =>
  v === null || v === undefined ? '—' : `${Number(v).toFixed(d)}%`

export const fmtDate = (s) => {
  if (!s) return '—'
  const iso = s.includes('T') ? s : s.replace(' ', 'T')
  const d = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : iso + 'Z')
  return isNaN(d) ? s : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export const CLASS_TONE = {
  no_fault_established: 'green',
  confirmed: 'green',
  probable: 'blue',
  inconclusive: 'amber',
  requires_further_investigation: 'amber',
}

export const diagnosisTitle = (diagnosis, categories = []) => {
  if (!diagnosis) return 'Awaiting investigation'
  if (diagnosis.outcome === 'no_fault_established') return 'No fault established'
  return diagnosis.primary_category
    ? categories.find(c => c.id === diagnosis.primary_category)?.label || titleCase(diagnosis.primary_category)
    : 'Insufficient evidence'
}

export const diagnosisTone = diagnosis => diagnosis?.outcome === 'no_fault_established'
  ? 'green' : CLASS_TONE[diagnosis?.classification] || 'gray'
export const STATUS_TONE = {
  open: 'gray', diagnosed: 'blue', awaiting_review: 'amber', resolved: 'green',
}
export const ORIGIN_TONE = {
  simulated: 'purple', manual_test: 'gray', real_public_review: 'green',
}
export const EVIDENCE_TONE = {
  matching: 'green', conflicting: 'red', missing: 'amber', neutral: 'gray',
}
