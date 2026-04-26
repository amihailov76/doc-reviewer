import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { DocumentProvider } from './context/DocumentContext'
import EvaluationPage from './pages/EvaluationPage'
import SnapshotsPage from './pages/SnapshotsPage'
import SettingsPage from './pages/SettingsPage'
import ProjectsPage from './pages/ProjectsPage'
import ProjectPage from './pages/ProjectPage'
import './App.css'

const buildDate = typeof __BUILD_DATE__ !== 'undefined' && __BUILD_DATE__
  ? `Обновлено ${__BUILD_DATE__}`
  : 'dev build'

const NAV_ITEMS = [
  { to: '/projects', label: '📁 Проекты' },
  { to: '/evaluation', label: '🔍 Оценка' },
  { to: '/snapshots', label: '📸 Сравнение результатов' },
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
            <div className="sidebar-footer">{buildDate}</div>
          </aside>

          <main className="main-content">
            <Routes>
              <Route path="/" element={<Navigate to="/projects" replace />} />
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/projects/:id" element={<ProjectPage />} />
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
