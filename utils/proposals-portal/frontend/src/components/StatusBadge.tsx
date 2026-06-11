import { Badge } from '@mantine/core'
import { STATUS_BADGE_COLORS, STATUS_LABELS, type ProposalStatus } from '../types'

interface StatusBadgeProps {
  status: ProposalStatus
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const color = STATUS_BADGE_COLORS[status] ?? 'gray'
  const label = STATUS_LABELS[status] ?? status

  return (
    <Badge
      size="sm"
      variant="light"
      color={color}
      className={className}
      style={{ textTransform: 'none', fontWeight: 600 }}
    >
      {label}
    </Badge>
  )
}
