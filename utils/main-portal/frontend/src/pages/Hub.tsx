import { useEffect } from 'react'
import { Stack, SimpleGrid, Text, Box } from '@mantine/core'
import { useHubStore } from '../store/hubStore'
import { PortalCard } from '../components/PortalCard'
import { SignalStrip } from '../components/SignalStrip'
import { SnapshotBar } from '../components/SnapshotBar'
import { AlertsList } from '../components/AlertsList'
import { formatCurrency, formatDaysUntil, formatRelativeTime } from '../utils/formatters'

export function Hub() {
  const { data, loading, error, startPolling, stopPolling } = useHubStore()

  useEffect(() => {
    startPolling(30000) // Refresh every 30 seconds
    return () => stopPolling()
  }, [startPolling, stopPolling])

  if (error) {
    return (
      <Box p="sm" style={{ background: 'var(--status-danger-bg)', border: '0.5px solid var(--status-danger-border)', borderRadius: 'var(--border-radius-lg)' }}>
        <Text fw={500}>Failed to load hub status</Text>
        <Text size="sm" mt={4}>{error}</Text>
      </Box>
    )
  }

  const portalStatus = data?.portal_status || {
    health: 'unreachable' as const,
    finance: 'unreachable' as const,
    diary: 'unreachable' as const,
    proposals: 'unreachable' as const,
    directives: 'unreachable' as const,
  }

  const directivesLines: string[] = data?.portal_status?.directives === 'reachable'
    ? ['Connected', 'CRUD + proxy active']
    : ['Unavailable']

  // Build portal card data
  const healthLines: string[] = data?.health
    ? [
        `${data.health.current_week}${data.health.current_program ? ` of ${data.health.current_program}` : ''}`,
        data.health.days_to_comp !== null
          ? `${formatDaysUntil(data.health.days_to_comp)} to comp`
          : 'No comp scheduled',
      ]
    : ['Unavailable']

  const financeLines: string[] = data?.finance
    ? [
        `Net worth: ${formatCurrency(data.finance.net_worth)}`,
        `Surplus: ${formatCurrency(data.finance.monthly_surplus)}/mo`,
      ]
    : ['Unavailable']

  const diaryLines: string[] = data?.diary
    ? [
        `Score: ${data.diary.latest_score.toFixed(1)}`,
        `${data.diary.active_entry_count} active entries`,
      ]
    : ['Unavailable']

  const proposalsLines: string[] = data?.proposals
    ? [
        `${data.proposals.pending_count} pending`,
        data.proposals.breakdown
          ? `${data.proposals.breakdown.agent} agent · ${data.proposals.breakdown.user} user`
          : '',
        data.proposals.latest_created_at
          ? `Last: ${formatRelativeTime(data.proposals.latest_created_at)}`
          : '',
      ].filter(Boolean)
    : ['Unavailable']

  return (
    <Stack gap="xl">
      {/* Signal Strip */}
      <section>
        <Text size="sm" fw={500} c="var(--text-secondary)" mb={8}>Current Signals</Text>
        <SignalStrip signals={data?.signals ?? null} loading={loading} />
      </section>

      {/* Snapshot Bar */}
      <section>
        <SnapshotBar finance={data?.finance ?? null} health={data?.health ?? null} loading={loading} />
      </section>

      {/* Portal Cards Grid */}
      <section>
        <Text size="sm" fw={500} c="var(--text-secondary)" mb={12}>Portals</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <PortalCard
            name="Health"
            icon="💪"
            href="http://localhost:3001"
            status={portalStatus.health}
            lines={healthLines}
          />
          <PortalCard
            name="Finance"
            icon="💰"
            href="http://localhost:3002"
            status={portalStatus.finance}
            lines={financeLines}
          />
          <PortalCard
            name="Diary"
            icon="📓"
            href="http://localhost:3003"
            status={portalStatus.diary}
            lines={diaryLines}
          />
          <PortalCard
            name="Proposals"
            icon="💡"
            href="http://localhost:3004"
            status={portalStatus.proposals}
            pendingCount={data?.proposals?.pending_count}
            lines={proposalsLines}
          />
          <PortalCard
            name="Directives"
            icon="📜"
            href="https://directives.if-prototype.xyz"
            status={portalStatus.directives}
            lines={directivesLines}
          />
        </SimpleGrid>
      </section>

      {/* Alerts */}
      <section>
        <AlertsList alerts={data?.alerts ?? []} loading={loading} />
      </section>

      {/* Last Updated */}
      {data?.computed_at && (
        <Text size="xs" c="var(--text-muted)" ta="right">
          Updated {formatRelativeTime(data.computed_at)}
        </Text>
      )}
    </Stack>
  )
}
