import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import PaymentPanel from './PaymentPanel'

vi.mock('../api', () => ({api:Object.fromEntries(['getPayment','submitPayment','reviewPayment','paymentProof'].map(k => [k,vi.fn()]))}))
const reviewers = [
  {reviewer_id:'rev-payment-001',name:'Payment reviewer',role:'payment_reviewer',active:true},
  {reviewer_id:'rev-inactive',name:'Inactive payment reviewer',role:'payment_reviewer',active:false},
  {reviewer_id:'rev-001',name:'Diagnosis reviewer',role:'diagnosis_reviewer',active:true},
]
const initial = {status:'not_submitted',version:0,submission:null,submissions:[],history:[],scope:'Manual review only; no bank or gateway lookup.'}
const submission = {submission_id:'PS-1',transaction_reference:'UPI-123456789012',submitted_at:'2026-11-05T00:00:00Z',source:'customer',proof:null}
const pending = {...initial,status:'submitted',version:1,submission,submissions:[submission]}
const reviewing = {...pending,status:'under_review',version:2,reviewer_id:'rev-payment-001',reason:'Manual review started',reviewed_at:'2026-11-05T00:01:00Z'}
const mount = () => render(<PaymentPanel caseId="C-test" reviewers={reviewers} />)

beforeEach(() => {vi.resetAllMocks();api.getPayment.mockResolvedValue(initial)})

it('shows loading and an honest empty state',async () => {
  mount()
  expect(screen.getByRole('status',{name:'Loading'})).toBeInTheDocument()
  expect(await screen.findByText('Not submitted',{exact:true})).toBeInTheDocument()
  expect(screen.getByText('No payment proof has been submitted for this ticket.')).toBeInTheDocument()
  expect(screen.queryByText('Paid',{exact:true})).not.toBeInTheDocument()
})

it('submits a reference as a versioned submission without verifying',async () => {
  api.submitPayment.mockResolvedValue(pending)
  mount()
  await userEvent.type(await screen.findByRole('textbox',{name:'Transaction reference'}),'UPI-123456789012')
  await userEvent.click(screen.getByRole('button',{name:'Submit payment information'}))
  expect(await screen.findByText('Submitted - not verified')).toBeInTheDocument()
  const [id,form] = api.submitPayment.mock.calls[0]
  expect(id).toBe('C-test')
  expect(form.get('version')).toBe('0')
  expect(form.get('transaction_reference')).toBe(submission.transaction_reference)
  expect([...form.keys()]).toEqual(['version','transaction_reference'])
  expect(api.reviewPayment).not.toHaveBeenCalled()
  expect(screen.queryByRole('button',{name:'Verify payment manually'})).not.toBeInTheDocument()
})

it('uploads screenshot-only proof and disables the form while submitting',async () => {
  let finish
  api.submitPayment.mockImplementation(() => new Promise(resolve => {finish=resolve}))
  mount()
  const file = new File(['image bytes'],'receipt.png',{type:'image/png'})
  await userEvent.upload(await screen.findByLabelText('Payment screenshot (optional)'),file)
  await userEvent.click(screen.getByRole('button',{name:'Submit payment information'}))
  expect(screen.getByRole('button',{name:'Submitting...'})).toBeDisabled()
  expect(api.submitPayment.mock.calls[0][1].get('proof')).toBe(file)
  finish({...pending,submission:{...submission,transaction_reference:null,proof:{name:'receipt.png',size:file.size}}})
  expect(await screen.findByText('Submitted - not verified')).toBeInTheDocument()
  expect(screen.getByText(/receipt.png/)).toBeInTheDocument()
})

