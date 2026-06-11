import { useState, useEffect } from 'react'
import { Box, Button, Center, Group, Loader, Stack, Text } from '@mantine/core'
import { Plus, Inbox } from 'lucide-react'
import { KanbanColumn } from '../components/KanbanColumn'
import { FilterBar } from '../components/FilterBar'
import { NewProposalModal } from '../components/NewProposalModal'
import { useProposalsStore } from '../store/proposalsStore'
import type { ProposalFilters } from '../types'

const COLUMN_META = {
  pending: {
    title: 'Pending',
    headerColor: '#f59e0b',
    headerBg: 'rgba(245, 158, 11, 0.08)',
    headerBorder: 'rgba(245, 158, 11, 0.4)',
  },
  approved: {
    title: 'Approved',
    headerColor: '#22c55e',
    headerBg: 'rgba(34, 197, 94, 0.08)',
    headerBorder: 'rgba(34, 197, 94, 0.4)',
  },
  rejected: {
    title: 'Rejected',
    headerColor: '#ef4444',
    headerBg: 'rgba(239, 68, 68, 0.08)',
    headerBorder: 'rgba(239, 68, 68, 0.4)',
  },
} as const

export default function Board() {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { proposals, loading, filters, loadProposals } = useProposalsStore()

  useEffect(() => {
    loadProposals()
  }, [loadProposals])

  const handleFilterChange = (newFilters: ProposalFilters) => {
    loadProposals(newFilters)
  }

  // Defensive: the store initializes `proposals` to [], but treat undefined / null
  // as empty too so a transient bad API payload never crashes the page.
  const safeProposals = Array.isArray(proposals) ? proposals : []
  const total = safeProposals.length
  const pendingCount = safeProposals.filter((p) => p.status === 'pending').length
  const approvedCount = safeProposals.filter((p) => p.status === 'approved').length
  const rejectedCount = safeProposals.filter((p) => p.status === 'rejected').length

  return (
    <Stack gap="md">
      {/* Page header */}
      <Box className="if-page-header">
        <Box>
          <Text className="if-page-title">Proposal Board</Text>
          <Text className="if-page-subtitle">
            {total} total · {pendingCount} pending · {approvedCount} approved · {rejectedCount} rejected
          </Text>
        </Box>
        <Button
          variant="gradient"
          gradient={{ from: 'blue.6', to: 'blue.4' }}
          leftSection={<Plus size={14} />}
          onClick={() => setIsModalOpen(true)}
        >
          New Proposal
        </Button>
      </Box>

      {/* Filters */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} />

      {/* Loading state */}
      {loading && total === 0 ? (
        <Center py="xl">
          <Stack align="center" gap="xs">
            <Loader size="sm" color="blue" />
            <Text size="sm" c="var(--color-text-secondary)">Loading proposals...</Text>
          </Stack>
        </Center>
      ) : total === 0 ? (
        <Center py="xl">
          <Stack align="center" gap="md" className="if-mock-card" style={{ minWidth: 320 }}>
            <Inbox size={32} color="var(--color-text-secondary)" />
            <Text size="sm" c="var(--color-text-secondary)">No proposals yet</Text>
            <Button
              variant="light"
              color="blue"
              leftSection={<Plus size={14} />}
              onClick={() => setIsModalOpen(true)}
            >
              Create your first proposal
            </Button>
          </Stack>
        </Center>
      ) : (
        <Group gap="md" align="stretch" wrap="wrap">
          <KanbanColumn
            title={COLUMN_META.pending.title}
            status="pending"
            proposals={safeProposals}
            headerColor={COLUMN_META.pending.headerColor}
            headerBg={COLUMN_META.pending.headerBg}
            headerBorder={COLUMN_META.pending.headerBorder}
          />
          <KanbanColumn
            title={COLUMN_META.approved.title}
            status="approved"
            proposals={safeProposals}
            headerColor={COLUMN_META.approved.headerColor}
            headerBg={COLUMN_META.approved.headerBg}
            headerBorder={COLUMN_META.approved.headerBorder}
          />
          <KanbanColumn
            title={COLUMN_META.rejected.title}
            status="rejected"
            proposals={safeProposals}
            headerColor={COLUMN_META.rejected.headerColor}
            headerBg={COLUMN_META.rejected.headerBg}
            headerBorder={COLUMN_META.rejected.headerBorder}
          />
        </Group>
      )}

      <NewProposalModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
    </Stack>
  )
}