import { useEffect, useState } from 'react'
import api from '../api/client'

const EMPTY = { name: '', client_name: '', contract_number: '', contract_amount: '', status: 'bidding', start_date: '', end_date: '', description: '' }

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    const res = await api.get('/projects/')
    setProjects(res.data.results ?? res.data)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.post('/projects/', form)
      setForm(EMPTY)
      setShowForm(false)
      load()
    } catch (err) {
      setError(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to create project.')
    } finally {
      setSaving(false)
    }
  }

  function handleChange(e) {
    setForm(f => ({ ...f, [e.target.name]: e.target.value }))
  }

  if (loading) return <p>Loading…</p>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={headingStyle}>Projects</h2>
        <button style={btnStyle} onClick={() => setShowForm(s => !s)}>
          {showForm ? 'Cancel' : '+ New Project'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} style={cardStyle}>
          <h3 style={{ marginBottom: '1rem', fontWeight: 600 }}>New Project</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <Field label="Project Name *" name="name" value={form.name} onChange={handleChange} required />
            <Field label="Client Name *" name="client_name" value={form.client_name} onChange={handleChange} required />
            <Field label="Contract Number" name="contract_number" value={form.contract_number} onChange={handleChange} />
            <Field label="Contract Amount" name="contract_amount" type="number" value={form.contract_amount} onChange={handleChange} />
            <Field label="Start Date" name="start_date" type="date" value={form.start_date} onChange={handleChange} />
            <Field label="End Date" name="end_date" type="date" value={form.end_date} onChange={handleChange} />
            <div>
              <label style={labelStyle}>Status</label>
              <select name="status" value={form.status} onChange={handleChange} style={inputStyle}>
                {['bidding','awarded','active','on_hold','completed','cancelled'].map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <Field label="Description" name="description" value={form.description} onChange={handleChange} />
          </div>
          {error && <p style={{ color: '#ef4444', marginTop: '0.5rem' }}>{error}</p>}
          <button style={{ ...btnStyle, marginTop: '1rem' }} type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Create Project'}
          </button>
        </form>
      )}

      {projects.length === 0 ? (
        <p style={{ color: '#6b7280' }}>No projects yet. Create your first one above.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr style={{ background: '#f3f4f6' }}>
              {['Name', 'Client', 'Status', 'Contract Value', 'Start', 'End'].map(h => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {projects.map(p => (
              <tr key={p.id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                <td style={tdStyle}>{p.name}</td>
                <td style={tdStyle}>{p.client_name}</td>
                <td style={tdStyle}>{p.status}</td>
                <td style={tdStyle}>${Number(p.contract_amount).toLocaleString()}</td>
                <td style={tdStyle}>{p.start_date ?? '—'}</td>
                <td style={tdStyle}>{p.end_date ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function Field({ label, name, type = 'text', value, onChange, required }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input style={inputStyle} name={name} type={type} value={value} onChange={onChange} required={required} />
    </div>
  )
}

const headingStyle = { fontSize: '1.4rem', fontWeight: 700, margin: 0 }
const cardStyle = { background: '#fff', borderRadius: '8px', padding: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.08)', marginBottom: '1.5rem' }
const tableStyle = { width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
const thStyle = { padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem', fontWeight: 600, color: '#374151', background: '#f3f4f6' }
const tdStyle = { padding: '0.75rem 1rem', fontSize: '0.9rem' }
const labelStyle = { display: 'block', marginBottom: '0.25rem', fontSize: '0.85rem', fontWeight: 500 }
const inputStyle = { width: '100%', padding: '0.45rem 0.75rem', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '0.95rem', boxSizing: 'border-box' }
const btnStyle = { padding: '0.5rem 1.25rem', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }
