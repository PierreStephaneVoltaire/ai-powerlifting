import { Stack, Text, Box } from '@mantine/core'

interface AlertsListProps {
  alerts: string[]
  loading?: boolean
}

export function AlertsList({ alerts, loading }: AlertsListProps) {
  if (loading) {
    return (
      <Stack gap={8}>
        {[100, 75].map(w => (
          <Box key={w} style={{ height: 40, width: `${w}%`, background: 'var(--bg-elevated)', borderRadius: 'var(--border-radius-md)' }} />
        ))}
      </Stack>
    )
  }

  if (alerts.length === 0) {
    return (
      <Box p="sm" style={{ background: 'var(--status-success-bg)', border: '0.5px solid var(--status-success-border)', borderRadius: 'var(--border-radius-lg)' }}>
        <Text size="sm" c="var(--status-success-text)">No alerts — everything looks good</Text>
      </Box>
    )
  }

  return (
    <Stack gap={6}>
      <Text size="sm" fw={500} c="var(--text-secondary)">
        ⚠️ Alerts
      </Text>
      {alerts.map((alert, i) => (
        <Box
          key={i}
          p="xs"
          style={{
            background: 'var(--status-warning-bg)',
            border: '0.5px solid var(--status-warning-border)',
            borderRadius: 'var(--border-radius-md)',
          }}
        >
          <Text size="sm" c="var(--status-warning-text)">{alert}</Text>
        </Box>
      ))}
    </Stack>
  )
}
