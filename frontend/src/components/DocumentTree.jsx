import { useState } from 'react'
import '../styles/DocumentTree.css'

export default function DocumentTree({ sections, onIncludeToggle, selectedId, onSelect }) {
  if (!sections || sections.length === 0) {
    return <p style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>Разделы не найдены</p>
  }

  const tree = buildTree(sections)

  return (
    <div className="doc-tree">
      {tree.map(node => (
        <TreeNode key={node.id} node={node} onIncludeToggle={onIncludeToggle} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </div>
  )
}

function TreeNode({ node, depth = 0, onIncludeToggle, selectedId, onSelect }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = node.children && node.children.length > 0
  const isSelected = node.id === selectedId
  const isSelectable = node.classification === 'instruction' || node.classification === 'possible'

  return (
    <div className="tree-node">
      <div
        className={`tree-node__row${hasChildren ? ' tree-node__row--expandable' : ''}${!node.include_in_evaluation ? ' tree-node__row--excluded' : ''}${isSelected ? ' tree-node__row--selected' : ''}`}
        onClick={() => {
          if (hasChildren) setExpanded(e => !e)
          if (isSelectable && onSelect) onSelect(node)
        }}
        style={{ cursor: isSelectable ? 'pointer' : undefined }}
      >
        <span className="tree-node__indent" style={{ width: depth * 18 + 'px' }} />

        <span className="tree-node__toggle">
          {hasChildren ? (expanded ? '▾' : '▸') : '·'}
        </span>

        <span className="tree-node__title" title={node.title}>
          {node.title}
        </span>

        <span className="tree-node__badges">
          {/* Номер страницы */}
          {node.page_number && (
            <span className="badge badge-gray">стр. {node.page_number}</span>
          )}

          {/* Классификация */}
          {node.classification === 'instruction' && (
            <span className="badge badge-blue" title="Все три признака инструкции">инструкция</span>
          )}
          {node.classification === 'possible' && (
            <span className="badge badge-yellow" title="Один или два признака инструкции">возможная</span>
          )}

          {/* Цвет оценки */}
          {node.color && (
            <span className={`badge badge-${node.color}`} title="Результат оценки">
              {colorEmoji(node.color)}
            </span>
          )}

          {/* Кнопка включения/исключения — только для инструкций и возможных */}
          {(node.classification === 'instruction' || node.classification === 'possible') && onIncludeToggle && (
            <button
              className={`include-btn${node.include_in_evaluation ? ' include-btn--on' : ' include-btn--off'}`}
              title={node.include_in_evaluation ? 'Исключить из оценки' : 'Включить в оценку'}
              onClick={e => { e.stopPropagation(); onIncludeToggle(node.id, !node.include_in_evaluation) }}
            >
              {node.include_in_evaluation ? '✓' : '✗'}
            </button>
          )}
        </span>
      </div>

      {hasChildren && expanded && (
        <div className="tree-node__children">
          {node.children.map(child => (
            <TreeNode key={child.id} node={child} depth={depth + 1} onIncludeToggle={onIncludeToggle} selectedId={selectedId} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  )
}

function buildTree(sections) {
  const roots = []
  const stack = []

  for (const section of sections) {
    const node = { ...section, children: [] }
    const level = section.level || 1

    while (stack.length > 0 && stack[stack.length - 1].level >= level) {
      stack.pop()
    }

    if (stack.length === 0) {
      roots.push(node)
    } else {
      stack[stack.length - 1].children.push(node)
    }

    stack.push(node)
  }

  return roots
}

function colorEmoji(color) {
  return { green: '🟢', yellow: '🟡', orange: '🟠', red: '🔴' }[color] || color
}
