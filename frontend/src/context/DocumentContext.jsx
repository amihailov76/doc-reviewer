import { createContext, useContext, useState, useEffect } from 'react'

const DocumentContext = createContext(null)

export function DocumentProvider({ children }) {
  const [currentDoc, setCurrentDoc] = useState(null)
  const [sections, setSections] = useState([])
  const [selectedSection, setSelectedSection] = useState(null)
  const [progress, setProgress] = useState(null)
  const [summary, setSummary] = useState(null)
  const [hasEvaluations, setHasEvaluations] = useState(false)
  const [criteriaLabels, setCriteriaLabels] = useState({})

  // Загружаем критерии один раз при старте
  useEffect(() => {
    fetch('/api/config/criteria')
      .then(r => r.ok ? r.json() : {})
      .then(data => setCriteriaLabels(data))
      .catch(() => {})
  }, [])

  function clearDocument() {
    setCurrentDoc(null)
    setSections([])
    setSelectedSection(null)
    setProgress(null)
    setSummary(null)
    setHasEvaluations(false)
  }

  return (
    <DocumentContext.Provider value={{
      currentDoc, setCurrentDoc,
      sections, setSections,
      selectedSection, setSelectedSection,
      progress, setProgress,
      summary, setSummary,
      hasEvaluations, setHasEvaluations,
      criteriaLabels,
      clearDocument,
    }}>
      {children}
    </DocumentContext.Provider>
  )
}

export function useDocument() {
  return useContext(DocumentContext)
}
