import { Group, Text, Badge, Box } from '@mantine/core'
import type { SignalsData } from '../types'
import { getScoreColor, getTrendColor, getLifeLoadColor, getTrendIcon } from '../utils/formatters'

interface SignalStripProps {
  signals: SignalsData | null
  loading?: boolean
}

export function SignalStrip({ signals, loading }: SignalStripProps) {
  const containerStyle = {
    display: 'flex', flexWrap: 'wrap' as const, alignItems: 'center', gap: 24,
    padding: '10px 16px',
    background: 'var(--bg-elevated)',
    borderRadius: 'var(--border-radius-lg)',
  }

  if (loading) {
    return (
      <Box style={containerStyle}>
        {[80, 64, 80, 64].map((w, i) => (
          <Box key={i} style={{ height: 20, width: w, background: 'var(--bg-surface)', borderRadius: 4 }} />
        ))}
      </Box>
    )
  }

  if (!signals) {
    return (
      <Box style={containerStyle}>
        <Text size="sm" c="var(--text-secondary)">Signal data unavailable</Text>
      </Box>
    )
  }

  return (
    <Box style={containerStyle}>
      <Group gap={6}>
        <Text size="sm" c="var(--text-secondary)">Score:</Text>
        <Text size="lg" fw={600} style={{ color: getScoreColor(signals.mental_health_score) }}>
          {signals.mental_health_score.toFixed(1)}
        </Text>
      </Group>

      <Group gap={6}>
        <Text size="sm" c="var(--text-secondary)">Trend:</Text>
        <Text fw={500} style={{ color: getTrendColor(signals.trend) }}>
          {getTrendIcon(signals.trend)} {signals.trend.replace('_', ' ')}
        </Text>
      </Group>

      <Group gap={6}>
        <Text size="sm" c="var(--text-secondary)">Life Load:</Text>
        <Badge
          size="sm"
          variant="light"
          style={{
            background: getLifeLoadColor(signals.life_load).bg,
            color: getLifeLoadColor(signals.life_load).text,
            border: `0.5px solid ${getLifeLoadColor(signals.life_load).border}`,
            textTransform: 'capitalize',
          }}
        >
          {signals.life_load.replace('_', ' ')}
        </Badge>
      </Group>

      {signals.social_battery && (
        <Group gap={6}>
          <Text size="sm" c="var(--text-secondary)">Social:</Text>
          <Text size="sm" fw={500} c="var(--text-primary)" style={{ textTransform: 'capitalize' }}>
            {signals.social_battery}
          </Text>
        </Group>
      )}
    </Box>
  )
}
