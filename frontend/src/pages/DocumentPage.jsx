import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import '../styles/DocumentPage.css'

const ALLOWED_EXT = ['.pdf', '.docx', '.md', '.txt']

export default function DocumentPage() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)

  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [conflict, setConflict] = useState(null)

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
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
      setError(`Формат «${ext}» не поддерживается. Разрешены: ${ALLOWED_EXT.join(', ')}`)
      return
    }
    setError(null)
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/documents/upload', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка при загрузке файла'); return }
      if (data.conflict) {
        setConflict({ filename: data.filename, existingId: data.existing_id, pendingFile: file })
        return
      }
      navigate(`/results/${data.id}`)
    } catch { setError('Не удалось связаться с сервером') }
    finally { setUploading(false) }
  }

  async function handleReplaceConfirm() {
    const { existingId, pendingFile } = conflict
    setConflict(null)
    setUploading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', pendingFile)
      const res = await fetch(`/api/documents/upload/replace/${existingId}`, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Ошибка при замене файла'); return }
      navigate(`/results/${data.id}`)
    } catch { setError('Не удалось связаться с сервером') }
    finally { setUploading(false) }
  }

  return (
    <div className="page">
      <h1 className="page-title">Загрузка документа</h1>
      <p className="page-subtitle">Поддерживаемые форматы: PDF, DOCX, MD, TXT</p>

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

      {error && <div className="alert alert-error">⚠️ {error}</div>}

      {conflict && (
        <div className="modal-overlay">
          <div className="modal">
            <h2 className="modal__title">Файл уже загружен</h2>
            <p className="modal__text">
              Документ <strong>«{conflict.filename}»</strong> уже есть в системе.
              Заменить его новой версией? Все результаты оценки будут удалены.
            </p>
            <div className="modal__actions">
              <button className="btn btn-secondary" onClick={() => setConflict(null)}>Отмена</button>
              <button className="btn btn-danger" onClick={handleReplaceConfirm}>Заменить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
