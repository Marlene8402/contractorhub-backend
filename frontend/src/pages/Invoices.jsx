import { useEffect, useState } from 'react'
import api from '../api/client'

export default function Invoices() {
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/invoices/').then(res => {
      setInvoices(res.data.results ?? res.data)
      setLoading(false)
    })
  }, [])

  if (loading) return <p>Loading…</p>

  const statusColors = {
    draft: '#f3f4f6', pending: '#fef9c3', sent: '#dbeafe',
    paid: '#dcfce7', overdue: '#fee2e2',
  }

  return (
    <div>
      <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '1.5rem' }}>Invoices</h2>
      {invoices.length === 0 ? (
        <p style={{ color: '#6b7280' }}>No invoices yet. Create a project first, then add invoices.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr style={{ background: '#f3f4f6' }}>
              {['Invoice #', 'Project', 'Amount', 'Status', 'Due Date', 'Paid Date'].map(h => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {invoices.map(inv => (
              <tr key={inv.id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                <td style={tdStyle}>{inv.invoice_number}</td>
                <td style={tdStyle}>{inv.project}</td>
                <td style={tdStyle}>${Number(inv.amount).toLocaleString()}</td>
                <td style={tdStyle}>
                  <span style={{ background: statusColors[inv.status] ?? '#f3f4f6', padding: '2px 8px', borderRadius: '12px', fontSize: '0.78rem', fontWeight: 500 }}>
                    {inv.status}
                  </span>
                </td>
                <td style={tdStyle}>{inv.due_date ?? '—'}</td>
                <td style={tdStyle}>{inv.paid_date ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

const tableStyle = { width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
const thStyle = { padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem', fontWeight: 600, color: '#374151' }
const tdStyle = { padding: '0.75rem 1rem', fontSize: '0.9rem' }
