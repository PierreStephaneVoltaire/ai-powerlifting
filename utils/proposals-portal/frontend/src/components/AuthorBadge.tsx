import { Badge } from '@mantine/core'
import { Bot, User } from 'lucide-react'
import type { ProposalAuthor } from '../types'

interface AuthorBadgeProps {
  author: ProposalAuthor
  className?: string
}

export function AuthorBadge({ author, className }: AuthorBadgeProps) {
  const isAgent = author === 'agent'
  const Icon = isAgent ? Bot : User
  const color = isAgent ? 'violet' : 'gray'
  const label = isAgent ? 'Agent' : 'You'

  return (
    <Badge
      size="sm"
      variant="light"
      color={color}
      className={className}
      leftSection={<Icon size={11} />}
      style={{ textTransform: 'none', fontWeight: 500 }}
    >
      {label}
    </Badge>
  )
}
