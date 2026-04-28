import { useEffect, useState } from 'react'
import api from '../api/client'

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function load() {
      try {
        const [summaryRes, projectsRes] = await Promise.all([
          api.get('/projects/summary/'),
          api.get('/projects/active_projects/'),
        ])
        setSummary(summaryRes.data)
        setProjects(projectsRes.data.results ?? projectsRes.data)
      } catch {
        setError('Failed to load dashboard data.')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return <p>Loading…</p>
  if (error) return <p style={{ color: '#ef4444' }}>{error}</p>

  return (
    <div>
      <h2 style={headingStyle}>Dashboard</h2>

      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
          <StatCard label="Total Projects" value={summary.total_projects} />
          <StatCard label="Active Projects" value={summary.active_projects} />
          <StatCard label="Completed" value={summary.completed_projects} />
          <StatCard label="Total Contract Value" value={`$${Number(summary.total_contract_value).toLocaleString()}`} />
        </div>
      )}

      <h3 style={{ marginBottom: '1rem', fontWeight: 600 }}>Active Projects</h3>
      {projects.length === 0 ? (
        <p style={{ color: '#6b7280' }}>No active projects yet. <a href="/projects">Create one →</a></p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr style={{ background: '#f3f4f6' }}>
              {['Project', 'Client', 'Status', 'Contract Value', 'End Date'].map(h => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {projects.map(p => (
              <tr key={p.id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                <td style={tdStyle}>{p.name}</td>
                <td style={tdStyle}>{p.client_name}</td>
                <td style={tdStyle}><StatusBadge status={p.status} /></td>
                <td style={tdStyle}>${Number(p.contract_amount).toLocaleString()}</td>
                <td style={tdStyle}>{p.end_date ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div style={{ background: '#fff', borderRadius: '8px', padding: '1.25rem', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <p style={{ color: '#6b7280', fontSize: '0.8rem', marginBottom: '0.4rem' }}>{label}</p>
      <p style={{ fontSize: '1.6rem', fontWeight: 700, margin: 0 }}>{value}</p>
    </div>
  )
}

function StatusBadge({ status }) {
  const colors = {
    active: '#dcfce7', awarded: '#dbeafe', bidding: '#fef9c3',
    on_hold: '#fee2e2', completed: '#f3f4f6', cancelled: '#f3f4f6',
  }
  return (
    <span style={{ background: colors[status] ?? '#f3f4f6', padding: '2px 8px', borderRadius: '12px', fontSize: '0.78rem', fontWeight: 500 }}>
      {status}
    </span>
  )
}

const headingStyle = { fontSize: '1.4rem', fontWeight: 700, marginBottom: '1.5rem' }
const tableStyle = { width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
const thStyle = { padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem', fontWeight: 600, color: '#374151' }
const tdStyle = { padding: '0.75rem 1rem', fontSize: '0.9rem' }
