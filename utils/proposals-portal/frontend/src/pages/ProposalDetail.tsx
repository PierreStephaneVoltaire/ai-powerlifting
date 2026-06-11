import { useParams, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { Box, Button, Center, Loader, Stack, Text } from '@mantine/core'
import { ArrowLeft } from 'lucide-react'
import { ProposalDetailPanel } from '../components/ProposalDetailPanel'
import { useProposalsStore } from '../store/proposalsStore'

export default function ProposalDetail() {
  const { sk } = useParams<{ sk: string }>()
  const navigate = useNavigate()
  const { selectedProposal, loading, error, loadProposal } = useProposalsStore()

  useEffect(() => {
    if (sk) {
      loadProposal(decodeURIComponent(sk))
    }
  }, [sk, loadProposal])

  if (loading && !selectedProposal) {
    return (
      <Center py="xl">
        <Stack align="center" gap="xs">
          <Loader size="md" color="blue" />
          <Text size="sm" c="var(--color-text-secondary)">Loading proposal...</Text>
        </Stack>
      </Center>
    )
  }

  if (error) {
    return (
      <Center py="xl">
        <Stack align="center" gap="sm" className="if-mock-card" style={{ minWidth: 320 }}>
          <Text size="sm" c="var(--status-danger-text)">{error}</Text>
          <Button
            variant="light"
            color="gray"
            leftSection={<ArrowLeft size={14} />}
            onClick={() => navigate('/')}
          >
            Back to Board
          </Button>
        </Stack>
      </Center>
    )
  }

  if (!selectedProposal) {
    return (
      <Center py="xl">
        <Stack align="center" gap="sm" className="if-mock-card" style={{ minWidth: 320 }}>
          <Text size="sm" c="var(--color-text-secondary)">Proposal not found</Text>
          <Button
            variant="light"
            color="gray"
            leftSection={<ArrowLeft size={14} />}
            onClick={() => navigate('/')}
          >
            Back to Board
          </Button>
        </Stack>
      </Center>
    )
  }

  return (
    <Box>
      <ProposalDetailPanel
        proposal={selectedProposal}
        onBack={() => navigate('/')}
      />
    </Box>
  )
}