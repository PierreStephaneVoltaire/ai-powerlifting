import { useState, useEffect } from 'react'
import {
  Box,
  Button,
  Group,
  Stack,
  Text,
  Textarea,
  ActionIcon,
  Tooltip,
  Divider,
} from '@mantine/core'
import { ArrowLeft, Check, Trash2, X } from 'lucide-react'
import { notifications } from '@mantine/notifications'
import { useProposalsStore } from '../store/proposalsStore'
import { TypeBadge } from './TypeBadge'
import { AuthorBadge } from './AuthorBadge'
import { StatusBadge } from './StatusBadge'
import { DirectivePreview } from './DirectivePreview'
import { ImplementationPlan } from './ImplementationPlan'
import { formatDateTime } from '../utils/formatters'
import type { Directive, Proposal } from '../types'

interface ProposalDetailPanelProps {
  proposal: Proposal
  onBack?: () => void
}

export function ProposalDetailPanel({ proposal, onBack }: ProposalDetailPanelProps) {
  const [showRejectInput, setShowRejectInput] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false)
  const [targetDirective, setTargetDirective] = useState<Directive | null>(null)
  const [loadingDirective, setLoadingDirective] = useState(false)

  const {
    approveProposal,
    rejectProposal,
    deleteProposal,
    loadDirective,
    loading,
  } = useProposalsStore()

  useEffect(() => {
    if (proposal.target_id) {
      setLoadingDirective(true)
      loadDirective(proposal.target_id)
        .then(() => {
          const store = useProposalsStore.getState()
          setTargetDirective(store.selectedDirective)
        })
        .catch(() => {
          setTargetDirective(null)
        })
        .finally(() => setLoadingDirective(false))
    } else {
      setTargetDirective(null)
    }
  }, [proposal.target_id, loadDirective])

  const handleApprove = async () => {
    if (!window.confirm('Approve this proposal? This will trigger plan generation.')) return
    try {
      await approveProposal(proposal.sk)
      setIsGeneratingPlan(true)
      notifications.show({ title: 'Approved', message: 'Implementation plan is being generated', color: 'green' })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Approval failed'
      notifications.show({ title: 'Approve failed', message, color: 'red' })
    }
  }

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      setShowRejectInput(true)
      return
    }
    try {
      await rejectProposal(proposal.sk, rejectReason)
      setShowRejectInput(false)
      setRejectReason('')
      notifications.show({ title: 'Rejected', message: 'Proposal has been rejected', color: 'orange' })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Reject failed'
      notifications.show({ title: 'Reject failed', message, color: 'red' })
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Delete this proposal? This cannot be undone.')) return
    try {
      await deleteProposal(proposal.sk)
      notifications.show({ title: 'Deleted', message: 'Proposal removed', color: 'gray' })
      onBack?.()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Delete failed'
      notifications.show({ title: 'Delete failed', message, color: 'red' })
    }
  }

  const isPending = proposal.status === 'pending'
  const isApproved = proposal.status === 'approved'

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Stack gap={6}>
          <Group gap={6}>
            <TypeBadge type={proposal.type} />
            <AuthorBadge author={proposal.author} />
            <StatusBadge status={proposal.status} />
          </Group>
          <Text fw={700} size="xl" c="var(--text-primary)" lh={1.2}>
            {proposal.title}
          </Text>
          <Text size="xs" c="var(--color-text-secondary)">
            Created {formatDateTime(proposal.created_at)}
          </Text>
        </Stack>

        {onBack && (
          <Tooltip label="Back to board">
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              onClick={onBack}
              aria-label="Back to board"
            >
              <ArrowLeft size={18} />
            </ActionIcon>
          </Tooltip>
        )}
      </Group>

      {/* Rationale */}
      <Box className="if-mock-card">
        <Text className="if-card-title" mb={8}>Rationale</Text>
        <Text size="sm" c="var(--text-primary)" style={{ whiteSpace: 'pre-wrap' }}>
          {proposal.rationale}
        </Text>
      </Box>

      {/* Proposed Content */}
      {proposal.content && (
        <Box className="if-mock-card">
          <Text className="if-card-title" mb={8}>Proposed Content</Text>
          <pre className="if-prose-pre">{proposal.content}</pre>
        </Box>
      )}

      {/* Target Directive Context (for rewrite/deprecate) */}
      {proposal.target_id && (
        <Box>
          <Text className="if-card-title" mb={8}>Current Directive</Text>
          <DirectivePreview directive={targetDirective} loading={loadingDirective} />
        </Box>
      )}

      {/* Rejection Reason */}
      {proposal.status === 'rejected' && proposal.rejection_reason && (
        <Box
          p="sm"
          style={{
            background: 'var(--status-danger-bg)',
            border: '0.5px solid var(--status-danger-border)',
            borderRadius: 'var(--border-radius-lg)',
          }}
        >
          <Text className="if-card-title" mb={6} c="var(--status-danger-text)">
            Rejection Reason
          </Text>
          <Text size="sm" c="var(--status-danger-text)">{proposal.rejection_reason}</Text>
        </Box>
      )}

      {/* Implementation Plan */}
      {isApproved && (
        <ImplementationPlan
          plan={proposal.implementation_plan}
          isGenerating={isGeneratingPlan && !proposal.implementation_plan}
        />
      )}

      {/* Actions */}
      {isPending && (
        <Box className="if-mock-card">
          <Text className="if-card-title" mb={10}>Actions</Text>

          {!showRejectInput ? (
            <Group gap="xs">
              <Button
                color="green"
                variant="gradient"
                gradient={{ from: 'green.6', to: 'green.4' }}
                leftSection={<Check size={14} />}
                onClick={handleApprove}
                disabled={loading}
              >
                Approve
              </Button>
              <Button
                color="red"
                variant="light"
                leftSection={<X size={14} />}
                onClick={() => setShowRejectInput(true)}
                disabled={loading}
              >
                Reject
              </Button>
              <Button
                color="gray"
                variant="subtle"
                leftSection={<Trash2 size={14} />}
                onClick={handleDelete}
                disabled={loading}
              >
                Delete
              </Button>
            </Group>
          ) : (
            <Stack gap="xs">
              <Textarea
                placeholder="Enter rejection reason..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.currentTarget.value)}
                autosize
                minRows={2}
                autoFocus
              />
              <Group gap="xs" justify="flex-end">
                <Button
                  variant="subtle"
                  color="gray"
                  onClick={() => {
                    setShowRejectInput(false)
                    setRejectReason('')
                  }}
                >
                  Cancel
                </Button>
                <Button
                  color="red"
                  variant="gradient"
                  gradient={{ from: 'red.6', to: 'red.4' }}
                  onClick={handleReject}
                  disabled={loading || !rejectReason.trim()}
                >
                  Confirm Rejection
                </Button>
              </Group>
            </Stack>
          )}
        </Box>
      )}

      {/* Resolution Info */}
      {proposal.resolved_at && (
        <>
          <Divider color="var(--color-border-tertiary)" />
          <Text size="xs" c="var(--color-text-secondary)">
            Resolved {formatDateTime(proposal.resolved_at)} by {proposal.resolved_by}
          </Text>
        </>
      )}
    </Stack>
  )
}
