import { Link } from 'react-router-dom'
import { Badge } from './ui'
import { diagnosisTitle, diagnosisTone, ORIGIN_TONE, fmtDate, titleCase } from '../format'

export default function TicketList({ items, categories = [] }) {
  return <>
    <div className="table-wrap ticket-table"><table>
      <thead><tr><th>Ticket</th><th>Complaint</th><th>Priority / owner</th><th>Diagnosis</th><th>Ticket state</th><th>Origin</th><th>Created</th></tr></thead>
      <tbody>{items.map(ticket => <tr key={ticket.case_id}>
        <td><Link to={`/cases/${ticket.case_id}`} className="mono">{ticket.case_id}</Link></td>
        <td className="clip">{ticket.complaint_text_redacted}</td>
        <td>{ticket.ticket?.priority || 'Pending'}<div className="small muted">{titleCase(ticket.ticket?.assigned_team || 'triage')}</div></td>
        <td><Badge tone={diagnosisTone(ticket.diagnosis)}>{diagnosisTitle(ticket.diagnosis, categories)}</Badge></td>
        <td>{titleCase(ticket.ticket?.state || ticket.status)}</td>
        <td><Badge tone={ORIGIN_TONE[ticket.data_origin]}>{titleCase(ticket.data_origin)}</Badge></td>
        <td className="small muted">{fmtDate(ticket.created_at)}</td>
      </tr>)}</tbody>
    </table></div>
    <div className="mobile-ticket-list">{items.map(ticket => <article className="card ticket-card" key={ticket.case_id}>
      <Link to={`/cases/${ticket.case_id}`} className="mono ticket-link">{ticket.case_id}</Link>
      <div className="chips"><Badge tone={ticket.ticket?.priority === 'P0' ? 'red' : ticket.ticket?.priority === 'P1' ? 'amber' : 'blue'}>{ticket.ticket?.priority || 'Pending'}</Badge>
        <Badge>{titleCase(ticket.ticket?.state || ticket.status)}</Badge><Badge tone={ORIGIN_TONE[ticket.data_origin]}>{titleCase(ticket.data_origin)}</Badge></div>
      <p className="ticket-excerpt">{ticket.complaint_text_redacted}</p>
      <div><Badge tone={diagnosisTone(ticket.diagnosis)}>{diagnosisTitle(ticket.diagnosis, categories)}</Badge></div>
      <p className="small muted">Owner: {titleCase(ticket.ticket?.assigned_team || 'triage')}<br />{fmtDate(ticket.created_at)}</p>
    </article>)}</div>
  </>
}
