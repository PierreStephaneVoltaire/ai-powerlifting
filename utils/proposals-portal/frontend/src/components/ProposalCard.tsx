import { useNavigate } from 'react-router-dom'
import { Group, Stack, Text, Box } from '@mantine/core'
import { ChevronRight } from 'lucide-react'
import type { Proposal } from '../types'
import { TypeBadge } from './TypeBadge'
import { AuthorBadge } from './AuthorBadge'
import { formatRelativeTime, truncateText } from '../utils/formatters'

interface ProposalCardProps {
  proposal: Proposal
}

export function ProposalCard({ proposal }: ProposalCardProps) {
  const navigate = useNavigate()

  const handleClick = () => {
    navigate(`/proposal/${encodeURIComponent(proposal.sk)}`)
  }

  return (
    <Box className="if-kanban-card" onClick={handleClick}>
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Group gap={6} wrap="nowrap">
            <TypeBadge type={proposal.type} />
            <AuthorBadge author={proposal.author} />
          </Group>
          <Text size="xs" c="var(--color-text-secondary)" style={{ flexShrink: 0 }}>
            {formatRelativeTime(proposal.created_at)}
          </Text>
        </Group>

        <Text fw={600} size="sm" c="var(--text-primary)" lineClamp={2}>
          {proposal.title}
        </Text>

        <Text size="xs" c="var(--color-text-secondary)" lineClamp={3}>
          {truncateText(proposal.rationale, 140)}
        </Text>

        <Group gap={4} mt={2} c="var(--accent-blue)">
          <Text size="xs" fw={600}>View &amp; decide</Text>
          <ChevronRight size={12} />
        </Group>
      </Stack>
    </Box>
  )
}
