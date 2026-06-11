import { Badge } from '@mantine/core'
import { TYPE_BADGE_COLORS, TYPE_LABELS, type ProposalType } from '../types'

interface TypeBadgeProps {
  type: ProposalType
  className?: string
}

export function TypeBadge({ type, className }: TypeBadgeProps) {
  const color = TYPE_BADGE_COLORS[type] ?? 'gray'
  const label = TYPE_LABELS[type] ?? type

  return (
    <Badge
      size="sm"
      variant="filled"
      color={color}
      className={className}
      style={{ textTransform: 'none', fontWeight: 600 }}
    >
      {label}
    </Badge>
  )
}
