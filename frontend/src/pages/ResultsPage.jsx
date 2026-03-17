import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import DocumentTree from '../components/DocumentTree'
import '../styles/ResultsPage.css'

const DOC_TYPES = [
  'Руководство по развёртыванию',
  'Руководство пользователя',
  'Руководство администратора',
  'Справочник по настройке источников',
  'Справочник по PDQL',
]

export default function ResultsPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [doc, setDoc] = useState(null)
  const [sections, setSections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [savingType, setSavingType] = useState(false)

  useEffect(() => {
    if (!id) { setLoading(false); return }
    fetchStructure(id)
  }, [id])

  async function fetchStructure(docId) {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/documents/${docId}/structure`)
      if (!res.ok) throw new Error('Документ не найден')
      const data = await res.json()
      setDoc(data.document)
      setSections(data.sections)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDocTypeChange(e) {
    const newType = e.target.value
    setSavingType(true)
    try {
      await fetch(`/api/documents/${id}/type`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_type: newType }),
      })
      setDoc(d => ({ ...d, doc_type: newType }))
    } finally {
      setSavingType(false)
    }
  }

  async function handleIncludeToggle(instructionId, include) {
    await fetch(`/api/instructions/${instructionId}/include`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include }),
    })
    setSections(prev =>
      prev.map(s => s.id === instructionId ? { ...s, include_in_evaluation: include } : s)
    )
  }

  async function handleBulkInclude(include) {
    await fetch(`/api/instructions/document/${id}/include-all`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include }),
    })
    setSections(prev => prev.map(s => ({ ...s, include_in_evaluation: include })))
  }

  // Счётчики классификации
  const counts = sections.reduce((acc, s) => {
    acc[s.classification] = (acc[s.classification] || 0) + 1
    return acc
  }, {})

  if (!id) return (
    <div className="page">
      <h1 className="page-title">Результаты</h1>
      <p className="page-subtitle">Загрузите документ, чтобы увидеть его структуру</p>
      <div className="card">
        <p style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>
          Ни один документ ещё не загружен.{' '}
          <button className="link-btn" onClick={() => navigate('/document')}>Загрузить →</button>
        </p>
      </div>
    </div>
  )

  if (loading) return (
    <div className="page"><p style={{ color: 'var(--color-text-secondary)' }}>Загрузка структуры…</p></div>
  )

  if (error) return (
    <div className="page">
      <div className="alert alert-error">⚠️ {error}</div>
      <button className="btn btn-secondary" onClick={() => navigate('/document')}>← Загрузить другой</button>
    </div>
  )

  return (
    <div className="page results-page">
      {/* Шапка документа */}
      <div className="doc-header card">
        <div className="doc-header__main">
          <span className="doc-header__icon">{fileIcon(doc.file_type)}</span>
          <div>
            <div className="doc-header__name">{doc.filename}</div>
            <div className="doc-header__meta">{sections.length} разделов · {doc.file_type.toUpperCase()}</div>
          </div>
          <button className="btn btn-secondary" style={{ marginLeft: 'auto' }}
            onClick={() => navigate('/document')}>
            Загрузить другой
          </button>
        </div>

        {/* Счётчики классификации */}
        <div className="classification-counts">
          <span className="count-badge count-badge--instruction">
            ✓ {counts['instruction'] || 0} инструкций
          </span>
          <span className="count-badge count-badge--possible">
            ? {counts['possible'] || 0} возможных
          </span>
          <span className="count-badge count-badge--other">
            — {counts['non-instruction'] || 0} прочих
          </span>
        </div>

        {/* Выбор типа документа */}
        <div className="doc-type-row">
          <label className="doc-type-label">Тип документа:</label>
          <select className="doc-type-select" value={doc.doc_type || ''}
            onChange={handleDocTypeChange} disabled={savingType}>
            <option value="" disabled>— выберите тип —</option>
            {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          {!doc.doc_type && (
            <span className="doc-type-hint">⚠️ Укажите тип для корректной оценки</span>
          )}
        </div>
      </div>

      {/* Дерево разделов */}
      <div className="card tree-card">
        <div className="tree-card__header">
          <h2 className="tree-card__title">Структура документа</h2>
          <div className="tree-card__actions">
            <button className="btn btn-secondary btn-sm" onClick={() => handleBulkInclude(true)}>
              ✓ Включить все
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => handleBulkInclude(false)}>
              ✗ Исключить все
            </button>
          </div>
        </div>
        <DocumentTree sections={sections} onIncludeToggle={handleIncludeToggle} />
      </div>
    </div>
  )
}

function fileIcon(type) {
  return { pdf: '📕', docx: '📘', md: '📝', txt: '📄' }[type] || '📄'
}
