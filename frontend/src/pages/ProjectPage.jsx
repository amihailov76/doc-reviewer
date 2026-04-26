import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useDocument } from '../context/DocumentContext'

const ALLOWED_EXT = ['.pdf', '.docx', '.md', '.txt']
const COLOR_EMOJI = { green: '🟢', yellow: '🟡', orange: '🟠', red: '🔴' }

export default function ProjectPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const fileInputRef = useRef(null)
  const { setCurrentDoc, setSections, setSelectedSection, setProgress, setSummary, setHasEvaluations } = useDocument()

  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Редактирование названия
  const [editingName, setEditingName] = useState(false)
  const [nameValue, setNameValue] = useState('')

  // Редактирование контекста
  const [editingContext, setEditingContext] = useState(false)
  const [contextValue, setContextValue] = useState('')
  const [savingContext, setSavingContext] = useState(false)

  // Генерация контекста
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState(null)

  // Загрузка документа в проект
  const [uploadTab, setUploadTab] = useState('file') // 'file' | 'url'
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [urlInput, setUrlInput] = useState('')

  useEffect(() => { loadProject() }, [id])

  async function loadProject() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/projects/${id}`)
      if (!res.ok) { setError('Проект не найден'); return }
      const data = await res.json()
      setProject(data)
      setNameValue(data.name)
      setContextValue(data.product_context || '')
    } catch { setError('Не удалось загрузить проект') }
    finally { setLoading(false) }
  }

  // ── Название ──────────────────────────────────────────────────────────────

  async function saveName() {
    const name = nameValue.trim()
    if (!name || name === project.name) { setEditingName(false); return }
    const res = await fetch(`/api/projects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (res.ok) {
      setProject(p => ({ ...p, name }))
      setEditingName(false)
    }
  }

  // ── Контекст ──────────────────────────────────────────────────────────────

  async function saveContext() {
    setSavingContext(true)
    const res = await fetch(`/api/projects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_context: contextValue }),
    })
    if (res.ok) {
      setProject(p => ({ ...p, product_context: contextValue, has_context: !!contextValue }))
      setEditingContext(false)
    }
    setSavingContext(false)
  }

  async function generateContext() {
    setGenerating(true)
    setGenError(null)
    try {
      const res = await fetch(`/api/projects/${id}/generate-context`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) {
        setGenError(data.detail?.message || data.detail || 'Ошибка генерации')
        return
      }
      setProject(p => ({
        ...p,
        product_context: data.product_context,
        has_context: true,
        context_generated_at: data.context_generated_at,
      }))
      setContextValue(data.product_context)
      setEditingContext(false)
    } catch { setGenError('Не удалось связаться с сервером') }
    finally { setGenerating(false) }
  }

  // ── Загрузка документа в проект ──────────────────────────────────────────

  async function uploadFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!ALLOWED_EXT.includes(ext)) {
      setUploadError(`Формат «${ext}» не поддерживается`)
      return
    }
    setUploadError(null)
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      // project_id передаётся как query-параметр, а не в FormData
      const res = await fetch(`/api/documents/upload?project_id=${id}`, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) { setUploadError(data.detail || 'Ошибка при загрузке'); return }

      if (data.conflict) {
        const formData2 = new FormData()
        formData2.append('file', file)
        const res2 = await fetch(`/api/documents/upload/replace/${data.existing_id}?project_id=${id}`, { method: 'POST', body: formData2 })
        const data2 = await res2.json()
        if (!res2.ok) { setUploadError(data2.detail || 'Ошибка при замене'); return }
        await loadProject()
        return
      }
      await loadProject()
    } catch { setUploadError('Не удалось связаться с сервером') }
    finally { setUploading(false) }
  }

  async function uploadUrl() {
    const url = urlInput.trim()
    if (!url) { setUploadError('Введите ссылку'); return }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setUploadError('Ссылка должна начинаться с http:// или https://')
      return
    }
    setUploadError(null)
    setUploading(true)
    try {
      const res = await fetch('/api/documents/from-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, project_id: parseInt(id) }),
      })
      const data = await res.json()
      if (!res.ok) { setUploadError(data.detail || 'Ошибка при загрузке страницы'); return }
      setUrlInput('')
      await loadProject()
    } catch { setUploadError('Не удалось связаться с сервером') }
    finally { setUploading(false) }
  }

  // ── Открыть документ в оценке ─────────────────────────────────────────────

  async function openDocument(docId) {
    const res = await fetch(`/api/documents/${docId}/structure`)
    const data = await res.json()
    setCurrentDoc(data.document)
    setSections(data.sections)
    setSelectedSection(null)
    setProgress(null)
    setSummary(null)
    setHasEvaluations(false)
    navigate('/evaluation')
  }

  // ── Удалить документ из проекта (отвязать) ────────────────────────────────

  async function removeFromProject(docId, e) {
    e.stopPropagation()
    if (!confirm('Убрать документ из проекта? Документ останется в системе.')) return
    await fetch(`/api/projects/documents/${docId}/assign`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: null }),
    })
    setProject(p => ({ ...p, documents: p.documents.filter(d => d.id !== docId) }))
  }

  // ── Рендер ────────────────────────────────────────────────────────────────

  if (loading) return <div className="page" style={{ color: 'var(--color-text-secondary)' }}>Загрузка…</div>
  if (error) return <div className="page"><div className="alert alert-error">⚠️ {error}</div></div>

  return (
    <div className="page">

      {/* Хлебные крошки */}
      <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginBottom: 16 }}>
        <Link to="/projects" style={{ color: 'var(--color-primary)', textDecoration: 'none' }}>Проекты</Link>
        {' › '}
        <span>{project.name}</span>
      </div>

      {/* Заголовок */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        {editingName ? (
          <>
            <input
              className="snap-name-input"
              style={{ fontSize: 20, fontWeight: 700, flex: 1, maxWidth: 400 }}
              value={nameValue}
              onChange={e => setNameValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') setEditingName(false) }}
              autoFocus
            />
            <button className="btn btn-primary btn-sm" onClick={saveName}>Сохранить</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setEditingName(false)}>Отмена</button>
          </>
        ) : (
          <>
            <h1 className="page-title" style={{ margin: 0 }}>📁 {project.name}</h1>
            <button className="btn btn-secondary btn-sm" onClick={() => { setEditingName(true); setNameValue(project.name) }}>
              ✏️ Переименовать
            </button>
          </>
        )}
      </div>

      {/* Контекст продукта */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>🧠 Контекст продукта</h2>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={generateContext}
              disabled={generating || project.documents?.length === 0}
            >
              {generating
                ? <><span className="drop-zone__spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Генерация…</>
                : '✨ Сгенерировать'}
            </button>
            {!editingContext && (
              <button className="btn btn-secondary btn-sm" onClick={() => { setEditingContext(true); setContextValue(project.product_context || '') }}>
                ✏️ Редактировать
              </button>
            )}
          </div>
        </div>

        <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', margin: '0 0 14px', lineHeight: 1.6 }}>
          Контекст подставляется в каждый запрос к LLM и помогает оценивать инструкции точнее:
          модель учитывает специфику продукта, его аудиторию и ключевые термины.
        </p>

        {genError && <div className="alert alert-error" style={{ marginBottom: 12 }}>⚠️ {genError}</div>}

        {generating && (
          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', padding: '12px 0' }}>
            Анализируем вводные разделы документов и составляем описание продукта…
          </div>
        )}

        {editingContext ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <textarea
              style={{
                width: '100%', minHeight: 220, padding: '10px 12px',
                border: '1px solid var(--color-border)', borderRadius: 7,
                fontSize: 13, lineHeight: 1.6, resize: 'vertical',
                fontFamily: 'inherit', boxSizing: 'border-box',
              }}
              value={contextValue}
              onChange={e => setContextValue(e.target.value)}
              placeholder="Введите описание продукта: название, аудитория, ключевые термины, компоненты…"
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" onClick={saveContext} disabled={savingContext}>
                {savingContext ? 'Сохранение…' : 'Сохранить'}
              </button>
              <button className="btn btn-secondary" onClick={() => setEditingContext(false)}>Отмена</button>
            </div>
          </div>
        ) : project.product_context ? (
          <>
            <div style={{
              fontSize: 13, lineHeight: 1.7, color: 'var(--color-text)',
              whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto',
              padding: '10px 12px', background: 'var(--color-bg)',
              border: '1px solid var(--color-border)', borderRadius: 7,
            }}>
              {project.product_context}
            </div>
            {project.context_generated_at && (
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 8 }}>
                Сгенерирован {formatDate(project.context_generated_at)} · Используется при оценке всех документов проекта
              </div>
            )}
          </>
        ) : (
          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', padding: '12px 0', lineHeight: 1.6 }}>
            {project.documents?.length === 0 ? (
              <>Контекст формируется автоматически из загруженных документов.
              Сначала добавьте документы в раздел ниже — затем кнопка <strong>Сгенерировать</strong> станет активной.</>
            ) : (
              <>Контекст не задан. Нажмите <strong>Сгенерировать</strong> для автоматического создания из загруженных документов
              или <strong>Редактировать</strong> для ввода вручную.</>
            )}
          </div>
        )}
      </div>

      {/* Документы */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
            📄 Документы ({project.documents?.length || 0})
          </h2>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              className={`btn btn-sm${uploadTab === 'file' ? ' btn-primary' : ' btn-secondary'}`}
              onClick={() => { setUploadTab('file'); setUploadError(null) }}
            >📄 Файл</button>
            <button
              className={`btn btn-sm${uploadTab === 'url' ? ' btn-primary' : ' btn-secondary'}`}
              onClick={() => { setUploadTab('url'); setUploadError(null) }}
            >🔗 По ссылке</button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.md,.txt"
            style={{ display: 'none' }}
            onChange={e => { const f = e.target.files[0]; if (f) uploadFile(f); e.target.value = '' }}
          />
        </div>

        {uploadTab === 'file' && (
          <div style={{ marginBottom: 12 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
              {uploading ? 'Загрузка…' : '+ Выбрать файл'}
            </button>
          </div>
        )}

        {uploadTab === 'url' && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              className="snap-name-input"
              style={{ flex: 1 }}
              type="url"
              placeholder="https://help.example.com/..."
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !uploading && uploadUrl()}
              disabled={uploading}
            />
            <button className="btn btn-primary btn-sm" onClick={uploadUrl} disabled={uploading || !urlInput.trim()}>
              {uploading ? 'Загрузка…' : 'Загрузить'}
            </button>
          </div>
        )}

        {uploadError && <div className="alert alert-error" style={{ marginBottom: 12 }}>⚠️ {uploadError}</div>}

        {!project.documents || project.documents.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--color-text-secondary)', fontSize: 13 }}>
            Документов нет. Загрузите PDF, DOCX, MD или TXT.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {project.documents.map(doc => (
              <div
                key={doc.id}
                onClick={() => openDocument(doc.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px',
                  border: '1px solid var(--color-border)', borderRadius: 8,
                  cursor: 'pointer', background: 'var(--color-bg)',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#f0f4ff'}
                onMouseLeave={e => e.currentTarget.style.background = 'var(--color-bg)'}
              >
                <span style={{ fontSize: 20 }}>{fileIcon(doc.file_type)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {doc.filename}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2, display: 'flex', gap: 12 }}>
                    {doc.doc_type && <span>{doc.doc_type}</span>}
                    <span>{doc.total_instructions} инструкций</span>
                    {doc.evaluated_count > 0 && (
                      <span style={{ color: 'var(--color-green)' }}>✓ оценено {doc.evaluated_count}</span>
                    )}
                    {doc.last_evaluated_at && <span>последняя оценка {formatDate(doc.last_evaluated_at)}</span>}
                  </div>
                </div>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={e => removeFromProject(doc.id, e)}
                  style={{ fontSize: 12, flexShrink: 0 }}
                >
                  Убрать
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function fileIcon(type) {
  return { pdf: '📕', docx: '📘', md: '📝', txt: '📄', web: '🌐' }[type] || '📄'
}

function formatDate(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}
