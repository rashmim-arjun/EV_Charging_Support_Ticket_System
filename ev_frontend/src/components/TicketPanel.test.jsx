import { render,screen,waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach,expect,it,vi } from 'vitest'
import TicketPanel from './TicketPanel'
import { api } from '../api'
vi.mock('../api',()=>({api:{ticketPolicy:vi.fn(),updateTicket:vi.fn(),investigateTicket:vi.fn()}}))
const ticket={ticket_id:'C-1',case_id:'C-1',state:'awaiting_evidence',priority:'P1',assigned_team:'triage',supporting_teams:['vehicle_specialists'],version:2,
  decision:{classification:'inconclusive',reasons:['Safety evidence requires urgent review.']},history:[{id:1,action:'created',actor:'system',reason:'Complaint received',created_at:'2026-11-04T00:00:00Z'}]}
beforeEach(()=>{vi.resetAllMocks();api.ticketPolicy.mockResolvedValue({teams:{triage:'Support triage',vehicle_specialists:'Vehicle specialists'},priorities:{P1:'High',P2:'Standard'},transitions:{awaiting_evidence:['escalated','assigned','investigating']}})})
const mount=(props={})=>render(<MemoryRouter><TicketPanel ticket={ticket} sessionId="MC-1" onChange={vi.fn()} onResolve={vi.fn()} {...props}/></MemoryRouter>)
it('shows ownership, cautious diagnosis and links the exact correlated session',async()=>{
  mount();expect(await screen.findByText('Ticket ID: C-1')).toBeInTheDocument()
  expect(screen.getByText('Safety evidence requires urgent review.')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Inspect correlated session logs'})).toHaveAttribute('href','/communication?session=MC-1')
  expect(screen.getByText(/No email, notification or external ticket is sent/)).toBeInTheDocument()
})
it('saves an explained escalation with optimistic version and human owner',async()=>{
  const changed=vi.fn();mount({onChange:changed});await screen.findByText('Ticket ID: C-1')
  await userEvent.click(screen.getByText('Update assignment or ticket state'))
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Ticket state'}),'escalated')
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Assigned team'}),'vehicle_specialists')
  await userEvent.type(screen.getByRole('textbox',{name:'Assignment / escalation reason'}),'Safety logs require specialist review')
  await userEvent.click(screen.getByRole('button',{name:'Save ticket decision'}))
  await waitFor(()=>expect(api.updateTicket).toHaveBeenCalledWith('C-1',expect.objectContaining({version:2,state:'escalated',assigned_team:'vehicle_specialists',reason:'Safety logs require specialist review'})))
  expect(changed).toHaveBeenCalled()
})
it('preserves the ticket and exposes a failed update for retry',async()=>{
  api.updateTicket.mockRejectedValue(new Error('Ticket changed; reload before applying an override.'))
  mount();await screen.findByText('Ticket ID: C-1')
  await userEvent.click(screen.getByText('Update assignment or ticket state'))
  await userEvent.type(screen.getByRole('textbox',{name:'Assignment / escalation reason'}),'Reviewed current evidence')
  await userEvent.click(screen.getByRole('button',{name:'Save ticket decision'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Ticket changed')
})
it('lists cited event IDs, affected components and requested missing evidence',async()=>{
  const detailed={...ticket,decision:{...ticket.decision,affected_components:['network','charger'],requires_human_review:true,policy_version:'support-policy-v1',
    evidence:[{event_id:'EVT-9',timestamp:'2026-11-04T01:02:03Z',component_type:'charger'}],missing_evidence:['Obtain the vehicle-side log for the stop request.']}}
  mount({ticket:detailed});await screen.findByText('Ticket ID: C-1')
  expect(screen.getByText('EVT-9')).toBeInTheDocument()
  expect(screen.getByText(/Network, Charger/)).toBeInTheDocument()
  expect(screen.getByText(/Human review required/)).toBeInTheDocument()
  expect(screen.getByText('Obtain the vehicle-side log for the stop request.')).toBeInTheDocument()
})
it('says no component is asserted when no log events are cited',async()=>{
  mount();await screen.findByText('Ticket ID: C-1')
  expect(screen.getByText(/No supporting log events are cited/)).toBeInTheDocument()
})
