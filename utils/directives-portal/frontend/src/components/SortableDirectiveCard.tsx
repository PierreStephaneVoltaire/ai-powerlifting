import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Directive } from '../api/client'
import { DirectiveCard } from './DirectiveCard'

interface SortableDirectiveCardProps {
  directive: Directive
  onEdit: (d: Directive) => void
  onDelete: (d: Directive) => void
  isOperator: boolean
  reorderMode: boolean
  originalAlpha: number
  originalBeta: number
  canMove: boolean
  onMoveTier: (origAlpha: number, origBeta: number, direction: 'up' | 'down') => void
  currentAlpha: number
}

export function SortableDirectiveCard({
  directive,
  onEdit,
  onDelete,
  isOperator,
  reorderMode,
  originalAlpha,
  originalBeta,
  canMove,
  onMoveTier,
  currentAlpha,
}: SortableDirectiveCardProps) {
  const stableId = `${originalAlpha}-${originalBeta}`

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: stableId, disabled: !canMove })

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 999 : 'auto',
    position: 'relative' as const,
  }

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <DirectiveCard
        directive={directive}
        onEdit={onEdit}
        onDelete={onDelete}
        isOperator={isOperator}
        reorderMode={reorderMode}
        originalAlpha={originalAlpha}
        originalBeta={originalBeta}
        dragHandleProps={canMove ? listeners : undefined}
        canMove={canMove}
        onMoveTier={onMoveTier}
        currentAlpha={currentAlpha}
      />
    </div>
  )
}
