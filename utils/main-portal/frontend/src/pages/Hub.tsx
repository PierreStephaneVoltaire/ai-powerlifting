import { useEffect } from 'react'
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
      <div className="p-4 rounded-lg bg-destructive/10 border border-destructive text-destructive">
        <p className="font-medium">Failed to load hub status</p>
        <p className="text-sm mt-1">{error}</p>
      </div>
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
    <div className="space-y-6">
      {/* Signal Strip */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-2">Current Signals</h2>
        <SignalStrip signals={data?.signals ?? null} loading={loading} />
      </section>

      {/* Snapshot Bar */}
      <section>
        <SnapshotBar finance={data?.finance ?? null} health={data?.health ?? null} loading={loading} />
      </section>

      {/* Portal Cards Grid */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">Portals</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
        </div>
      </section>

      {/* Alerts */}
      <section>
        <AlertsList alerts={data?.alerts ?? []} loading={loading} />
      </section>

      {/* Last Updated */}
      {data?.computed_at && (
        <p className="text-xs text-muted-foreground text-right">
          Updated {formatRelativeTime(data.computed_at)}
        </p>
      )}
    </div>
  )
}
