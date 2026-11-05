import { NavLink, Route, Routes } from 'react-router-dom'
import { Component, lazy, Suspense, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Spinner } from './components/ui'
import { api } from './api'
import { useAsync } from './hooks'
const Dashboard = lazy(() => import('./pages/Dashboard.jsx'))
const NewCase = lazy(() => import('./pages/NewCase.jsx'))
const Cases = lazy(() => import('./pages/Cases.jsx'))
const CaseDetail = lazy(() => import('./pages/CaseDetail.jsx'))
const Knowledge = lazy(() => import('./pages/Knowledge.jsx'))
const Evaluation = lazy(() => import('./pages/Evaluation.jsx'))
const Reviews = lazy(() => import('./pages/Reviews.jsx'))
const Communication = lazy(() => import('./pages/Communication.jsx'))

class RouteBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return <div className="alert error" role="alert">This page could not be displayed. <button className="btn" onClick={() => window.location.reload()}>Reload application</button></div>
    return this.props.children
  }
}

const NAV = [
  ['/', '📊', 'Dashboard'],
  ['/new', '➕', 'New complaint'],
  ['/cases', '🗂️', 'Support tickets'],
  ['/knowledge', '🧠', 'Knowledge & learning'],
  ['/evaluation', '🧪', 'Evaluation'],
  ['/reviews', '📥', 'Review import'],
  ['/communication', '↔', 'Communication monitoring'],
]

function Health() {
  const { data, error } = useAsync(() => api.health(), [])
  const ok = data?.status === 'ok'
  return (
    <div className="side-foot">
      <span className={`dot ${error ? 'bad' : ok ? 'ok' : ''}`} />
      {error ? 'Backend offline' : ok ? 'API online' : 'Checking…'}
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  useEffect(() => setMenuOpen(false), [location.pathname])
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand-row"><div className="brand"><div className="logo">⚡</div><div>EV Charging<br />Support Tickets</div></div>
          <button className="mobile-menu-toggle" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? 'Close' : 'Menu'}</button></div>
        <nav id="main-navigation" className={`nav${menuOpen ? ' is-open' : ''}`} aria-label="Main navigation">
          {NAV.map(([to, icon, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span aria-hidden="true">{icon}</span>{label}
            </NavLink>
          ))}
        </nav>
        <Health />
      </aside>
      <main className="main">
        <RouteBoundary key={location.pathname}><Suspense fallback={<Spinner />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewCase />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:caseId" element={<CaseDetail />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/reviews" element={<Reviews />} />
          <Route path="/communication" element={<Communication />} />
          <Route path="*" element={<div className="empty">Page not found.</div>} />
        </Routes>
        </Suspense></RouteBoundary>
      </main>
    </div>
  )
}
