import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import NewCase from './NewCase'
import Cases from './Cases'
import CaseDetail from './CaseDetail'
import Knowledge from './Knowledge'
import Reviews from './Reviews'
import Evaluation from './Evaluation'
import Dashboard from './Dashboard'

vi.mock('../api', () => ({ api: Object.fromEntries(['apps','intakeContext','openTicket','categories','reviewers','listCases','submitCase','getCase','getTrace','submitResolution','previewLearning','applyLearning','rules','priors','changes','revertChange','activateRule','rollback','evalSummary','runEval','listReviews','importReviews','performance','recurring','ticketSummary'].map(k => [k, vi.fn()])) }))
const cats = [{ id: 'session_fails_to_start', label: 'Session fails to start' }]
const appRows = [{ id: 'tata_power_ez_charge', display_name: 'Tata Power EZ Charge' }]
const diag = { primary_category: 'session_fails_to_start', classification: 'probable', evidence_strength: .7, evidence_strength_label: 'moderate', confidence: .9, contributing_categories: [], unresolved_questions: [], stop_reason: 'confidence_threshold_reached', version: 1 }
const summary = { case_id: 'C-test', app_id: 'tata_power_ez_charge', complaint_text_redacted: 'Charging never started', status: 'awaiting_review', data_origin: 'manual_test', diagnosis: diag }
const full = { case: summary, complaint: {}, diagnosis: diag, evidence: { matching: [{ id: 1, description: 'Start timeout in charger log', tool_name: 'timeline_check', weight: .7 }] }, recommendations: [], resolution: null }
const trace = { steps: [{ step_no: 1, tool_name: 'timeline_check', selection_reason: 'Checks start failure', outcome_summary: 'Start timeout', candidate_scores: [], state_changes: {}, result: {} }], final_beliefs: {}, stop_reason: 'confidence_threshold_reached' }
const mount = component => render(<MemoryRouter>{component}</MemoryRouter>)

beforeEach(() => {
  vi.resetAllMocks()
  api.apps.mockResolvedValue(appRows)
  api.intakeContext.mockResolvedValue({session:null,stations:[],location_available:false})
  api.categories.mockResolvedValue(cats)
  api.reviewers.mockResolvedValue([{ reviewer_id: 'rev-001', name: 'Reviewer', active: true, role: 'reviewer' }])
  api.listCases.mockResolvedValue({ items: [], total: 0, page: 1 })
  api.getCase.mockResolvedValue(full)
  api.getTrace.mockResolvedValue(trace)
  api.rules.mockResolvedValue([])
  api.priors.mockResolvedValue([])
  api.changes.mockResolvedValue([])
  api.listReviews.mockResolvedValue([])
  api.evalSummary.mockResolvedValue({ available: false })
  api.ticketSummary.mockResolvedValue({ open_escalated: 2, open_awaiting_evidence: 1, open_in_triage: 3, human_overrides: 1, open_by_priority: { P0: 1, P1: 1 }, delivery_scope: 'Local internal assignments only; no external message or ticket is sent.' })
})

