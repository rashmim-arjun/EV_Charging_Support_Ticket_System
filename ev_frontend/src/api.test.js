import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, BASE } from './api'

afterEach(() => vi.unstubAllGlobals())
describe('API transport contract', () => {
  it('sends payment proof as multipart and review identity only in its dedicated header', async () => {
    const fetch = vi.fn().mockResolvedValue({ok:true,json:async () => ({status:'submitted'})})
    vi.stubGlobal('fetch',fetch)
    const form = new FormData()
    form.append('version','0');form.append('transaction_reference','UPI-123456789012')
    await api.submitPayment('C-test',form)
    expect(fetch.mock.calls[0][1].body).toBe(form)
    expect(fetch.mock.calls[0][1].headers['Content-Type']).toBeUndefined()
    await api.reviewPayment('C-test',{version:1,decision:'under_review',reason:'Manually reviewing'},'rev-payment-001')
    expect(fetch.mock.calls[1][1].headers['X-Reviewer-ID']).toBe('rev-payment-001')
    expect(JSON.parse(fetch.mock.calls[1][1].body)).not.toHaveProperty('reviewer_id')
  })
  it('uses the same-origin proxy by default', () => {
    expect(BASE).toBe('/api/v1')
  })
  it('encodes filters and omits empty values', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) })
    vi.stubGlobal('fetch', fetch)
    await api.listCases({ app_id: 'a & b', category: '', page: 2 })
    expect(fetch.mock.calls[0][0]).toContain('app_id=a+%26+b&page=2')
  })
  it('preserves backend error details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ error: { code: 'validation_error', message: 'Bad input', details: [{ msg: 'Too short' }] } }) }))
    await expect(api.submitCase({})).rejects.toMatchObject({ status: 422, code: 'validation_error', message: 'Bad input' })
  })
  it('shows a useful network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed fetch')))
    await expect(api.health()).rejects.toMatchObject({ code: 'network_error' })
  })
  it('preserves proxy outage instructions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502,
      json: async () => ({ error: { code: 'backend_unavailable', message: 'Start FastAPI on port 8000, then retry.' } }) }))
    await expect(api.health()).rejects.toMatchObject({ code: 'backend_unavailable', message: 'Start FastAPI on port 8000, then retry.' })
  })
  it('explains gateway errors even without JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502,
      json: async () => { throw new SyntaxError('Not JSON') } }))
    await expect(api.health()).rejects.toMatchObject({ status: 502, message: expect.stringContaining('Start the backend') })
  })
  it('explains HTML returned by a wrong API route', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200,
      json: async () => { throw new SyntaxError('HTML') } }))
    await expect(api.health()).rejects.toMatchObject({ code: 'invalid_response', message: expect.stringContaining('VITE_API_BASE') })
  })
  it('sends reviews as multipart without overriding the content type', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ imported: 1 }) })
    vi.stubGlobal('fetch', fetch)
    await api.importReviews(new File(['test'], 'reviews.csv'))
    const opts = fetch.mock.calls[0][1]
    expect(opts.body).toBeInstanceOf(FormData)
    expect(opts.headers['Content-Type']).toBeUndefined()
  })
})
