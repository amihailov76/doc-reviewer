import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDocument } from '../context/DocumentContext'
import '../styles/SnapshotsPage.css'

const COLOR_EMOJI = { green: '🟢', yellow: '🟡', orange: '🟠', red: '🔴' }
const CHANGE_LABEL = {
  improved:  { icon: '↑', label: 'Улучшилось',     cls: 'improved' },
  degraded:  { icon: '↓', label: 'Ухудшилось',     cls: 'degraded' },
  unchanged: { icon: '=', label: 'Без изменений',   cls: 'unchanged' },
  new:       { icon: '+', label: 'Новый раздел',    cls: 'new' },
  removed:   { icon: '−', label: 'Удалён',          cls: 'removed' },
}

export default function SnapshotsPage() {
  const navigate = useNavigate()
  const { currentDoc, hasEvaluations } = useDocument()

  // Группы
  const [groups, setGroups] = useState([])
  const [selectedGroupId, setSelectedGroupId] = useState(null)
  const [newGroupName, setNewGroupName] = useState('')
  const [creatingGroup, setCreatingGroup] = useState(false)
  const [showNewGroup, setShowNewGroup] = useState(false)

  // Снимки выбранной группы
  const [snapshots, setSnapshots] = useState([])

  // Промежуточные снимки текущего документа
  const [partialSnapshots, setPartialSnapshots] = useState([])
  const [selectedPartialIds, setSelectedPartialIds] = useState(new Set())

  // Сохранение снимка
  const [savingName, setSavingName] = useState('')
  const [saving, setSaving] = useState(false)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [isPartialSave, setIsPartialSave] = useState(false)

  // Диалог слияния
  const [showMergeDialog, setShowMergeDialog] = useState(false)
  const [mergeName, setMergeName] = useState('')
  const [mergeGroupId, setMergeGroupId] = useState('')
  const [merging, setMerging] = useState(false)
  const [mergeSuccess, setMergeSuccess] = useState(null) // { id, name, group_id }
  const [assignGroupId, setAssignGroupId] = useState('')
  const [assignRole, setAssignRole] = useState('current')
  const [assigning, setAssigning] = useState(false)

  // Сравнение
  const [snapA, setSnapA] = useState('')
  const [snapB, setSnapB] = useState('current')
  const [comparison, setComparison] = useState(null)
  const [showOnlyChanged, setShowOnlyChanged] = useState(false)
  const [loadingCompare, setLoadingCompare] = useState(false)

  const [error, setError] = useState(null)

  // ── Группы ─────────────────────────────────────────────────────────────────

  useEffect(() => { loadGroups() }, [])

  useEffect(() => {
    if (!selectedGroupId) { setSnapshots([]); return }
    loadSnapshots(selectedGroupId)
    setComparison(null)
  }, [selectedGroupId])

  // Загружаем промежуточные снимки при смене документа
  useEffect(() => {
    if (currentDoc) loadPartialSnapshots(currentDoc.id)
    else setPartialSnapshots([])
  }, [currentDoc?.id])

  async function loadGroups() {
    const res = await fetch('/api/groups/')
    const data = await res.json()
    setGroups(data)
    if (data.length > 0 && !selectedGroupId) setSelectedGroupId(data[0].id)
  }

  async function loadSnapshots(groupId) {
    const res = await fetch(`/api/groups/${groupId}/snapshots`)
    const data = await res.json()
    setSnapshots(data)
    const baseline = data.find(s => s.role === 'baseline')
    if (baseline) setSnapA(String(baseline.id))
  }

  async function loadPartialSnapshots(docId) {
    try {
      const res = await fetch(`/api/snapshots/document/${docId}/partial`)
      if (res.ok) setPartialSnapshots(await res.json())
    } catch { /* не критично */ }
  }

  async function handleCreateGroup() {
    const name = newGroupName.trim()
    if (!name) return
    setCreatingGroup(true)
    try {
      const res = await fetch('/api/groups/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка создания группы'); return }
      setNewGroupName('')
      setShowNewGroup(false)
      await loadGroups()
      setSelectedGroupId(data.id)
    } finally { setCreatingGroup(false) }
  }

  async function handleDeleteGroup(groupId) {
    if (!confirm('Удалить группу и все её снимки?')) return
    await fetch(`/api/groups/${groupId}`, { method: 'DELETE' })
    await loadGroups()
    if (selectedGroupId === groupId) setSelectedGroupId(null)
  }

  // ── Снимки ─────────────────────────────────────────────────────────────────

  async function handleSaveSnapshot() {
    if (!currentDoc) return
    setSaving(true); setError(null)
    try {
      const name = savingName.trim() || currentDoc.filename
      const body = { name, is_partial: isPartialSave }
      if (!isPartialSave) {
        if (!selectedGroupId) { setError('Выберите продуктовую группу'); return }
        body.group_id = selectedGroupId
        body.role = 'current'
      }
      const res = await fetch(`/api/snapshots/document/${currentDoc.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка при сохранении снимка'); return }
      setSavingName('')
      setShowSaveDialog(false)
      setIsPartialSave(false)
      if (isPartialSave) {
        await loadPartialSnapshots(currentDoc.id)
      } else {
        await loadSnapshots(selectedGroupId)
      }
    } finally { setSaving(false) }
  }

  async function handleSaveBaseline() {
    if (!currentDoc || !selectedGroupId) return
    setSaving(true); setError(null)
    try {
      const name = savingName.trim() || currentDoc.filename
      const res = await fetch(`/api/snapshots/document/${currentDoc.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, role: 'baseline', group_id: selectedGroupId }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка при сохранении снимка'); return }
      setSavingName('')
      setShowSaveDialog(false)
      await loadSnapshots(selectedGroupId)
    } finally { setSaving(false) }
  }

  async function handleDeleteSnapshot(snapshotId) {
    await fetch(`/api/snapshots/${snapshotId}`, { method: 'DELETE' })
    setComparison(null)
    if (selectedGroupId) await loadSnapshots(selectedGroupId)
  }

  async function handleAssignGroup() {
    if (!mergeSuccess || !assignGroupId) return
    setAssigning(true)
    try {
      const res = await fetch(`/api/snapshots/${mergeSuccess.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: parseInt(assignGroupId), role: assignRole }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка при назначении группы'); return }
      setMergeSuccess(null)
      await loadGroups()
      setSelectedGroupId(data.group_id)
      await loadSnapshots(data.group_id)
    } finally { setAssigning(false) }
  }

  async function handleDeletePartial(snapshotId) {
    await fetch(`/api/snapshots/${snapshotId}`, { method: 'DELETE' })
    setSelectedPartialIds(prev => { const s = new Set(prev); s.delete(snapshotId); return s })
    if (currentDoc) await loadPartialSnapshots(currentDoc.id)
  }

  function handleExportSnapshotXls(snapshotId, snapshotName) {
    window.location.href = `/api/snapshots/${snapshotId}/export`
  }

  // ── Промежуточные снимки — выбор ───────────────────────────────────────────

  function togglePartialSelect(id) {
    setSelectedPartialIds(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  // ── Слияние промежуточных снимков ─────────────────────────────────────────

  async function handleMerge() {
    if (selectedPartialIds.size === 0) return
    setMerging(true); setError(null)
    try {
      const body = {
        snapshot_ids: Array.from(selectedPartialIds),
        name: mergeName.trim() || (currentDoc?.filename + ' (объединённый)'),
        role: 'current',
      }
      if (mergeGroupId) body.group_id = parseInt(mergeGroupId)
      const res = await fetch('/api/snapshots/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка при объединении снимков'); return }
      setShowMergeDialog(false)
      setMergeName('')
      setMergeGroupId('')
      setSelectedPartialIds(new Set())
      setMergeSuccess({ id: data.id, name: data.name, group_id: data.group_id })
      setAssignGroupId('')
      setAssignRole('current')
      // Перезагружаем промежуточные снимки
      if (currentDoc) await loadPartialSnapshots(currentDoc.id)
      // Если снимок попал в группу — переключаемся на неё
      if (data.group_id) {
        await loadGroups()
        setSelectedGroupId(data.group_id)
        await loadSnapshots(data.group_id)
      }
    } finally { setMerging(false) }
  }

  // ── Сравнение ───────────────────────────────────────────────────────────────

  async function handleCompare() {
    setLoadingCompare(true); setError(null)
    try {
      const params = new URLSearchParams({ snapshot_a: snapA })
      if (snapB !== 'current') {
        params.set('snapshot_b', snapB)
      } else if (currentDoc) {
        params.set('document_id', currentDoc.id)
      } else {
        setError('Загрузите документ для сравнения с текущим состоянием')
        return
      }
      const res = await fetch(`/api/snapshots/compare?${params}`)
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка при сравнении'); return }
      setComparison(data)
    } finally { setLoadingCompare(false) }
  }

  const baseline = snapshots.find(s => s.role === 'baseline')
  const selectedGroup = groups.find(g => g.id === selectedGroupId)

  const diffRows = comparison?.diff.filter(d =>
    showOnlyChanged ? ['degraded', 'improved', 'new', 'removed'].includes(d.change) : true
  ) || []

  const canCompare = snapA && (snapB !== 'current' || (currentDoc && hasEvaluations))

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="page snapshots-page">
      <h1 className="page-title">Сравнение результатов</h1>
      <p className="page-subtitle">
        Сравнивайте результаты проверки документа, чтобы понять, улучшился ли он после обновления.<br />
        Используйте продуктовые группы, чтобы просматривать и сравнивать результаты для документации разных продуктов.
      </p>

      {error && <div className="alert alert-error">⚠️ {error}</div>}

      {/* Промежуточные результаты (видны только при загруженном документе) */}
      {currentDoc && (
        <div className="card partial-section">
          <div className="partial-section__header">
            <div>
              <span className="partial-section__title">🗂 Промежуточные результаты</span>
              <span className="partial-section__doc">— {currentDoc.filename}</span>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {selectedPartialIds.size >= 1 && (
                <button className="btn btn-primary btn-sm" onClick={() => setShowMergeDialog(true)}>
                  ⇒ Объединить выбранные ({selectedPartialIds.size})
                </button>
              )}
              {hasEvaluations && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => { setIsPartialSave(true); setShowSaveDialog(true) }}
                >
                  + Сохранить промежуточный
                </button>
              )}
            </div>
          </div>

          <div className="partial-hint">
            💡 Оцените документ по частям: выберите разделы на вкладке <strong>Оценка</strong>,
            сохраните промежуточный результат, затем объедините несколько промежуточных в итоговый снимок.
          </div>

          {partialSnapshots.length === 0 ? (
            <p className="partial-section__empty">
              Нет промежуточных результатов.
              {hasEvaluations
                ? ' Оцените часть документа и нажмите «Сохранить промежуточный».'
                : ' Сначала выполните оценку на вкладке Оценка.'}
            </p>
          ) : (
            <div className="partial-list">
              {partialSnapshots.map(s => (
                <div key={s.id} className={`partial-item${selectedPartialIds.has(s.id) ? ' partial-item--selected' : ''}`}>
                  <label className="partial-item__checkbox">
                    <input
                      type="checkbox"
                      checked={selectedPartialIds.has(s.id)}
                      onChange={() => togglePartialSelect(s.id)}
                    />
                  </label>
                  <div className="partial-item__info">
                    <div className="partial-item__name">{s.name}</div>
                    <div className="partial-item__date">{new Date(s.created_at).toLocaleString('ru')}</div>
                  </div>
                  <div className="partial-item__summary">
                    {['green', 'yellow', 'orange', 'red'].map(c =>
                      s.data.summary[c] > 0 && (
                        <span key={c} className="snap-summary-badge">{COLOR_EMOJI[c]} {s.data.summary[c]}</span>
                      )
                    )}
                    <span className="snap-summary-badge snap-summary-badge--total">
                      {s.data.summary.total} разд.
                    </span>
                  </div>
                  <button className="btn-delete" onClick={() => handleDeletePartial(s.id)} title="Удалить">✕</button>
                </div>
              ))}
            </div>
          )}

          {/* Диалог слияния */}
          {showMergeDialog && (
            <div className="merge-dialog">
              <div className="merge-dialog__row">
                <input
                  className="snap-name-input"
                  placeholder="Название итогового снимка"
                  value={mergeName}
                  onChange={e => setMergeName(e.target.value)}
                  autoFocus
                />
                <select
                  className="doc-type-select"
                  value={mergeGroupId}
                  onChange={e => setMergeGroupId(e.target.value)}
                >
                  <option value="">— без группы —</option>
                  {groups.map(g => <option key={g.id} value={g.id}>📁 {g.name}</option>)}
                </select>
                <button className="btn btn-primary" onClick={handleMerge} disabled={merging}>
                  {merging ? 'Объединение…' : 'Объединить'}
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => setShowMergeDialog(false)}>✕</button>
              </div>
              <p className="merge-dialog__hint">
                Из {selectedPartialIds.size} промежуточных результатов будет создан один итоговый снимок.
                При совпадении разделов побеждает последний по времени результат.
              </p>
            </div>
          )}

          {/* Результат слияния: назначение в группу */}
          {mergeSuccess && (
            <div className="merge-result-card">
              <div className="merge-result-card__header">
                <span>✅ Снимок «{mergeSuccess.name}» создан</span>
                <button className="btn-close-banner" onClick={() => setMergeSuccess(null)}>✕</button>
              </div>
              {!mergeSuccess.group_id && (
                <div className="merge-result-card__assign">
                  <span className="merge-result-card__label">Сохранить в группу:</span>
                  <select
                    className="doc-type-select"
                    value={assignGroupId}
                    onChange={e => setAssignGroupId(e.target.value)}
                  >
                    <option value="">— выберите группу —</option>
                    {groups.map(g => <option key={g.id} value={g.id}>📁 {g.name}</option>)}
                  </select>
                  <select
                    className="doc-type-select"
                    value={assignRole}
                    onChange={e => setAssignRole(e.target.value)}
                  >
                    <option value="current">снимок</option>
                    <option value="baseline">★ baseline</option>
                  </select>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleAssignGroup}
                    disabled={assigning || !assignGroupId}
                  >
                    {assigning ? 'Сохранение…' : 'Сохранить'}
                  </button>
                </div>
              )}
              {mergeSuccess.group_id && (
                <p className="merge-result-card__hint">Снимок добавлен в группу — см. список ниже.</p>
              )}
            </div>
          )}

          {/* Диалог сохранения промежуточного снимка */}
          {showSaveDialog && isPartialSave && (
            <div className="card save-dialog">
              <div className="save-dialog__row">
                <input
                  className="snap-name-input"
                  placeholder="Название промежуточного результата"
                  value={savingName}
                  onChange={e => setSavingName(e.target.value)}
                  autoFocus
                />
                <button className="btn btn-primary" onClick={handleSaveSnapshot} disabled={saving}>
                  Сохранить промежуточный
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => { setShowSaveDialog(false); setIsPartialSave(false) }}>✕</button>
              </div>
              <p className="save-dialog__hint">
                Промежуточный результат сохраняет только оценённые разделы. Позже его можно объединить с другими промежуточными результатами.
              </p>
            </div>
          )}
        </div>
      )}

      <div className="snapshots-layout">

        {/* Левая панель — группы */}
        <div className="groups-panel">
          <div className="groups-panel__header">
            <span className="groups-panel__title">Продуктовые группы</span>
            <button className="btn btn-primary btn-sm" onClick={() => setShowNewGroup(v => !v)}>+ Новая</button>
          </div>

          {showNewGroup && (
            <div className="new-group-form">
              <input
                className="snap-name-input"
                placeholder="Название группы"
                value={newGroupName}
                onChange={e => setNewGroupName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleCreateGroup()}
                autoFocus
              />
              <button className="btn btn-primary btn-sm" onClick={handleCreateGroup} disabled={creatingGroup || !newGroupName.trim()}>
                Создать
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowNewGroup(false)}>✕</button>
            </div>
          )}

          <div className="groups-list">
            {groups.length === 0 && (
              <p className="groups-empty">Нет групп. Создайте первую группу для сохранения снимков.</p>
            )}
            {groups.map(g => (
              <div
                key={g.id}
                className={`group-item${g.id === selectedGroupId ? ' group-item--active' : ''}`}
                onClick={() => setSelectedGroupId(g.id)}
              >
                <div className="group-item__name">{g.name}</div>
                <div className="group-item__meta">{g.snapshot_count} снимков</div>
                <button
                  className="btn-delete btn-delete--sm"
                  title="Удалить группу"
                  onClick={e => { e.stopPropagation(); handleDeleteGroup(g.id) }}
                >✕</button>
              </div>
            ))}
          </div>
        </div>

        {/* Правая панель — снимки группы */}
        <div className="snapshots-content">
          {!selectedGroupId ? (
            <div className="card snapshots-empty">
              <p>Выберите группу или создайте новую</p>
            </div>
          ) : (
            <>
              {/* Шапка группы */}
              <div className="card group-header">
                <div className="group-header__left">
                  <h2 className="group-header__name">{selectedGroup?.name}</h2>
                  <span className="group-header__meta">{snapshots.length} снимков</span>
                </div>
                <div className="group-header__right">
                  {currentDoc && hasEvaluations && (
                    <button className="btn btn-primary btn-sm" onClick={() => { setIsPartialSave(false); setShowSaveDialog(v => !v) }}>
                      + Сохранить снимок
                    </button>
                  )}
                  {currentDoc && !hasEvaluations && (
                    <span className="snap-hint">Выполните оценку, чтобы сохранить снимок</span>
                  )}
                  {!currentDoc && (
                    <button className="link-btn" onClick={() => navigate('/evaluation')}>
                      Загрузите документ на вкладке Оценка →
                    </button>
                  )}
                </div>
              </div>

              {/* Диалог сохранения итогового снимка */}
              {showSaveDialog && !isPartialSave && (
                <div className="card save-dialog">
                  <div className="save-dialog__row">
                    <input
                      className="snap-name-input"
                      placeholder={`Название снимка (по умолч.: ${currentDoc?.filename})`}
                      value={savingName}
                      onChange={e => setSavingName(e.target.value)}
                    />
                    <button className="btn btn-primary" onClick={handleSaveBaseline} disabled={saving}>
                      ★ Сохранить как baseline
                    </button>
                    <button className="btn btn-secondary" onClick={handleSaveSnapshot} disabled={saving}>
                      Сохранить снимок
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setShowSaveDialog(false)}>✕</button>
                  </div>
                </div>
              )}

              {/* Список итоговых снимков */}
              {snapshots.length === 0 ? (
                <div className="card snapshots-empty">
                  <p>В этой группе пока нет снимков.</p>
                </div>
              ) : (
                <div className="card">
                  <div className="snap-list">
                    {snapshots.map(s => (
                      <div key={s.id} className={`snap-item${s.role === 'baseline' ? ' snap-item--baseline' : ''}`}>
                        <div className="snap-item__header">
                          <div className="snap-item__info">
                            <span className="snap-item__role">{s.role === 'baseline' ? '★ baseline' : 'снимок'}</span>
                            <div>
                              <div className="snap-item__name">{s.name}</div>
                              {s.document_filename && s.document_filename !== s.name && (
                                <div className="snap-item__file">📄 {s.document_filename}</div>
                              )}
                              <div className="snap-item__date">{new Date(s.created_at).toLocaleString('ru')}</div>
                            </div>
                          </div>
                          <div className="snap-item__actions">
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleExportSnapshotXls(s.id, s.name)}
                              title="Скачать XLS"
                            >⬇ XLS</button>
                            <button className="btn-delete" onClick={() => handleDeleteSnapshot(s.id)} title="Удалить снимок">✕</button>
                          </div>
                        </div>
                        <div className="snap-item__body">
                          <div className="snap-item__summary">
                            {['green', 'yellow', 'orange', 'red'].map(c =>
                              s.data.summary[c] > 0 && (
                                <span key={c} className="snap-summary-badge">{COLOR_EMOJI[c]} {s.data.summary[c]}</span>
                              )
                            )}
                            <span className="snap-summary-badge snap-summary-badge--total">Всего: {s.data.summary.total}</span>
                          </div>
                          {s.data.integral && (
                            <div className="snap-integral">
                              <span className={`snap-integral__grade snap-integral__grade--${s.data.integral.grade.toLowerCase()}`}>
                                {s.data.integral.grade}
                              </span>
                              <span className={`snap-integral__verdict snap-integral__verdict--${s.data.integral.grade.toLowerCase()}`}>
                                {s.data.integral.grade_label}
                              </span>
                              <span className="snap-integral__score">{s.data.integral.score}%</span>
                              {s.data.integral.top_violations?.length > 0 && (
                                <span className="snap-integral__violations">
                                  нарушения: {s.data.integral.top_violations.map(v => v.criterion_id).join(', ')}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Панель сравнения */}
                  {snapshots.length >= 1 && (
                    <div className="compare-panel">
                      <div className="compare-panel__selectors">
                        <div className="compare-panel__field">
                          <label className="compare-panel__label">Снимок A</label>
                          <select className="doc-type-select" value={snapA} onChange={e => { setSnapA(e.target.value); setComparison(null) }}>
                            <option value="">— выберите —</option>
                            {snapshots.map(s => (
                              <option key={s.id} value={String(s.id)}>
                                {s.role === 'baseline' ? '★ ' : ''}{s.name} · {new Date(s.created_at).toLocaleDateString('ru')}
                              </option>
                            ))}
                          </select>
                        </div>
                        <span className="compare-panel__arrow">⇄</span>
                        <div className="compare-panel__field">
                          <label className="compare-panel__label">Снимок B</label>
                          <select className="doc-type-select" value={snapB} onChange={e => { setSnapB(e.target.value); setComparison(null) }}>
                            <option value="current">Текущее состояние</option>
                            {snapshots.map(s => (
                              <option key={s.id} value={String(s.id)}>
                                {s.role === 'baseline' ? '★ ' : ''}{s.name} · {new Date(s.created_at).toLocaleDateString('ru')}
                              </option>
                            ))}
                          </select>
                        </div>
                        <button className="btn btn-primary compare-panel__btn" onClick={handleCompare} disabled={loadingCompare || !canCompare || !snapA}>
                          {loadingCompare ? 'Сравнение…' : 'Сравнить'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Результаты сравнения */}
              {comparison && (
                <div className="card comparison">
                  <div className="comparison__header">
                    <div>
                      <h2 className="comparison__title">Результаты сравнения</h2>
                      <p className="comparison__subtitle">
                        <strong>{comparison.source_a.name}</strong>
                        {comparison.source_a.created_at && ` · ${new Date(comparison.source_a.created_at).toLocaleDateString('ru')}`}
                        {' ⇄ '}
                        <strong>{comparison.source_b.name}</strong>
                        {comparison.source_b.created_at && ` · ${new Date(comparison.source_b.created_at).toLocaleDateString('ru')}`}
                      </p>
                    </div>
                    <div className="comparison__stats">
                      {comparison.stats.degraded > 0 && <span className="stat-badge stat-badge--degraded">↓ {comparison.stats.degraded} ухудшилось</span>}
                      {comparison.stats.improved > 0 && <span className="stat-badge stat-badge--improved">↑ {comparison.stats.improved} улучшилось</span>}
                      {comparison.stats.new > 0 && <span className="stat-badge stat-badge--new">+ {comparison.stats.new} новых</span>}
                      {comparison.stats.removed > 0 && <span className="stat-badge stat-badge--removed">− {comparison.stats.removed} удалено</span>}
                      {comparison.stats.unchanged > 0 && <span className="stat-badge stat-badge--unchanged">= {comparison.stats.unchanged} без изменений</span>}
                    </div>
                  </div>

                  <label className="snap-filter">
                    <input type="checkbox" checked={showOnlyChanged} onChange={e => setShowOnlyChanged(e.target.checked)} />
                    Показывать только изменившиеся разделы
                  </label>

                  <div className="diff-table-wrap">
                    <table className="diff-table">
                      <thead>
                        <tr>
                          <th>Раздел</th>
                          <th className="diff-th--snap" title={comparison.source_a.name}>
                            {comparison.source_a.name}
                          </th>
                          <th className="diff-th--snap" title={comparison.source_b.name}>
                            {comparison.source_b.name}
                          </th>
                          <th>Изменение</th>
                          <th>Стр.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {diffRows.map((row, i) => {
                          const ch = CHANGE_LABEL[row.change]
                          return (
                            <tr key={i} className={`diff-row diff-row--${ch.cls}`}>
                              <td className="diff-row__title" title={row.title}>{row.title}</td>
                              <td className="diff-row__color">{row.color_a ? COLOR_EMOJI[row.color_a] : '—'}</td>
                              <td className="diff-row__color">{row.change !== 'removed' ? COLOR_EMOJI[row.color] : '—'}</td>
                              <td><span className={`change-badge change-badge--${ch.cls}`}>{ch.icon} {ch.label}</span></td>
                              <td className="diff-row__page">{row.page_number || '—'}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
