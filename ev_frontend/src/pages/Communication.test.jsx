import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import Communication from './Communication'
import { api } from '../api'

vi.mock('../api', () => ({ api: Object.fromEntries(['communicationTemplates', 'communicationSessions', 'communicationSession', 'generateCommunication', 'diagnoseCommunication', 'runCommunicationEvaluation'].map(k => [k, vi.fn()])) }))
const components = Object.fromEntries(['app', 'csms', 'charger', 'connector', 'vehicle', 'bms', 'payment', 'network'].map(c => [c, c + '-1']))
const session = { session_id: 'MC-test', trace_id: 'TRACE-test', components, status: 'failed', event_count: 2 }
const events = [{ event_id: 'E1', component_type: 'app', component_id: 'app-1', timestamp: '2026-10-01T00:00:00.000Z', event_type: 'message.sent', severity: 'info', status: 'ok', message: 'Send command', correlation_id: 'COR-1', message_id: 'M1', payload: {} },
  { event_id: 'E2', component_type: 'network', component_id: 'network-1', timestamp: '2026-10-01T00:00:00.100Z', event_type: 'transport.dropped', severity: 'error', status: 'lost', message: 'Dropped command', correlation_id: 'COR-1', message_id: 'M1', payload: {} }]
const detail = { session, events, components: [{ component_type: 'network', component_id: 'network-1', health: 'degraded', connection: 'message_loss' }],
  flows: [{ message_id: 'M1', source: 'app', target: 'csms', operation: 'RequestStartTransaction', status: 'dropped', correlation_id: 'COR-1' }],
  anomalies: [{ code: 'message_dropped', severity: 'error', component_type: 'network', description: 'Transport dropped the command.', event_ids: ['E1', 'E2'] }], diagnosis: null }
const mount = () => render(<MemoryRouter><Communication /></MemoryRouter>)

beforeEach(() => {
  vi.resetAllMocks()
  api.communicationTemplates.mockResolvedValue({ scenarios: ['none', 'network_loss'] })
  api.communicationSessions.mockResolvedValue({ items: [session], total: 1, page: 1 })
  api.communicationSession.mockResolvedValue(detail)
})

