import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function ProjectsPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { loadProjects() }, [])

  async function loadProjects() {
    setLoading(true)
    try {
      const res = await fetch('/api/projects/')
      const data = await res.json()
      setProjects(data)
    } catch { setError('Не удалось загрузить проекты') }
    finally { setLoading(false) }
  }

  async function createProject() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try {
      const res = await fetch('/api/projects/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка создания'); return }
      setProjects(prev => [data, ...prev])
      setNewName('')
      setShowForm(false)
      navigate(`/projects/${data.id}`)
    } catch { setError('Не удалось создать проект') }
    finally { setCreating(false) }
  }

  async function deleteProject(id, e) {
    e.stopPropagation()
    if (!confirm('Удалить проект? Документы останутся в системе без привязки.')) return
    await fetch(`/api/projects/${id}`, { method: 'DELETE' })
    setProjects(prev => prev.filter(p => p.id !== id))
  }

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Проекты</h1>
        <button className="btn btn-primary" onClick={() => { setShowForm(v => !v); setNewName('') }}>
          {showForm ? 'Отмена' : '+ Новый проект'}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 10 }}>
            <input
              className="snap-name-input"
              style={{ flex: 1 }}
              placeholder="Название проекта"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !creating && createProject()}
              autoFocus
            />
            <button className="btn btn-primary" onClick={createProject} disabled={creating || !newName.trim()}>
              {creating ? 'Создание…' : 'Создать'}
            </button>
          </div>
        </div>
      )}

      {error && <div className="alert alert-error">⚠️ {error}</div>}

      {loading ? (
        <div style={{ color: 'var(--color-text-secondary)', padding: 24 }}>Загрузка…</div>
      ) : projects.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '40px 24px', color: 'var(--color-text-secondary)' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📁</div>
          <p>Проектов пока нет. Создайте первый проект и добавьте в него документы для оценки.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {projects.map(p => (
            <div
              key={p.id}
              className="card"
              style={{ cursor: 'pointer', marginBottom: 0, display: 'flex', alignItems: 'center', gap: 16 }}
              onClick={() => navigate(`/projects/${p.id}`)}
            >
              <div style={{ fontSize: 24 }}>📁</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{p.name}</div>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2, display: 'flex', gap: 14 }}>
                  <span>📄 {p.doc_count} {docLabel(p.doc_count)}</span>
                  <span>{p.has_context ? '✅ Контекст задан' : '⬜ Контекст не задан'}</span>
                  {p.created_at && <span>Создан {formatDate(p.created_at)}</span>}
                </div>
              </div>
              <button
                className="btn btn-secondary btn-sm"
                style={{ color: 'var(--color-red)', borderColor: 'var(--color-red)', flexShrink: 0 }}
                onClick={e => deleteProject(p.id, e)}
              >
                Удалить
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function docLabel(n) {
  if (n % 10 === 1 && n % 100 !== 11) return 'документ'
  if ([2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100)) return 'документа'
  return 'документов'
}

function formatDate(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}