describe('complaint and case workflow', () => {
  it('submits the sample and navigates using the real nested API response', async () => {
    api.submitCase.mockResolvedValue({ case_summary: summary, case: full })
    render(<MemoryRouter initialEntries={['/new']}><Routes><Route path="/new" element={<NewCase />} /><Route path="/cases/:id" element={<p>Diagnosis loaded</p>} /></Routes></MemoryRouter>)
    await userEvent.click(screen.getByText('Demo examples'))
    await userEvent.click(await screen.findByRole('button', { name: /Session never started/ }))
    await userEvent.click(screen.getByRole('button', { name: /Run diagnosis/ }))
    expect(await screen.findByText('Diagnosis loaded')).toBeInTheDocument()
    expect(api.submitCase).toHaveBeenCalledWith(expect.objectContaining({ session_ref: 'SSN-042-0001', app_id: 'tata_power_ez_charge' }))
  })
  it('allows intake even when station suggestions are unavailable', async () => {
    api.intakeContext.mockRejectedValue(new Error('Backend unavailable'))
    mount(<NewCase />)
    expect(await screen.findByText(/Station suggestions are unavailable/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', {name:'Complaint *'})).toBeInTheDocument()
    expect(screen.getByRole('button', {name:/Run diagnosis/})).toBeEnabled()
  })
  it('defaults to local current time, removes the app selector and limits the complaint to 500 characters', async () => {
    mount(<NewCase />)
    const date = screen.getByLabelText(/When did it happen/)
    expect(Math.abs(new Date(date.value).getTime() - Date.now())).toBeLessThan(61000)
    expect(screen.queryByLabelText(/^App/)).not.toBeInTheDocument()
    expect(api.apps).not.toHaveBeenCalled()
    expect(screen.getByRole('textbox', {name:'Complaint *'})).toHaveAttribute('maxlength','500')
    expect(screen.getByLabelText(/User reference/)).not.toBeVisible()
    await userEvent.click(screen.getByRole('button', {name:'Charging will not start'}))
    const text = screen.getByRole('textbox', {name:'Complaint *'}).value
    expect(text.length).toBeGreaterThanOrEqual(100)
    expect(text.length).toBeLessThanOrEqual(500)
    expect(screen.getByText(`${text.length}/500`)).toBeInTheDocument()
  })
  it('submits a short complaint without choosing a provider', async () => {
    api.submitCase.mockResolvedValue({case:full})
    render(<MemoryRouter initialEntries={['/new']}><Routes><Route path="/new" element={<NewCase />} /><Route path="/cases/:id" element={<p>Diagnosis loaded</p>} /></Routes></MemoryRouter>)
    await userEvent.click(screen.getByRole('button',{name:'Charging stopped early'}))
    await userEvent.click(screen.getByRole('button',{name:/Run diagnosis/}))
    await screen.findByText('Diagnosis loaded')
    expect(api.submitCase).toHaveBeenCalledWith(expect.objectContaining({complaint_ts:expect.any(String)}))
    expect(api.submitCase.mock.calls[0][0]).not.toHaveProperty('app_id')
  })
  it('fills a station from a session and preserves the chosen date', async () => {
    api.intakeContext.mockImplementation(async ({session_ref}) => ({stations:[],session:session_ref === 'SSN-test' ?
      {session_id:'SSN-test',station_id:'STN-test',app_id:'statiq'}:null}))
    mount(<NewCase />)
    const date = screen.getByLabelText(/When did it happen/)
    fireEvent.change(date,{target:{value:'2026-11-01T10:30'}})
    fireEvent.change(screen.getByLabelText(/Session reference/),{target:{value:'SSN-test'}})
    await waitFor(() => expect(screen.getByLabelText(/Station ID/)).toHaveValue('STN-test'))
    expect(date).toHaveValue('2026-11-01T10:30')
    fireEvent.change(screen.getByLabelText(/Session reference/),{target:{value:''}})
    expect(screen.getByLabelText(/Station ID/)).toHaveValue('')
  })
  it('paginates then resets the page when filters change', async () => {
    api.listCases.mockImplementation(async ({ page }) => ({ items: [summary], total: 31, page }))
    mount(<Cases />)
    await screen.findByRole('link', { name: 'C-test' })
    await userEvent.click(screen.getByRole('button', { name: /Next/ }))
    await waitFor(() => expect(api.listCases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
    await userEvent.selectOptions(screen.getByLabelText('App'), 'tata_power_ez_charge')
    await waitFor(() => expect(api.listCases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, app_id: 'tata_power_ez_charge' })))
  })
  it('displays API errors without incorrectly claiming no matches', async () => {
    api.listCases.mockRejectedValue(new Error('Server failed'))
    mount(<Cases />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Server failed')
    expect(screen.queryByText('No cases match these filters.')).not.toBeInTheDocument()
  })
  it('shows evidence, accepts feedback, previews and applies learning', async () => {
    api.submitResolution.mockImplementation(async () => {
      api.getCase.mockResolvedValue({ ...full, resolution: { verified_root_cause: 'session_fails_to_start', agent_prediction_category: 'session_fails_to_start', prediction_correct: 1, verified_contributing_json: '[]', corrective_action: 'Verified start timeout', learning_applied: 0 } })
      return { resolution_id: 1 }
    })
    api.previewLearning.mockResolvedValue({ changes: [{ change_type: 'update', signal_key: 'start_timeout', old_value: .7, new_value: .8, reason: 'Verified evidence' }] })
    api.applyLearning.mockResolvedValue({ applied: true })
    render(<MemoryRouter initialEntries={['/cases/C-test']}><Routes><Route path="/cases/:caseId" element={<CaseDetail />} /></Routes></MemoryRouter>)
    expect(await screen.findByText(/Synthetic calibrated confidence/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Evidence' }))
    expect(screen.getByText('Start timeout in charger log')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Verify & learn' }))
    await userEvent.selectOptions(screen.getByLabelText(/Reviewer \*/), 'rev-001')
    await userEvent.type(screen.getByLabelText(/Corrective action/), 'Verified start timeout')
    await userEvent.click(screen.getByRole('button', { name: /Submit verified resolution/ }))
    await screen.findByText('Verified resolution')
    await userEvent.click(screen.getByRole('button', { name: /Preview changes/ }))
    expect(await screen.findByText('Verified evidence')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Apply learning/ }))
    await waitFor(() => expect(api.applyLearning).toHaveBeenCalledWith('C-test'))
  })
})

describe('knowledge, import and evaluation pages', () => {
  it('activates an inactive proposed rule', async () => {
    api.rules.mockResolvedValue([{ rule_id: 1, category: 'session_fails_to_start', signal_key: 'start_timeout', weight: .5, source: 'learned', active: false, version: 1 }])
    api.activateRule.mockResolvedValue({ changed: true })
    mount(<Knowledge />)
    await userEvent.click(await screen.findByRole('button', { name: 'Activate' }))
    expect(api.activateRule).toHaveBeenCalledWith(1, true)
    expect(await screen.findByText('Rule #1 updated.')).toBeInTheDocument()
  })
  it('uploads a review file and refreshes stored reviews', async () => {
    api.importReviews.mockImplementation(async () => {
      api.listReviews.mockResolvedValue([{ review_id: 1, app_id: 'statiq', redacted_text: 'Charging failed', data_origin: 'manual_test' }])
      return { imported: 1, skipped: 0, errors: [] }
    })
    mount(<Reviews />)
    const file = new File(['text,data_origin\nCharging failed,manual_test'], 'reviews.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByLabelText('Review file'), file)
    await userEvent.click(screen.getByRole('button', { name: /Import$/ }))
    expect(api.importReviews).toHaveBeenCalledWith(file)
    expect(await screen.findByText('Charging failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Import$/ })).toBeDisabled()
    expect(screen.queryByLabelText('App')).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'App', exact: true })).not.toBeInTheDocument()
    expect(api.apps).not.toHaveBeenCalled()
    expect(api.listReviews).toHaveBeenCalledWith({data_origin:'',limit:25,offset:0})
  })
  it('runs evaluation and displays a structured error', async () => {
    api.runEval.mockRejectedValue(new Error('Evaluation already running'))
    mount(<Evaluation />)
    await screen.findByText(/No evaluation has been run/)
    await userEvent.click(screen.getByRole('button', { name: /Run evaluation/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Evaluation already running')
    expect(api.runEval).toHaveBeenCalledWith({ seed: 42, cases_per_category: 8 })
  })
  it('prevents evaluation with out-of-range case counts', async () => {
    mount(<Evaluation />)
    fireEvent.change(screen.getByLabelText('Cases / template'), { target: { value: '0' } })
    expect(screen.getByRole('button', { name: /Run evaluation/ })).toBeDisabled()
  })
  it('shows the ticket queue summary with its local-only delivery scope', async () => {
    api.performance.mockResolvedValue({ primary_accuracy_pct: null, total_resolved_cases: 0 })
    api.recurring.mockResolvedValue({ by_app_category: [], data_origin_counts: {} })
    mount(<Dashboard />)
    expect(await screen.findByText('Open escalated')).toBeInTheDocument()
    expect(screen.getByText('In triage queue')).toBeInTheDocument()
    expect(screen.getByText(/P0 1 · P1 1 · P2 0 · P3 0/)).toBeInTheDocument()
    expect(screen.getByText(/no external message or ticket is sent/)).toBeInTheDocument()
  })
  it('shows dashboard loading and error recovery', async () => {
    api.performance.mockRejectedValue(new Error('Metrics unavailable'))
    api.recurring.mockResolvedValue({})
    mount(<Dashboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Metrics unavailable')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