it('shows empty/loading state and can generate a session', async () => {
  api.communicationSessions.mockResolvedValue({ items: [], total: 0, page: 1 })
  api.generateCommunication.mockImplementation(async () => {
    api.communicationSessions.mockResolvedValue({ items: [session], total: 1, page: 1 })
    return { run_id: 'run-1', inserted: 1, total: 1, session_ids: ['MC-test'], warnings: [] }
  })
  mount()
  expect(await screen.findByText(/No simulated communication sessions yet/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Generate sessions' }))
  expect(await screen.findByText('Chronological session logs')).toBeInTheDocument()
  expect(api.generateCommunication).toHaveBeenCalledWith(expect.objectContaining({ seed: 42, split: 'test' }))
})

it('renders session events, component health and component filtering', async () => {
  mount()
  expect(await screen.findByText('Dropped command')).toBeInTheDocument()
  expect(screen.getByText('Connection: message_loss')).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Component filter' }), 'network')
  expect(screen.queryByText('Send command')).not.toBeInTheDocument()
  expect(screen.getByText('Dropped command')).toBeInTheDocument()
})

it('explains missing BMS and payment records and opens their session filters', async () => {
  mount()
  await screen.findByText('Chronological session logs')
  const bms = screen.getByRole('group', { name: 'BMS component logs' })
  expect(within(bms).getByText('0 recorded events')).toBeInTheDocument()
  expect(within(bms).queryByText(/Last recorded/)).not.toBeInTheDocument()
  await userEvent.click(within(bms).getByRole('button', { name: 'View BMS logs (0)' }))
  expect(screen.getByRole('combobox', { name: 'Component filter' })).toHaveValue('bms')
  expect(screen.getByText(/No BMS records were captured for this session/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'View Payment logs (0)' }))
  expect(screen.getByText(/No Payment records were captured for this session/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Show all session logs' }))
  expect(screen.getByText('Dropped command')).toBeInTheDocument()
})

it('opens actual BMS, payment and network records with timestamps and clears an old search', async () => {
  const bmsEvent = { ...events[0], event_id: 'E3', component_type: 'bms', component_id: 'bms-1',
    timestamp: '2026-10-01T00:00:00.200Z', event_type: 'battery.telemetry', message: 'Battery temperature recorded' }
  const paymentEvent = { ...events[0], event_id: 'E4', component_type: 'payment', component_id: 'payment-1',
    timestamp: '2026-10-01T00:00:00.300Z', event_type: 'payment.result', message: 'Payment result recorded' }
  api.communicationSession.mockResolvedValue({ ...detail, events: [...events, bmsEvent, paymentEvent] })
  mount()
  await screen.findByText('Chronological session logs')
  const bms = screen.getByRole('group', { name: 'BMS component logs' })
  expect(within(bms).getByText('1 recorded event')).toBeInTheDocument()
  expect(within(bms).getByText(bmsEvent.timestamp)).toBeInTheDocument()
  await userEvent.type(screen.getByRole('textbox', { name: 'Search events' }), 'unmatched-search')
  expect(screen.getByText('No events match these filters.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'View BMS logs (1)' }))
  expect(screen.getByRole('textbox', { name: 'Search events' })).toHaveValue('')
  expect(screen.getByText('Battery temperature recorded')).toBeInTheDocument()
  expect(screen.queryByText('Payment result recorded')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'View Payment logs (1)' }))
  expect(screen.getByText('Payment result recorded')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'View Network logs (1)' }))
  expect(screen.getByText('Dropped command')).toBeInTheDocument()
})

it('distinguishes a health check from component activity logs', async () => {
  api.communicationSession.mockResolvedValue({ ...detail, events: [...events,
    { ...events[0], event_id: 'E3', component_type: 'bms', event_type: 'component.health', message: 'Initial BMS health' }] })
  mount()
  await screen.findByText('Chronological session logs')
  const bms = screen.getByRole('group', { name: 'BMS component logs' })
  expect(within(bms).getByText('1 recorded event')).toBeInTheDocument()
  expect(within(bms).getByText(/Only a health check is recorded/)).toBeInTheDocument()
})

it('shows the flow diagram and filters logs by a selected correlation', async () => {
  mount()
  await screen.findByText('Chronological session logs')
  await userEvent.click(screen.getByRole('button', { name: /Message flow/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Inspect RequestStartTransaction from app to csms' }))
  expect(screen.getByRole('textbox', { name: 'Search events' })).toHaveValue('COR-1')
})

it('shows failure evidence and can navigate back to its event', async () => {
  mount()
  await screen.findByText('Chronological session logs')
  await userEvent.click(screen.getByRole('button', { name: /Communication failures & conflicts/ }))
  expect(screen.getByText('Transport dropped the command.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'E2', exact: true }))
  expect(document.getElementById('event-E2')).toHaveClass('comm-highlight')
})

it('runs diagnosis and links to existing reviewer feedback', async () => {
  const diagnosis = { root_cause: 'network_loss', component_type: 'network', classification: 'probable', evidence_strength: .8, confidence: .9,
    diagnostic_checks: 4, unresolved_questions: [], evidence: [{ description: 'Confirmed transport failure', event_ids: ['E2'] }], case_id: 'C-test' }
  api.diagnoseCommunication.mockImplementation(async () => { api.communicationSession.mockResolvedValue({ ...detail, diagnosis }); return diagnosis })
  mount()
  await userEvent.click(await screen.findByRole('button', { name: 'Diagnose session' }))
  expect(await screen.findByText('Confirmed transport failure')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Open case for reviewer/ })).toHaveAttribute('href', '/cases/C-test')
  expect(api.diagnoseCommunication).toHaveBeenCalledWith('MC-test')
})

it('shows API errors with retry and no false empty claim', async () => {
  api.communicationSessions.mockRejectedValue(new Error('Session service unavailable'))
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Session service unavailable')
  expect(screen.queryByText(/No simulated communication sessions yet/)).not.toBeInTheDocument()
})

it('presents contradictory observations as inconclusive and links their evidence', async () => {
  const diagnosis = { root_cause: null, component_type: null, classification: 'inconclusive', evidence_strength: 0, confidence: null,
    diagnostic_checks: 4, unresolved_questions: ['Conflicting observations require verification.'],
    evidence: [{ kind: 'conflicting', description: 'The same message was reported as dropped and received.', event_ids: ['E1', 'E2'] }] }
  api.communicationSession.mockResolvedValue({ ...detail, flows: [{ ...detail.flows[0], status: 'conflicting' }], diagnosis })
  mount()
  await screen.findByText('Chronological session logs')
  await userEvent.click(screen.getByRole('button', { name: /Message flow/ }))
  const flow = screen.getByRole('button', { name: 'Inspect RequestStartTransaction from app to csms' })
  expect(flow.querySelector('line')).toHaveAttribute('stroke', '#b42318')
  await userEvent.click(screen.getByRole('button', { name: 'Root-cause diagnosis' }))
  expect(screen.getByText('Inconclusive: insufficient or conflicting evidence')).toBeInTheDocument()
  expect(screen.queryByText(/Synthetic calibrated confidence:/)).not.toBeInTheDocument()
  expect(screen.getByText(diagnosis.evidence[0].description).closest('.ev')).toHaveClass('conflicting')
  await userEvent.click(screen.getByRole('button', { name: 'E2', exact: true }))
  expect(document.getElementById('event-E2')).toHaveClass('comm-highlight')
})
