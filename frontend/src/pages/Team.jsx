import { useEffect, useState } from 'react'
import api from '../api/client'

const EMPTY = { first_name: '', last_name: '', email: '', phone: '', role: '' }

export default function Team() {
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    const res = await api.get('/team-members/')
    setMembers(res.data.results ?? res.data)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.post('/team-members/', form)
      setForm(EMPTY)
      setShowForm(false)
      load()
    } catch (err) {
      setError(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to add team member.')
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
        <h2 style={headingStyle}>Team Members</h2>
        <button style={btnStyle} onClick={() => setShowForm(s => !s)}>
          {showForm ? 'Cancel' : '+ Add Member'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} style={cardStyle}>
          <h3 style={{ marginBottom: '1rem', fontWeight: 600 }}>New Team Member</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <Field label="First Name *" name="first_name" value={form.first_name} onChange={handleChange} required />
            <Field label="Last Name *" name="last_name" value={form.last_name} onChange={handleChange} required />
            <Field label="Email" name="email" type="email" value={form.email} onChange={handleChange} />
            <Field label="Phone" name="phone" value={form.phone} onChange={handleChange} />
            <Field label="Role" name="role" value={form.role} onChange={handleChange} />
          </div>
          {error && <p style={{ color: '#ef4444', marginTop: '0.5rem' }}>{error}</p>}
          <button style={{ ...btnStyle, marginTop: '1rem' }} type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Add Member'}
          </button>
        </form>
      )}

      {members.length === 0 ? (
        <p style={{ color: '#6b7280' }}>No team members yet.</p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1rem' }}>
          {members.map(m => (
            <div key={m.id} style={cardStyle}>
              <p style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '0.25rem' }}>{m.first_name} {m.last_name}</p>
              <p style={{ color: '#6b7280', fontSize: '0.85rem', marginBottom: '0.5rem' }}>{m.role || 'No role set'}</p>
              {m.email && <p style={{ fontSize: '0.85rem' }}>✉ {m.email}</p>}
              {m.phone && <p style={{ fontSize: '0.85rem' }}>📞 {m.phone}</p>}
              <span style={{ display: 'inline-block', marginTop: '0.5rem', fontSize: '0.75rem', padding: '2px 8px', borderRadius: '12px', background: m.is_active ? '#dcfce7' : '#fee2e2' }}>
                {m.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
          ))}
        </div>
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
const labelStyle = { display: 'block', marginBottom: '0.25rem', fontSize: '0.85rem', fontWeight: 500 }
const inputStyle = { width: '100%', padding: '0.45rem 0.75rem', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '0.95rem', boxSizing: 'border-box' }
const btnStyle = { padding: '0.5rem 1.25rem', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }
