import { NavLink, useNavigate, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard', exact: true },
  { to: '/projects', label: 'Projects' },
  { to: '/team', label: 'Team' },
  { to: '/invoices', label: 'Invoices' },
]

export default function Layout() {
  const navigate = useNavigate()

  function logout() {
    localStorage.removeItem('token')
    navigate('/login')
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'system-ui, sans-serif' }}>
      <aside style={{ width: '220px', background: '#1e3a5f', color: '#fff', display: 'flex', flexDirection: 'column', padding: '1.5rem 0' }}>
        <div style={{ padding: '0 1.5rem', marginBottom: '2rem' }}>
          <h1 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0 }}>ContractorHub</h1>
        </div>
        <nav style={{ flex: 1 }}>
          {navItems.map(({ to, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              style={({ isActive }) => ({
                display: 'block',
                padding: '0.6rem 1.5rem',
                color: isActive ? '#fff' : '#93c5fd',
                background: isActive ? 'rgba(255,255,255,0.1)' : 'transparent',
                textDecoration: 'none',
                fontWeight: isActive ? 600 : 400,
              })}
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <button onClick={logout} style={{ margin: '0 1rem', padding: '0.5rem', background: 'rgba(255,255,255,0.1)', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>
          Sign Out
        </button>
      </aside>
      <main style={{ flex: 1, background: '#f9fafb', padding: '2rem', overflowY: 'auto' }}>
        <Outlet />
      </main>
    </div>
  )
}
