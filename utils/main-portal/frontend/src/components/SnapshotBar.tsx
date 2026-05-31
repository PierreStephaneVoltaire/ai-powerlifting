import { Group, Text, Box } from '@mantine/core'
import type { FinanceData, HealthData } from '../types'
import { formatCurrency, formatDaysUntil } from '../utils/formatters'

interface SnapshotBarProps {
  finance: FinanceData | null
  health: HealthData | null
  loading?: boolean
}

export function SnapshotBar({ finance, health, loading }: SnapshotBarProps) {
  if (loading) {
    return (
      <Box
        style={{
          display: 'flex', flexWrap: 'wrap', gap: 24,
          padding: '10px 16px',
          borderBottom: '0.5px solid var(--border-subtle)',
        }}
      >
        {[32, 28, 24].map(w => (
          <Box key={w} style={{ height: 16, width: w * 4, background: 'var(--bg-elevated)', borderRadius: 4 }} />
        ))}
      </Box>
    )
  }

  const items: { label: string; value: string; positive?: boolean | null }[] = []

  if (finance) {
    items.push({ label: 'Net Worth', value: formatCurrency(finance.net_worth), positive: finance.net_worth >= 0 })
    items.push({ label: 'Surplus', value: formatCurrency(finance.monthly_surplus) + '/mo', positive: finance.monthly_surplus >= 0 })
  }
  if (health) {
    items.push({ label: 'Week', value: health.current_week, positive: null })
    if (health.days_to_comp !== null) {
      items.push({ label: 'Comp', value: formatDaysUntil(health.days_to_comp), positive: health.days_to_comp > 14 ? null : false })
    }
  }

  if (items.length === 0) return null

  return (
    <Box style={{ display: 'flex', flexWrap: 'wrap', gap: 24, padding: '10px 16px', borderBottom: '0.5px solid var(--border-subtle)' }}>
      {items.map((item, i) => (
        <Group key={i} gap={6}>
          <Text size="sm" c="var(--text-secondary)">{item.label}:</Text>
          <Text
            size="sm"
            fw={500}
            c={
              item.positive === null ? 'var(--text-primary)' :
              item.positive ? 'var(--status-success-text)' :
              'var(--status-danger-text)'
            }
          >
            {item.value}
          </Text>
        </Group>
      ))}
    </Box>
  )
}
