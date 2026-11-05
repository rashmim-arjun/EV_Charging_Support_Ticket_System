// Thin client for the FastAPI backend (/api/v1). Errors use the backend's
// consistent shape: { error: { code, message, details } }.
export const BASE = (import.meta.env.VITE_API_BASE?.trim() || '/api/v1').replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request(path, { method = 'GET', body, form, params, headers = {}, responseType } = {}) {
  let url = BASE + path
  if (params) {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, v)
    })
    const s = q.toString()
    if (s) url += '?' + s
  }
  const opts = { method, headers: { ...headers } }
  if (form) opts.body = form
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(url, opts)
  } catch {
    throw new ApiError(0, 'network_error',
      `Cannot reach ${BASE}. Check that FastAPI is running on port 8000 and that the API URL and allowed CORS origin match this page. Retry after starting the backend.`)
  }
  if (res.ok && responseType === 'blob') return res.blob()
  let data = null
  try { data = await res.json() } catch {
    if (res.ok && res.status !== 204) throw new ApiError(res.status, 'invalid_response',
      `Expected JSON from ${url}. Check VITE_API_BASE (including /api/v1) and the /api proxy configuration.`)
  }
  if (!res.ok) {
    const e = data?.error || {}
    throw new ApiError(res.status, e.code || 'http_' + res.status,
      e.message || (res.status === 502 || res.status === 504
        ? 'The API proxy could not reach FastAPI. Start the backend on port 8000, then retry.'
        : res.statusText || `API request failed (HTTP ${res.status}).`), e.details)
  }
  return data
}

export const api = {
  communicationTemplates: () => request('/communication/templates'),
  communicationSessions: params => request('/communication/sessions', { params }),
  communicationSession: id => request(`/communication/sessions/${encodeURIComponent(id)}`),
  generateCommunication: body => request('/communication/generate', { method: 'POST', body }),
  diagnoseCommunication: id => request(`/communication/sessions/${encodeURIComponent(id)}/diagnose`, { method: 'POST' }),
  runCommunicationEvaluation: body => request('/communication/evaluation', { method: 'POST', body }),
  communicationEvaluation: () => request('/communication/evaluation'),
  health: () => request('/health'),
  apps: () => request('/apps'),
  categories: () => request('/categories'),
  reviewers: () => request('/reviewers'),

  listCases: (params) => request('/cases', { params }),
  getCase: (id) => request(`/cases/${id}`),
  ticketPolicy: () => request('/tickets/policy'),
  ticketSummary: () => request('/tickets/summary'),
  openTicket: (body) => request('/tickets', {method:'POST',body}),
  intakeContext: (params) => request('/tickets/intake-context', { params }),
  updateTicket: (id,body) => request(`/tickets/${id}`, { method:'PATCH',body }),
  investigateTicket: (id) => request(`/tickets/${id}/investigate`, { method:'POST' }),
  getPayment: id => request(`/tickets/${encodeURIComponent(id)}/payment`),
  submitPayment: (id, form) => request(`/tickets/${encodeURIComponent(id)}/payment/submissions`, { method:'POST',form }),
  reviewPayment: (id, body, reviewerId) => request(`/tickets/${encodeURIComponent(id)}/payment/review`, {
    method:'POST',body,headers:{'X-Reviewer-ID':reviewerId} }),
  paymentProof: (id, submissionId, reviewerId) => request(`/tickets/${encodeURIComponent(id)}/payment/submissions/${encodeURIComponent(submissionId)}/proof`, {
    headers:{'X-Reviewer-ID':reviewerId},responseType:'blob' }),
  getTrace: (id) => request(`/cases/${id}/trace`),
  submitCase: (body) => request('/cases', { method: 'POST', body }),
  submitResolution: (id, body) =>
    request(`/cases/${id}/resolution`, { method: 'POST', body }),
  previewLearning: (id) =>
    request(`/cases/${id}/learning/preview`, { method: 'POST' }),
  applyLearning: (id) =>
    request(`/cases/${id}/learning/apply`, { method: 'POST' }),

  rules: () => request('/knowledge/rules'),
  activateRule: (id, active) => request(`/knowledge/rules/${id}/activation`, { method: 'POST', body: { active, reason: active ? 'Reviewer approved rule activation' : 'Reviewer deactivated rule' } }),
  priors: () => request('/knowledge/tool-priors'),
  changes: () => request('/knowledge/changes'),
  revertChange: (id) => request(`/knowledge/changes/${id}/revert`, { method: 'POST' }),
  rollback: (to_change_id, reason) =>
    request('/knowledge/rollback', { method: 'POST', body: { to_change_id, reason } }),

  performance: (params) => request('/metrics/performance', { params }),
  recurring: (params) => request('/metrics/recurring', { params }),

  evalSummary: () => request('/evaluation/summary'),
  runEval: (body) => request('/evaluation/run', { method: 'POST', body }),

  listReviews: (params) => request('/reviews', { params }),
  importReviews: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/reviews/import', { method: 'POST', form })
  },
}