it('validates missing proof and invalid references before calling the API',async () => {
  mount()
  await userEvent.click(await screen.findByRole('button',{name:'Submit payment information'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Provide a transaction reference')
  await userEvent.type(screen.getByRole('textbox',{name:'Transaction reference'}),'bad ref')
  await userEvent.click(screen.getByRole('button',{name:'Submit payment information'}))
  expect(screen.getByRole('alert')).toHaveTextContent('6-100')
  expect(api.submitPayment).not.toHaveBeenCalled()
})

it('requires the dedicated local reviewer role, then starts review and verifies with a reason',async () => {
  api.getPayment.mockResolvedValue(pending)
  api.reviewPayment.mockResolvedValueOnce(reviewing).mockResolvedValueOnce({...reviewing,status:'verified',version:3,reason:'Manual records reconciled'})
  mount()
  await screen.findByText('Submitted - not verified')
  await userEvent.click(screen.getByText('Manual reviewer actions'))
  expect(screen.queryByRole('option',{name:/Diagnosis reviewer/})).not.toBeInTheDocument()
  expect(screen.queryByRole('option',{name:/Inactive payment reviewer/})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Start manual review'})).toBeDisabled()
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Payment reviewer'}),'rev-payment-001')
  await userEvent.type(screen.getByRole('textbox',{name:'Manual review reason'}),'Manual review started')
  await userEvent.click(screen.getByRole('button',{name:'Start manual review'}))
  expect(await screen.findByText('Under manual review')).toBeInTheDocument()
  expect(api.reviewPayment).toHaveBeenNthCalledWith(1,'C-test',{version:1,decision:'under_review',reason:'Manual review started'},'rev-payment-001')
  await userEvent.type(screen.getByRole('textbox',{name:'Manual review reason'}),'Manual records reconciled')
  await userEvent.click(screen.getByRole('button',{name:'Verify payment manually'}))
  expect(await screen.findByText('Verified by manual reviewer')).toBeInTheDocument()
  expect(api.reviewPayment).toHaveBeenNthCalledWith(2,'C-test',{version:2,decision:'verified',reason:'Manual records reconciled'},'rev-payment-001')
})

it('shows a rejected decision, reviewer identity and reason and allows correction',async () => {
  api.getPayment.mockResolvedValue(reviewing)
  api.reviewPayment.mockResolvedValue({...reviewing,status:'rejected',version:3,reason:'Reference does not match the supplied receipt.'})
  mount()
  await screen.findByText('Under manual review')
  await userEvent.click(screen.getByText('Manual reviewer actions'))
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Payment reviewer'}),'rev-payment-001')
  await userEvent.type(screen.getByRole('textbox',{name:'Manual review reason'}),'Reference does not match the supplied receipt.')
  await userEvent.click(screen.getByRole('button',{name:'Reject payment'}))
  expect(await screen.findByText('Rejected',{exact:true})).toBeInTheDocument()
  expect(screen.getByText(/Rejection reason: Reference does not match/)).toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'Submit corrected payment proof'})).toBeInTheDocument()
})

it.each([
  ['stale_payment','Payment information changed. Reload before trying again.'],
  ['payment_reviewer_required','An active local payment reviewer is required.'],
])('preserves a %s error and reloads server state',async (code,message) => {
  api.getPayment.mockResolvedValue(pending)
  api.reviewPayment.mockRejectedValue(Object.assign(new Error(message),{code}))
  mount()
  await screen.findByText('Submitted - not verified')
  await userEvent.click(screen.getByText('Manual reviewer actions'))
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Payment reviewer'}),'rev-payment-001')
  await userEvent.type(screen.getByRole('textbox',{name:'Manual review reason'}),'Manual review started')
  await userEvent.click(screen.getByRole('button',{name:'Start manual review'}))
  expect(await screen.findByRole('alert')).toHaveTextContent(message)
  expect(screen.getByText('Submitted - not verified')).toBeInTheDocument()
  api.getPayment.mockResolvedValue(reviewing)
  await userEvent.click(screen.getByRole('button',{name:'Retry'}))
  expect(await screen.findByText('Under manual review')).toBeInTheDocument()
})

it('renders saved audit history and a legacy claim without implying verification',async () => {
  api.getPayment.mockResolvedValue({...reviewing,reviewer_id:null,
    submission:{...submission,source:'legacy_claim'},history:[{id:1,action:'payment_legacy_review_required',actor:'system',
      reason:'Historical claim retained; manual review required.',created_at:'2026-11-05T00:01:00Z',before:{legacy:'Paid'},after:{status:'under_review'}}]})
  mount()
  expect(await screen.findByText(/Historical payment claim retained/)).toBeInTheDocument()
  await userEvent.click(screen.getByText('Payment submission and review history (1)'))
  expect(screen.getByText('Historical claim retained; manual review required.')).toBeVisible()
  expect(screen.getByText(/system/)).toBeVisible()
  expect(screen.queryByText('Verified by manual reviewer')).not.toBeInTheDocument()
})

it('shows API failures with a retry action',async () => {
  api.getPayment.mockRejectedValue(new Error('Payment details could not be loaded.'))
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Payment details could not be loaded.')
  expect(screen.getByRole('button',{name:'Retry'})).toBeInTheDocument()
})
