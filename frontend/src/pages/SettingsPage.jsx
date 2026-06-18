import { useState, useEffect } from 'react'

const PROVIDER_PRESETS = {
  openai:    { label: 'OpenAI',    base_url: 'https://api.openai.com/v1',    requires_key: true  },
  anthropic: { label: 'Anthropic', base_url: 'https://api.anthropic.com/v1', requires_key: true  },
  local:     { label: 'Ollama',    base_url: 'http://localhost:11434/v1',     requires_key: false },
  custom:    { label: 'Другой',    base_url: '',                              requires_key: true  },
}

const EMPTY_FORM = {
  model_id: '', name: '', provider: 'openai',
  base_url: PROVIDER_PRESETS.openai.base_url,
  requires_key: true, api_key: '',
}

export default function SettingsPage() {
  const [models, setModels] = useState([])
  const [activeModelId, setActiveModelId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formSaving, setFormSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  // Критерии
  const [criteriaSets, setCriteriaSets] = useState([])
  const [criteriaForm, setCriteriaForm] = useState(null) // null | { id, name, content } | 'new'
  const [criteriaSaving, setCriteriaSaving] = useState(false)
  const [criteriaError, setCriteriaError] = useState(null)

  const CRITERIA_TEMPLATE = `# Критерии оценки инструкций

## 1. Структура инструкции

### 1.1 Название критерия
Описание того, что проверяется.

### 1.2 Другой критерий
Описание.

## 2. Другая группа

### 2.1 Критерий
Описание.`

  useEffect(() => { fetchModels(); fetchCriteriaSets() }, [])

  async function fetchModels() {
    try {
      const res = await fetch('/api/config/models')
      const data = await res.json()
      setModels(data.models)
      setActiveModelId(data.active_model)
    } catch {
      setError('Не удалось загрузить список моделей')
    } finally {
      setLoading(false)
    }
  }

  async function fetchCriteriaSets() {
    try {
      const res = await fetch('/api/config/criteria-sets')
      const data = await res.json()
      setCriteriaSets(data)
    } catch {}
  }

  async function handleSetActive(modelId) {
    setActiveModelId(modelId)
    await fetch('/api/config/active-model', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    })
  }

  function openAddForm() {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setFormError(null)
    setShowForm(true)
  }

  function openEditForm(m) {
    setEditingId(m.id)
    setForm({ model_id: m.model_id, name: m.name, provider: m.provider, base_url: m.base_url, requires_key: m.requires_key, api_key: '' })
    setFormError(null)
    setShowForm(true)
  }

  function handleProviderChange(provider) {
    const preset = PROVIDER_PRESETS[provider]
    setForm(f => ({ ...f, provider, base_url: preset.base_url || f.base_url, requires_key: preset.requires_key }))
  }

  async function handleSaveModel() {
    const { model_id, name, provider, base_url, requires_key, api_key } = form
    if (!model_id.trim() || !name.trim() || !base_url.trim()) { setFormError('Заполните все обязательные поля'); return }
    setFormSaving(true); setFormError(null)
    try {
      let res
      if (editingId) {
        res = await fetch(`/api/config/models/${editingId}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_id, name, provider, base_url, requires_key, api_key: api_key.trim() || null }),
        })
      } else {
        res = await fetch('/api/config/models', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_id, name, provider, base_url, requires_key, api_key: api_key.trim() || null }),
        })
      }
      if (!res.ok) { const d = await res.json(); setFormError(d.detail || 'Ошибка сохранения'); return }
      setShowForm(false); await fetchModels()
    } finally { setFormSaving(false) }
  }

  async function handleDeleteModel(m) {
    if (!confirm(`Удалить модель «${m.name}»?`)) return
    await fetch(`/api/config/models/${m.id}`, { method: 'DELETE' })
    await fetchModels()
  }

  // ── Критерии ────────────────────────────────────────────────────────────────

  async function handleActivateCriteria(id) {
    await fetch(`/api/config/criteria-sets/${id}/activate`, { method: 'PATCH' })
    await fetchCriteriaSets()
  }

  async function handleResetCriteria(id) {
    if (!confirm('Сбросить к дефолтной версии? Все изменения будут потеряны.')) return
    const res = await fetch(`/api/config/criteria-sets/${id}/reset`, { method: 'PATCH' })
    if (!res.ok) { const d = await res.json(); alert(d.detail); return }
    await fetchCriteriaSets()
    if (criteriaForm?.id === id) setCriteriaForm(null)
  }

  async function handleDeleteCriteria(c) {
    if (!confirm(`Удалить набор «${c.name}»?`)) return
    await fetch(`/api/config/criteria-sets/${c.id}`, { method: 'DELETE' })
    await fetchCriteriaSets()
    if (criteriaForm?.id === c.id) setCriteriaForm(null)
  }

  async function handleSaveCriteria() {
    const { id, name, content } = criteriaForm
    if (!name.trim() || !content.trim()) { setCriteriaError('Заполните название и содержимое'); return }
    setCriteriaSaving(true); setCriteriaError(null)
    try {
      let res
      if (id === 'new') {
        res = await fetch('/api/config/criteria-sets', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, content }),
        })
      } else {
        res = await fetch(`/api/config/criteria-sets/${id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, content }),
        })
      }
      if (!res.ok) { const d = await res.json(); setCriteriaError(d.detail || 'Ошибка'); return }
      setCriteriaForm(null)
      await fetchCriteriaSets()
    } finally { setCriteriaSaving(false) }
  }

  return (
    <div className="page" style={{ maxWidth: 760 }}>
      <h1 className="page-title">Настройки</h1>
      <p className="page-subtitle">Перед началом работы настройте подключение к LLM и выберите критерии оценки документа.</p>

      {/* Модели */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Модели</h2>
          <button className="btn btn-primary btn-sm" onClick={openAddForm}>+ Добавить</button>
        </div>

        {loading ? (
          <p style={{ color: 'var(--color-text-secondary)' }}>Загрузка…</p>
        ) : error ? (
          <p style={{ color: 'var(--color-red)' }}>{error}</p>
        ) : models.length === 0 ? (
          <p style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>Нет моделей. Добавьте первую.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {models.map(m => (
              <div
                key={m.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 14px',
                  border: `1px solid ${m.model_id === activeModelId ? 'var(--color-primary)' : 'var(--color-border)'}`,
                  borderRadius: 8,
                  background: m.model_id === activeModelId ? '#eff6ff' : 'var(--color-surface)',
                  cursor: 'pointer',
                }}
                onClick={() => handleSetActive(m.model_id)}
              >
                <input type="radio" name="active_model" checked={m.model_id === activeModelId}
                  onChange={() => handleSetActive(m.model_id)}
                  style={{ accentColor: 'var(--color-primary)', flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13.5 }}>{m.name}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--color-text-secondary)', marginTop: 2, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <span>{m.model_id}</span>
                    <span style={{ color: 'var(--color-border)' }}>·</span>
                    <span>{m.base_url}</span>
                    {m.requires_key && (
                      m.has_key
                        ? <span style={{ color: 'var(--color-green)' }}>🔑 ключ задан</span>
                        : <span style={{ color: 'var(--color-orange)' }}>🔑 ключ не задан</span>
                    )}
                  </div>
                </div>
                <button className="btn btn-secondary btn-sm"
                  onClick={e => { e.stopPropagation(); openEditForm(m) }}
                  style={{ flexShrink: 0 }}>Изменить</button>
                <button className="btn-delete" title="Удалить модель"
                  onClick={e => { e.stopPropagation(); handleDeleteModel(m) }}>✕</button>
              </div>
            ))}
          </div>
        )}

        {showForm && (
          <div style={{ marginTop: 16, padding: 16, background: 'var(--color-bg)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>
              {editingId ? 'Редактировать модель' : 'Добавить модель'}
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label style={labelStyle}>
                <span>Провайдер</span>
                <select className="doc-type-select" value={form.provider}
                  onChange={e => handleProviderChange(e.target.value)} disabled={!!editingId}>
                  {Object.entries(PROVIDER_PRESETS).map(([key, p]) => (
                    <option key={key} value={key}>{p.label}</option>
                  ))}
                </select>
              </label>
              <label style={labelStyle}>
                <span>ID модели <Req /></span>
                <input className="snap-name-input" placeholder="gpt-4o, claude-sonnet-4-6…"
                  value={form.model_id} onChange={e => setForm(f => ({ ...f, model_id: e.target.value }))} />
              </label>
              <label style={{ ...labelStyle, gridColumn: '1 / -1' }}>
                <span>Название <Req /></span>
                <input className="snap-name-input" placeholder="GPT-4o, Claude Sonnet…"
                  value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              </label>
              <label style={{ ...labelStyle, gridColumn: '1 / -1' }}>
                <span>Base URL <Req /></span>
                <input className="snap-name-input" placeholder="https://api.openai.com/v1"
                  value={form.base_url} onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))} />
              </label>
              {form.requires_key && (
                <label style={{ ...labelStyle, gridColumn: '1 / -1' }}>
                  <span>API-ключ{editingId && <span style={{ fontWeight: 400, marginLeft: 4 }}>(оставьте пустым, чтобы не менять)</span>}</span>
                  <input type="password" className="snap-name-input" placeholder="sk-…"
                    value={form.api_key} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} />
                </label>
              )}
              <label style={{ ...labelStyle, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={form.requires_key}
                  onChange={e => setForm(f => ({ ...f, requires_key: e.target.checked }))}
                  style={{ accentColor: 'var(--color-primary)' }} />
                <span style={{ fontSize: 13 }}>Требует API-ключ</span>
              </label>
            </div>
            {formError && <p style={{ color: 'var(--color-red)', fontSize: 12, marginTop: 8 }}>{formError}</p>}
            <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
              <button className="btn btn-primary" onClick={handleSaveModel} disabled={formSaving}>
                {formSaving ? 'Сохранение…' : 'Сохранить'}
              </button>
              <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Отмена</button>
            </div>
          </div>
        )}
      </div>

      {/* Критерии оценки */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Критерии оценки</h2>
          <button className="btn btn-primary btn-sm"
            onClick={() => { setCriteriaForm({ id: 'new', name: '', content: CRITERIA_TEMPLATE }); setCriteriaError(null) }}>
            + Добавить набор
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {criteriaSets.map(c => (
            <div key={c.id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px',
              border: `1px solid ${c.is_active ? 'var(--color-primary)' : 'var(--color-border)'}`,
              borderRadius: 8,
              background: c.is_active ? '#eff6ff' : 'var(--color-surface)',
              cursor: 'pointer',
            }} onClick={() => handleActivateCriteria(c.id)}>
              <input type="radio" name="active_criteria" checked={c.is_active}
                onChange={() => handleActivateCriteria(c.id)}
                style={{ accentColor: 'var(--color-primary)', flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: 13.5 }}>{c.name}</div>
                <div style={{ fontSize: 11.5, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                  {c.is_default && <span style={{ marginRight: 8 }}>По умолчанию</span>}
                  {c.is_active && <span style={{ color: 'var(--color-green)' }}>● Активный</span>}
                </div>
              </div>
              <button className="btn btn-secondary btn-sm"
                onClick={e => { e.stopPropagation(); setCriteriaForm({ id: c.id, name: c.name, content: c.content }); setCriteriaError(null) }}>
                Изменить
              </button>
              {c.is_default && (
                <button className="btn btn-secondary btn-sm"
                  onClick={e => { e.stopPropagation(); handleResetCriteria(c.id) }}
                  title="Сбросить к дефолтной версии">
                  Сбросить
                </button>
              )}
              {!c.is_default && (
                <button className="btn-delete" title="Удалить набор"
                  onClick={e => { e.stopPropagation(); handleDeleteCriteria(c) }}>✕</button>
              )}
            </div>
          ))}
        </div>

        {/* Редактор критериев */}
        {criteriaForm && (
          <div style={{ marginTop: 16, padding: 16, background: 'var(--color-bg)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>
              {criteriaForm.id === 'new' ? 'Новый набор критериев' : `Редактировать: ${criteriaForm.name}`}
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <label style={labelStyle}>
                <span>Название набора <Req /></span>
                <input className="snap-name-input" placeholder="Например: Критерии для API-документации"
                  value={criteriaForm.name}
                  onChange={e => setCriteriaForm(f => ({ ...f, name: e.target.value }))} />
              </label>
              <label style={labelStyle}>
                <span>
                  Критерии (Markdown) <Req />
                  <span style={{ fontWeight: 400, marginLeft: 8 }}>
                    Формат: <code style={{ fontSize: 11, background: '#f3f4f6', padding: '1px 4px', borderRadius: 3 }}>### N.N Название</code> + описание на следующей строке
                  </span>
                </span>
                <textarea
                  value={criteriaForm.content}
                  onChange={e => setCriteriaForm(f => ({ ...f, content: e.target.value }))}
                  rows={18}
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    padding: '8px 10px', fontFamily: 'monospace', fontSize: 12,
                    border: '1px solid var(--color-border)', borderRadius: 7,
                    background: 'var(--color-bg)', color: 'var(--color-text)',
                    resize: 'vertical', lineHeight: 1.6,
                  }}
                />
              </label>
            </div>
            {criteriaError && <p style={{ color: 'var(--color-red)', fontSize: 12, marginTop: 8 }}>{criteriaError}</p>}
            <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
              <button className="btn btn-primary" onClick={handleSaveCriteria} disabled={criteriaSaving}>
                {criteriaSaving ? 'Сохранение…' : 'Сохранить'}
              </button>
              <button className="btn btn-secondary" onClick={() => setCriteriaForm(null)}>Отмена</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const labelStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  fontSize: 12,
  fontWeight: 500,
  color: 'var(--color-text-secondary)',
}

function Req() {
  return <span style={{ color: 'var(--color-red)' }}> *</span>
}
