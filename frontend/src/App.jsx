import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { DocumentProvider } from './context/DocumentContext'
import EvaluationPage from './pages/EvaluationPage'
import SnapshotsPage from './pages/SnapshotsPage'
import SettingsPage from './pages/SettingsPage'
import './App.css'

const NAV_ITEMS = [
  { to: '/evaluation', label: '🔍 Оценка' },
  { to: '/snapshots', label: '📸 Снимки' },
  { to: '/settings', label: '⚙️ Настройки' },
]

export default function App() {
  return (
    <DocumentProvider>
      <BrowserRouter>
        <div className="app-layout">
          <aside className="sidebar">
            <div className="sidebar-logo">
              <span className="sidebar-logo-icon">🔎</span>
              <span className="sidebar-logo-text">doc-reviewer</span>
            </div>
            <nav className="sidebar-nav">
              {NAV_ITEMS.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => 'nav-item' + (isActive ? ' nav-item--active' : '')}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <div className="sidebar-footer">MaxPatrol SIEM</div>
          </aside>

          <main className="main-content">
            <Routes>
              <Route path="/" element={<Navigate to="/evaluation" replace />} />
              <Route path="/evaluation" element={<EvaluationPage />} />
              <Route path="/snapshots" element={<SnapshotsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </DocumentProvider>
  )
}
