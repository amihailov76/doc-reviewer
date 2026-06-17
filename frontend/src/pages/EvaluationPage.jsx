import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import DocumentTree from '../components/DocumentTree'
import { useDocument } from '../context/DocumentContext'
import '../styles/DocumentPage.css'
import '../styles/ResultsPage.css'
import '../styles/EvaluationPage.css'

const ALLOWED_EXT = ['.pdf', '.docx', '.md', '.txt']
const COLOR_EMOJI = { green: '🟢', yellow: '🟡', orange: '🟠', red: '🔴' }
const COLOR_LABEL = { green: 'Хорошо', yellow: 'Замечания', orange: 'Проблемы', red: 'Критично' }
const COLOR_RULE = {
  green:  'Нет ошибок, не более одного замечания',
  yellow: 'Есть замечания, не более одной ошибки',
  orange: '2–3 критических ошибки',
  red:    '4 и более критических ошибки',
}

export default function EvaluationPage() {
  const fileInputRef = useRef(null)
  const navigate = useNavigate()
  const {
    currentDoc: doc, setCurrentDoc: setDoc,
    sections, setSections,
    selectedSection, setSelectedSection,
    progress, setProgress,
    summary, setSummary,
    hasEvaluations, setHasEvaluations,
    criteriaLabels,
    clearDocument,
  } = useDocument()

  const [projects, setProjects] = useState([])          // все проекты для селектора
  const [docProject, setDocProject] = useState(null)    // объект текущего проекта
  const [savingProject, setSavingProject] = useState(false)

  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [running, setRunning] = useState(false)
  const [evalError, setEvalError] = useState(null)
  const [integral, setIntegral] = useState(null)   // интегральная оценка документа
  const [showScaleInfo, setShowScaleInfo] = useState(false)
  const [showFeedback, setShowFeedback] = useState(false)
  const [statusModal, setStatusModal] = useState(null)  // 'green' | 'yellow' | 'orange' | 'red' | null
  const [uploadTab, setUploadTab] = useState('file') // 'file' | 'url'
  const [urlInput, setUrlInput] = useState('')
  const [addUrlInput, setAddUrlInput] = useState('')
  const [addingUrl, setAddingUrl] = useState(false)
  const [addUrlError, setAddUrlError] = useState(null)
  const [showAddUrl, setShowAddUrl] = useState(false)
  const [addedUrls, setAddedUrls] = useState([]) // список добавленных URL

  async function uploadUrl() {
    const url = urlInput.trim()
    if (!url) { setUploadError('Введите ссылку'); return }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setUploadError('Ссылка должна начинаться с http:// или https://')
      return
    }
    setUploadError(null); setUploading(true)
    try {
      const res = await fetch('/api/documents/from-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      const data = await res.json()
      if (!res.ok) { setUploadError(data.detail || 'Ошибка при загрузке страницы'); return }
      setAddedUrls([url])
      await loadDocument(data.id)
    } catch { setUploadError('Не удалось связаться с сервером') }
    finally { setUploading(false) }
  }

  async function handleAddUrl() {
    const url = addUrlInput.trim()
    if (!url) { setAddUrlError('Введите ссылку'); return }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setAddUrlError('Ссылка должна начинаться с http:// или https://')
      return
    }
    setAddUrlError(null); setAddingUrl(true)
    try {
      const res = await fetch(`/api/documents/${doc.id}/add-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      const data = await res.json()
      if (!res.ok) { setAddUrlError(data.detail || 'Ошибка при загрузке страницы'); return }
      setAddedUrls(prev => [...prev, url])
      setAddUrlInput('')
      setShowAddUrl(false)
      await loadDocument(doc.id)
    } catch { setAddUrlError('Не удалось связаться с сервером') }
    finally { setAddingUrl(false) }
  }

  // ── Загрузка ──────────────────────────────────────────────────────────────

  function handleDrop(e) {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  function handleFileChange(e) {
    const file = e.target.files[0]
    if (file) uploadFile(file)
    e.target.value = ''
  }

  async function uploadFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!ALLOWED_EXT.includes(ext)) {
      setUploadError(`Формат «${ext}» не поддерживается. Разрешены: ${ALLOWED_EXT.join(', ')}`)
      return
    }
    setUploadError(null); setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/documents/upload', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) { setUploadError(data.detail || 'Ошибка при загрузке'); return }
      if (data.conflict) {
        // Автоматически заменяем без подтверждения
        setUploading(true)
        try {
          const formData2 = new FormData()
          formData2.append('file', file)
          const res2 = await fetch(`/api/documents/upload/replace/${data.existing_id}`, { method: 'POST', body: formData2 })
          const data2 = await res2.json()
          if (!res2.ok) { setUploadError(data2.detail || 'Ошибка при замене'); return }
          await loadDocument(data2.id)
        } catch { setUploadError('Не удалось связаться с сервером') }
        finally { setUploading(false) }
        return
      }
      await loadDocument(data.id)
    } catch { setUploadError('Не удалось связаться с сервером') }
    finally { setUploading(false) }
  }

  async function loadDocument(id) {
    const res = await fetch(`/api/documents/${id}/structure`)
    const data = await res.json()
    setDoc(data.document)
    setSections(data.sections)
    setSelectedSection(null)
    setProgress(null); setSummary(null); setEvalError(null)
    await _loadProjects(data.document?.project_id)
  }

  async function _loadProjects(currentProjectId) {
    try {
      const res = await fetch('/api/projects/')
      const list = await res.json()
      setProjects(list)
      if (currentProjectId) {
        setDocProject(list.find(p => p.id === currentProjectId) || null)
      } else {
        setDocProject(null)
      }
    } catch { setProjects([]) }
  }

  // Подгружаем проекты при открытии документа из ProjectPage (через контекст)
  useEffect(() => {
    if (doc) _loadProjects(doc.project_id)
  }, [doc?.id])

  // Если документ уже оценён — загружаем интегральную оценку
  useEffect(() => {
    if (doc && hasEvaluations) loadIntegral(doc.id)
    else setIntegral(null)
  }, [doc?.id, hasEvaluations])

  async function handleProjectChange(e) {
    const projectId = e.target.value === '' ? null : parseInt(e.target.value)
    setSavingProject(true)
    try {
      await fetch(`/api/projects/documents/${doc.id}/assign`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      })
      setDoc(d => ({ ...d, project_id: projectId }))
      setDocProject(projectId ? projects.find(p => p.id === projectId) || null : null)
    } finally {
      setSavingProject(false)
    }
  }

  async function handleIncludeToggle(instructionId, include) {
    await fetch(`/api/instructions/${instructionId}/include`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include }),
    })
    setSections(prev => prev.map(s => s.id === instructionId ? { ...s, include_in_evaluation: include } : s))
  }

  async function handleBulkInclude(include) {
    await fetch(`/api/instructions/document/${doc.id}/include-all`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include }),
    })
    setSections(prev => prev.map(s => ({ ...s, include_in_evaluation: include })))
  }

  // ── Навигация по разделам ─────────────────────────────────────────────────

  const evalSections = sections.filter(s =>
    s.classification === 'instruction' || s.classification === 'possible'
  )
  const selectedIdx = selectedSection
    ? evalSections.findIndex(s => s.id === selectedSection.id)
    : -1

  function selectSection(section) {
    setSelectedSection(section)
    setShowFeedback(false)
  }

  // ── Оценка ────────────────────────────────────────────────────────────────

  async function handleEvaluate(resume = false) {
    if (!doc) return
    setRunning(true); setEvalError(null); setSummary(null)
    if (!resume) setProgress(null)

    const url = `/api/evaluation/document/${doc.id}${resume ? '?resume=true' : ''}`
    const eventSource = new EventSource(url)

    eventSource.onmessage = (e) => {
      const event = JSON.parse(e.data)
      if (event.type === 'start') {
        setProgress(prev => resume && prev
          ? { ...prev, total: event.total }
          : { done: 0, total: event.total, items: [] })
      }
      if (event.type === 'progress') {
        setProgress(prev => ({
          ...prev, done: event.done, total: event.total,
          items: [...(prev?.items || []), { id: event.instruction_id, title: event.title, color: event.color }],
        }))
        setSections(prev => prev.map(s =>
          s.id === event.instruction_id ? { ...s, color: event.color } : s
        ))
        // Обновляем выбранный раздел если он только что оценён
        setSelectedSection(prev =>
          prev?.id === event.instruction_id ? { ...prev, color: event.color } : prev
        )
      }
      if (event.type === 'skip') {
        setProgress(prev => ({
          ...prev, done: event.done, total: event.total,
          items: [...(prev?.items || []), { id: event.instruction_id, title: event.title, color: event.color, skipped: true }],
        }))
      }
      if (event.type === 'error') {
        setEvalError({ message: event.message, advice: event.advice })
        eventSource.close(); setRunning(false)
      }
      if (event.type === 'done') {
        setSummary(event.summary)
        if (!event.aborted) {
          setHasEvaluations(true)
          loadIntegral(doc.id)
        }
        eventSource.close(); setRunning(false)
      }
    }
    eventSource.onerror = () => {
      setEvalError({ message: 'Соединение с сервером прервано', advice: 'Проверьте, запущен ли бэкенд.' })
      eventSource.close(); setRunning(false)
    }
  }

  async function loadIntegral(docId) {
    try {
      const res = await fetch(`/api/evaluation/document/${docId}/summary`)
      if (res.ok) setIntegral(await res.json())
    } catch { /* не критично */ }
  }

  async function handleReeval(instructionId) {
    setEvalError(null)
    const res = await fetch(`/api/evaluation/instruction/${instructionId}`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) { setEvalError({ message: data.detail?.message || 'Ошибка оценки', advice: data.detail?.advice || '' }); return }
    setSections(prev => prev.map(s => s.id === instructionId ? { ...s, color: data.color } : s))
    setProgress(prev => prev ? {
      ...prev,
      items: prev.items.map(i => i.id === instructionId ? { ...i, color: data.color } : i),
    } : null)
    if (selectedSection?.id === instructionId) {
      setSelectedSection(prev => ({ ...prev, color: data.color, evaluation: data }))
    }
  }

  async function handleOverride(instructionId, type, criterion, value) {
    const body = { type, value }
    if (type === 'criteria') body.criterion = criterion
    const res = await fetch(`/api/instructions/${instructionId}/override`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) return
    const data = await res.json()
    // Обновляем overrides в selectedSection и в sections
    const updater = s => s.id === instructionId ? { ...s, overrides: data.overrides } : s
    setSections(prev => prev.map(updater))
    setSelectedSection(prev => prev?.id === instructionId ? { ...prev, overrides: data.overrides } : prev)
  }

  async function handleReset() {
    if (!doc) return
    await fetch(`/api/evaluation/document/${doc.id}`, { method: 'DELETE' })
    setProgress(null); setSummary(null); setEvalError(null); setHasEvaluations(false); setIntegral(null)
    setSections(prev => prev.map(s => ({ ...s, color: null })))
    setSelectedSection(null)
  }

  async function handleExportXls() {
    window.location.href = `/api/snapshots/document/${doc.id}/export`
  }

  // ── Загрузка фидбека конкретного раздела ──────────────────────────────────

  async function loadSectionFeedback(section) {
    if (!section || !section.id) return null
    const res = await fetch(`/api/evaluation/instruction/${section.id}`)
    if (!res.ok) return null
    return res.json()
  }

  async function handleShowFeedback() {
    if (!selectedSection) return
    const data = await loadSectionFeedback(selectedSection)
    if (data) {
      setSelectedSection(prev => ({ ...prev, _feedback: data }))
    }
    setShowFeedback(true)
  }

  const counts = sections.reduce((acc, s) => {
    acc[s.classification] = (acc[s.classification] || 0) + 1
    return acc
  }, {})

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="page eval-page">

      {/* Зона загрузки */}
      {!doc && (
        <div className="eval-upload">
          <h1 className="page-title">Оценка инструкций</h1>
          <p className="page-subtitle">Загрузите документ для начала работы</p>

          {/* Вкладки */}
          <p className="upload-hint">
            Загрузите документ или ссылку на веб-страницу с инструкцией. После загрузки первой ссылки вы можете добавить другие — все они будут проверены как один документ.<br />
            Приложение оптимизировано для парсинга инструкций веб-справки Positive Technologies. Контент других сайтов может отображаться с ошибками.
          </p>

          {/* Вкладки */}
          <div className="upload-tabs">
            <button
              className={`upload-tab${uploadTab === 'file' ? ' upload-tab--active' : ''}`}
              onClick={() => { setUploadTab('file'); setUploadError(null) }}
            >📄 Файл</button>
            <button
              className={`upload-tab${uploadTab === 'url' ? ' upload-tab--active' : ''}`}
              onClick={() => { setUploadTab('url'); setUploadError(null) }}
            >🔗 По ссылке</button>
          </div>

          {/* Файл */}
          {uploadTab === 'file' && (
            <div
              className={`drop-zone${dragOver ? ' drop-zone--over' : ''}${uploading ? ' drop-zone--loading' : ''}`}
              onClick={() => !uploading && fileInputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,.md,.txt"
                style={{ display: 'none' }} onChange={handleFileChange} />
              {uploading ? (
                <><div className="drop-zone__spinner" /><p className="drop-zone__text">Загрузка и парсинг…</p></>
              ) : (
                <>
                  <div className="drop-zone__icon">📄</div>
                  <p className="drop-zone__text">Перетащите файл сюда или <span className="drop-zone__link">выберите на диске</span></p>
                  <p className="drop-zone__hint">{ALLOWED_EXT.join('  ·  ')}</p>
                </>
              )}
            </div>
          )}

          {/* По ссылке */}
          {uploadTab === 'url' && (
            <div className="url-zone">
              <input
                className="url-zone__input snap-name-input"
                type="url"
                placeholder="https://help.example.com/..."
                value={urlInput}
                onChange={e => setUrlInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !uploading && uploadUrl()}
                disabled={uploading}
                autoFocus
              />
              <button
                className="btn btn-primary"
                onClick={uploadUrl}
                disabled={uploading}
              >
                {uploading ? <><span className="drop-zone__spinner" style={{ width: 14, height: 14, marginRight: 6 }} />Загрузка…</> : 'Загрузить'}
              </button>
              <p className="drop-zone__hint" style={{ marginTop: 8 }}>
                Страница откроется в браузере на сервере — работает с JS-сайтами
              </p>
            </div>
          )}

          {uploadError && <div className="alert alert-error">⚠️ {uploadError}</div>}
        </div>
      )}

      {/* Основной экран */}
      {doc && (
        <div className="eval-main">

          {/* Шапка */}
          <div className="eval-header card">
            <div className="eval-header__left">
              <span className="eval-header__icon">{fileIcon(doc.file_type)}</span>
              <div>
                <div className="eval-header__name">{doc.filename}</div>
                <div className="eval-header__meta">
                  {sections.length} разделов · {doc.file_type.toUpperCase()}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                  <select
                    className="doc-type-select"
                    value={doc.project_id || ''}
                    onChange={handleProjectChange}
                    disabled={savingProject}
                    style={{ fontSize: 12, padding: '3px 8px' }}
                  >
                    <option value="">— без проекта —</option>
                    {projects.map(p => (
                      <option key={p.id} value={p.id}>📁 {p.name}</option>
                    ))}
                  </select>
                  {docProject ? (
                    docProject.has_context
                      ? <span style={{ fontSize: 12, color: 'var(--color-green)' }} title="Контекст продукта задан и будет использован при оценке">✅ контекст задан</span>
                      : <span
                          style={{ fontSize: 12, color: '#b45309', cursor: 'pointer' }}
                          title="Контекст не задан — оценка без учёта специфики продукта. Нажмите, чтобы перейти в проект."
                          onClick={() => navigate(`/projects/${doc.project_id}`)}
                        >⚠️ контекст не задан</span>
                  ) : (
                    <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>контекст не используется</span>
                  )}
                </div>
              </div>
            </div>
            <div className="eval-header__right">
              <button className="btn btn-secondary btn-sm" onClick={clearDocument}>Загрузить другой</button>
            </div>
          </div>

          {/* Список загруженных URL (только для web-документов) */}
          {doc.file_type === 'web' && (
            <div className="card" style={{ padding: '12px 16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: addedUrls.length > 0 ? 8 : 0 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>🔗 Загруженные страницы</span>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => { setShowAddUrl(v => !v); setAddUrlError(null); setAddUrlInput('') }}
                  disabled={addingUrl}
                >
                  {showAddUrl ? 'Отмена' : '+ Добавить страницу'}
                </button>
              </div>
              {addedUrls.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: showAddUrl ? 10 : 0 }}>
                  {addedUrls.map((u, i) => (
                    <div key={i} style={{ fontSize: 12, color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ color: 'var(--color-green)' }}>✓</span>
                      <a href={u} target="_blank" rel="noreferrer" style={{ color: 'var(--color-primary)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u}</a>
                    </div>
                  ))}
                </div>
              )}
              {showAddUrl && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      className="snap-name-input"
                      type="url"
                      placeholder="https://help.example.com/..."
                      value={addUrlInput}
                      onChange={e => setAddUrlInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && !addingUrl && handleAddUrl()}
                      disabled={addingUrl}
                      autoFocus
                      style={{ flex: 1 }}
                    />
                    <button className="btn btn-primary" onClick={handleAddUrl} disabled={addingUrl}>
                      {addingUrl ? 'Загрузка…' : 'Загрузить'}
                    </button>
                  </div>
                  {addUrlError && <div className="alert alert-error" style={{ margin: 0 }}>⚠️ {addUrlError}</div>}
                </div>
              )}
            </div>
          )}


          {/* Прогресс-бар и сводка */}
          {progress && (
            <div className="card eval-progress-bar-card">
              <div className="eval-progress__header">
                <span className="eval-progress__label">
                  {running ? `Оценивается… ${progress.done} из ${progress.total}` : `Оценено: ${progress.done} из ${progress.total}`}
                </span>
                <span className="eval-progress__percent">{Math.round((progress.done / progress.total) * 100)}%</span>
              </div>
              <div className="progress-bar">
                <div className="progress-bar__fill" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
              </div>
            </div>
          )}

          {summary && !running && (
            <div className="eval-summary-bar card">
              {['green', 'yellow', 'orange', 'red'].map(color => {
                const total = (summary.green || 0) + (summary.yellow || 0) + (summary.orange || 0) + (summary.red || 0)
                const pct = total > 0 ? Math.round((summary[color] || 0) / total * 100) : 0
                return (
                  <div
                    key={color}
                    className={`summary-block summary-block--${color}${(summary[color] || 0) > 0 ? ' summary-block--clickable' : ''}`}
                    onClick={() => (summary[color] || 0) > 0 && setStatusModal(color)}
                    title={(summary[color] || 0) > 0 ? 'Нажмите, чтобы увидеть список разделов' : undefined}
                  >
                    <span className="summary-block__emoji">{COLOR_EMOJI[color]}</span>
                    <span className="summary-block__count">{summary[color] || 0}</span>
                    <span className="summary-block__label">{COLOR_LABEL[color]}</span>
                    <span className="summary-block__pct">{pct}%</span>
                    <span className="summary-block__tooltip">{COLOR_RULE[color]}</span>
                  </div>
                )
              })}
              {summary.errors > 0 && <span className="eval-summary__errors">⚠️ {summary.errors} не оценено</span>}
            </div>
          )}

          {integral && !running && (
            <div className="card integral-card">
              <div className="integral-card__header">
                <span className="integral-card__header-title">Итоговая оценка</span>
                <button className="scale-info-link" onClick={() => setShowScaleInfo(true)}>
                  Как работает оценка?
                </button>
              </div>
              <div className="integral-card__body">
                <div className="integral-card__left">
                  <span className={`integral-card__grade integral-card__grade--${integral.grade.toLowerCase()}`}>
                    {integral.grade}
                  </span>
                  <div className="integral-card__score-wrap">
                    <span className={`integral-card__verdict integral-card__verdict--${integral.grade.toLowerCase()}`}>
                      {integral.grade_label}
                    </span>
                    <span className="integral-card__score">{integral.score}%</span>
                    <span className="integral-card__meta">
                      {integral.evaluated_count} из {integral.total_count} разделов оценено
                    </span>
                  </div>
                </div>
                {integral.top_violations.length > 0 && (
                  <div className="integral-card__right">
                    <span className="integral-card__violations-title">Частые нарушения:</span>
                    <ol className="integral-card__violations">
                      {integral.top_violations.map(v => (
                        <li key={v.criterion_id} className="integral-card__violation">
                          <span className="integral-card__violation-id">{v.criterion_id}</span>
                          <span className="integral-card__violation-label">{v.label}</span>
                          <span className="integral-card__violation-count">{v.error_count}×</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
              <div className="integral-card__footer">
                <button className="btn btn-secondary btn-sm" onClick={handleExportXls}>
                  ⬇ Скачать XLS
                </button>
                <span className="integral-card__footer-hint">
                  Хотите зафиксировать результат? Перейдите в раздел <strong>Снимки</strong>
                </span>
              </div>
            </div>
          )}

          {evalError && (
            <div className="alert alert-error">
              <div className="alert__message">⚠️ {evalError.message}</div>
              {evalError.advice && <div className="alert__advice">💡 {evalError.advice}</div>}
            </div>
          )}

          {/* Двухколоночный layout */}
          <div className="eval-columns">

            {/* Левая колонка — структура */}
            <div className="eval-col eval-col--tree card">
              <div className="eval-toolbar">
                <div className="eval-toolbar__left">
                  <h2 className="tree-card__title">Структура документа</h2>
                  <div className="classification-counts">
                    <span className="count-badge count-badge--instruction">✓ {counts['instruction'] || 0} инструкций</span>
                    <span className="count-badge count-badge--possible">? {counts['possible'] || 0} возможных</span>
                    <span className="count-badge count-badge--other">— {counts['non-instruction'] || 0} прочих</span>
                  </div>
                </div>
                <div className="eval-toolbar__right">
                  <button className="btn btn-primary" onClick={() => handleEvaluate(false)} disabled={running}>
                    {running ? 'Оценка…' : '▶ Оценить'}
                  </button>
                  {evalError && !running && progress && (
                    <button className="btn btn-primary" onClick={() => handleEvaluate(true)}>↻ Продолжить</button>
                  )}
                  {(progress || summary) && !running && (
                    <button className="btn btn-secondary" onClick={handleReset}>Сбросить</button>
                  )}
                  <div className="bulk-btns">
                    <button className="btn btn-secondary btn-sm" onClick={() => handleBulkInclude(true)}>✓ Все</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => handleBulkInclude(false)}>✗ Все</button>
                  </div>
                </div>
              </div>
              <div className="tree-scroll">
                <DocumentTree
                  sections={sections}
                  onIncludeToggle={handleIncludeToggle}
                  selectedId={selectedSection?.id}
                  onSelect={selectSection}
                />
              </div>
            </div>

            {/* Правая колонка — просмотр раздела */}
            <div className="eval-col eval-col--preview card">
              {!selectedSection ? (
                <div className="preview-empty">
                  <span className="preview-empty__icon">👈</span>
                  <p>Выберите раздел в структуре для просмотра</p>
                </div>
              ) : (
                <div className="preview-panel">
                  {/* Навигация */}
                  <div className="preview-nav">
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={selectedIdx <= 0}
                      onClick={() => selectSection(evalSections[selectedIdx - 1])}
                    >← Назад</button>
                    <span className="preview-nav__counter">
                      {selectedIdx + 1} / {evalSections.length}
                    </span>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={selectedIdx >= evalSections.length - 1}
                      onClick={() => selectSection(evalSections[selectedIdx + 1])}
                    >Вперёд →</button>
                  </div>

                  {/* Заголовок раздела */}
                  <div className="preview-header">
                    <h3 className="preview-title">{selectedSection.title}</h3>
                    <div className="preview-meta">
                      {selectedSection.page_number && <span className="badge badge-gray">стр. {selectedSection.page_number}</span>}
                      {selectedSection.color && (
                        <span className={`badge badge-${selectedSection.color}`}>
                          {COLOR_EMOJI[selectedSection.color]} {COLOR_LABEL[selectedSection.color]}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Текст раздела */}
                  <div className="preview-content">
                    {selectedSection.content
                      ? formatContent(selectedSection.content)
                      : <span className="preview-empty-text">Содержимое раздела недоступно</span>
                    }
                  </div>

                  {/* Фидбек от LLM */}
                  {selectedSection.color && (
                    <div className="preview-feedback">
                      {!showFeedback ? (
                        <button className="btn btn-secondary btn-sm" onClick={handleShowFeedback}>
                          💬 Показать фидбек от LLM
                        </button>
                      ) : (
                        <FeedbackPanel
                          section={selectedSection}
                          onReeval={() => handleReeval(selectedSection.id)}
                          onOverride={(type, criterion, value) => handleOverride(selectedSection.id, type, criterion, value)}
                          running={running}
                          criteriaLabels={criteriaLabels}
                        />
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {showScaleInfo && <ScaleInfoModal onClose={() => setShowScaleInfo(false)} />}
      {statusModal && (
        <StatusModal
          color={statusModal}
          sections={sections}
          onSelect={s => { selectSection(s); setStatusModal(null) }}
          onClose={() => setStatusModal(null)}
        />
      )}

    </div>
  )
}

// ── Модал списка разделов по статусу ─────────────────────────────────────────

function StatusModal({ color, sections, onSelect, onClose }) {
  const COLOR_EMOJI = { green: '🟢', yellow: '🟡', orange: '🟠', red: '🔴' }
  const COLOR_LABEL = { green: 'Хорошо', yellow: 'Замечания', orange: 'Проблемы', red: 'Критично' }

  const matched = sections.filter(s => s.color === color)

  function handleCopy() {
    const text = matched.map(s =>
      s.page_number ? `${s.title} (стр. ${s.page_number})` : s.title
    ).join('\n')
    navigator.clipboard.writeText(text).catch(() => {})
  }

  return (
    <div className="scale-modal-overlay" onClick={onClose}>
      <div className="scale-modal status-modal" onClick={e => e.stopPropagation()}>
        <div className="scale-modal__header">
          <h3 className="scale-modal__title">
            {COLOR_EMOJI[color]} {COLOR_LABEL[color]} — {matched.length} разд.
          </h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button className="btn btn-secondary btn-sm" onClick={handleCopy}>
              📋 Скопировать список
            </button>
            <button className="scale-modal__close" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="scale-modal__body status-modal__body">
          {matched.length === 0 ? (
            <p style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>Нет разделов с этим статусом.</p>
          ) : (
            <ul className="status-modal__list">
              {matched.map(s => (
                <li key={s.id} className="status-modal__item" onClick={() => onSelect(s)}>
                  <span className="status-modal__title">{s.title}</span>
                  {s.page_number && (
                    <span className="status-modal__page">стр. {s.page_number}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Модал «Как работает оценка» ───────────────────────────────────────────────

function ScaleInfoModal({ onClose }) {
  return (
    <div className="scale-modal-overlay" onClick={onClose}>
      <div className="scale-modal" onClick={e => e.stopPropagation()}>
        <div className="scale-modal__header">
          <h3 className="scale-modal__title">Как работает оценка</h3>
          <button className="scale-modal__close" onClick={onClose}>✕</button>
        </div>

        <div className="scale-modal__body">

          <section className="scale-modal__section">
            <h4 className="scale-modal__section-title">Шкала вердиктов</h4>
            <div className="scale-modal__scale">
              {[
                { color: 'green',  emoji: '🟢', label: 'Хорошо',            rule: 'Нет ошибок, не более одного замечания' },
                { color: 'yellow', emoji: '🟡', label: 'Есть замечания',     rule: 'Не более одной ошибки' },
                { color: 'orange', emoji: '🟠', label: 'Требует доработки',  rule: '2–3 ошибки' },
                { color: 'red',    emoji: '🔴', label: 'Критично',           rule: '4 и более ошибок' },
              ].map(({ color, emoji, label, rule }) => (
                <div key={color} className={`scale-modal__row scale-modal__row--${color}`}>
                  <span className="scale-modal__emoji">{emoji}</span>
                  <span className="scale-modal__color-label">{label}</span>
                  <span className="scale-modal__rule">{rule}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="scale-modal__section">
            <h4 className="scale-modal__section-title">Результаты по критериям</h4>
            <div className="scale-modal__badges">
              <div className="scale-modal__badge-row">
                <span className="criteria-badge criteria-badge--ok">ok</span>
                <span className="scale-modal__badge-desc">Критерий полностью выполнен</span>
              </div>
              <div className="scale-modal__badge-row">
                <span className="criteria-badge criteria-badge--warning">warning</span>
                <span className="scale-modal__badge-desc">Критерий выполнен частично — элемент есть, но неполный или неточный</span>
              </div>
              <div className="scale-modal__badge-row">
                <span className="criteria-badge criteria-badge--error">error</span>
                <span className="scale-modal__badge-desc">Критерий не выполнен — элемент отсутствует или существенно нарушен</span>
              </div>
            </div>
          </section>

          <section className="scale-modal__section">
            <h4 className="scale-modal__section-title">Итоговая оценка документа</h4>
            <div className="scale-modal__scale">
              {[
                { grade: 'A', color: 'green',  label: 'Полностью соответствует',     range: '≥ 85%' },
                { grade: 'B', color: 'yellow', label: 'Соответствует с замечаниями', range: '65–84%' },
                { grade: 'C', color: 'orange', label: 'Не соответствует',            range: '40–64%' },
                { grade: 'D', color: 'red',    label: 'Полностью не соответствует',  range: '< 40%' },
              ].map(({ grade, color, label, range }) => (
                <div key={grade} className={`scale-modal__row scale-modal__row--${color}`}>
                  <span className={`integral-card__grade integral-card__grade--${grade.toLowerCase()} scale-modal__grade-badge`}>{grade}</span>
                  <span className="scale-modal__color-label">{label}</span>
                  <span className="scale-modal__rule">{range}</span>
                </div>
              ))}
            </div>
            <p className="scale-modal__text" style={{ marginTop: 10 }}>
              Балл = сумма очков всех разделов / (кол-во разделов × 3) × 100%.
              Каждый раздел приносит: 🟢 3 очка, 🟡 2 очка, 🟠 1 очко, 🔴 0 очков.
            </p>
          </section>

          <section className="scale-modal__section">
            <h4 className="scale-modal__section-title">Источник критериев</h4>
            <p className="scale-modal__text">
              Критерии оценки основаны на стандартах написания технической документации
              для ИБ-продуктов: структура инструкции, формулировка шагов, наличие
              предварительных условий, описание результата. Активный набор критериев
              можно посмотреть и изменить в разделе{' '}
              <strong>Настройки → Критерии</strong>.
            </p>
          </section>

        </div>
      </div>
    </div>
  )
}

// ── Панель фидбека ────────────────────────────────────────────────────────────

function FeedbackPanel({ section, onReeval, onOverride, running, criteriaLabels }) {
  const feedback = section._feedback
  const criteria = section._feedback?.criteria_results || {}
  const recommendations = section._feedback?.recommendations || []
  const overrides = section.overrides || {}
  const criteriaOverrides = overrides.criteria || {}
  const sectionOverride = overrides.section === true

  if (!feedback) {
    return <p style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>Загрузка фидбека…</p>
  }

  return (
    <div className="feedback-panel">
      <div className="feedback-panel__header">
        <span className="feedback-panel__title">💬 Фидбек от LLM</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button
            className={`btn btn-secondary btn-sm${sectionOverride ? ' override-active' : ''}`}
            title={sectionOverride ? 'Снять отметку' : 'Пометить раздел как ложное срабатывание'}
            onClick={() => onOverride('section', null, !sectionOverride)}
            style={{ fontSize: 12 }}
          >
            {sectionOverride ? '⚠️ Ложное срабатывание' : 'Отметить как ложное срабатывание'}
          </button>
          <button className="btn-reeval" title="Переоценить" onClick={onReeval} disabled={running}>↺</button>
        </div>
      </div>
      {sectionOverride && (
        <div style={{ fontSize: 12, color: '#854d0e', marginBottom: 8, padding: '6px 10px', background: '#fef9c3', borderRadius: 6, border: '1px solid #fde68a' }}>
          ⚠️ Раздел помечен как ложное срабатывание — оценка LLM может не учитывать контекст документа
        </div>
      )}
      <div className="feedback-criteria">
        {Object.entries(criteria).map(([key, val]) => {
          const isOverridden = criteriaOverrides[key] === true
          return (
            <span key={key} className={`criteria-badge criteria-badge--${isOverridden ? 'overridden' : val}`} title={criteriaLabels?.[key] || key}>
              {isOverridden && '⚠️ '}{key}: {isOverridden ? 'ignored' : val}
            </span>
          )
        })}
      </div>
      {recommendations.length > 0 && (
        <div className="feedback-recommendations">
          {recommendations.map((r, i) => {
            const isOverridden = criteriaOverrides[r.criterion] === true
            return (
              <div key={i} className={`feedback-rec${isOverridden ? ' feedback-rec--overridden' : ''}`}>
                <div className="feedback-rec__criterion">
                  {isOverridden && <span title="Ложное срабатывание" style={{ marginRight: 4 }}>⚠️</span>}
                  [{r.criterion}] {criteriaLabels?.[r.criterion]?.split(' — ')[0] || ''}
                </div>
                <div className="feedback-rec__text" style={{ opacity: isOverridden ? 0.4 : 1 }}>{r.text}</div>
                {r.example && <div className="feedback-rec__example" style={{ opacity: isOverridden ? 0.4 : 1 }}>Пример: {r.example}</div>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function fileIcon(type) {
  return { pdf: '📕', docx: '📘', md: '📝', txt: '📄', web: '🌐' }[type] || '📄'
}

// ── Форматирование текста раздела ─────────────────────────────────────────────

function formatContent(text) {
  const lines = text.split('\n')
  return lines.map((line, i) => {
    if (!line.trim()) return <br key={i} />
    if (line.startsWith('# '))   return <h1 key={i} className="preview-h1">{line.slice(2)}</h1>
    if (line.startsWith('## '))  return <h2 key={i} className="preview-h2">{line.slice(3)}</h2>
    if (line.startsWith('### ')) return <h3 key={i} className="preview-h3">{line.slice(4)}</h3>
    if (line.startsWith('- ') || line.startsWith('* '))
      return <li key={i} className="preview-li">{line.slice(2)}</li>
    if (/^\d+\.\s/.test(line))
      return <li key={i} className="preview-li preview-li--num">{line.replace(/^\d+\.\s/, '')}</li>
    return <p key={i} className="preview-p">{line}</p>
  })
}
