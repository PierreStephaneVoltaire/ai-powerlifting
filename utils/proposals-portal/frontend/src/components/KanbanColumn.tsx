import { Box, Group, Text } from '@mantine/core'
import type { Proposal, ProposalStatus } from '../types'
import { ProposalCard } from './ProposalCard'

interface KanbanColumnProps {
  title: string
  status: ProposalStatus
  proposals: Proposal[]
  headerColor: string
  headerBg: string
  headerBorder: string
}

export function KanbanColumn({
  title,
  status,
  proposals,
  headerColor,
  headerBg,
  headerBorder,
}: KanbanColumnProps) {
  const filteredProposals = proposals.filter((p) => p.status === status)

  return (
    <div className="if-kanban-column">
      <div
        className="if-kanban-column-header"
        style={{ background: headerBg, borderBottom: `2px solid ${headerBorder}` }}
      >
        <Group gap={8}>
          <Box style={{ width: 8, height: 8, borderRadius: '50%', background: headerColor, flexShrink: 0 }} />
          <Text fw={700} size="sm" c="var(--text-primary)">{title}</Text>
        </Group>
        <Text
          size="xs"
          fw={600}
          ff="'IBM Plex Mono', monospace"
          c="var(--text-secondary)"
          style={{ minWidth: 22, textAlign: 'center' }}
        >
          {filteredProposals.length}
        </Text>
      </div>

      <div className="if-kanban-column-body">
        {filteredProposals.length === 0 ? (
          <Text size="xs" c="var(--color-text-secondary)" ta="center" py="lg">
            No proposals
          </Text>
        ) : (
          filteredProposals.map((proposal) => (
            <ProposalCard key={proposal.sk} proposal={proposal} />
          ))
        )}
      </div>
    </div>
  )
}
