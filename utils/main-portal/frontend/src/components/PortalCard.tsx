import { Paper, Group, Text, Box, Anchor } from '@mantine/core'

interface PortalCardProps {
  name: string
  icon: string
  href: string
  status: 'reachable' | 'unreachable'
  pendingCount?: number
  lines: string[]
}

export function PortalCard({ name, icon, href, status, pendingCount, lines }: PortalCardProps) {
  const isReachable = status === 'reachable'

  const card = (
    <Paper
      p="md"
      style={{
        background: 'var(--bg-surface)',
        border: '0.5px solid var(--border-subtle)',
        borderRadius: 'var(--border-radius-lg)',
        transition: 'background 120ms ease, border-color 120ms ease',
        cursor: isReachable ? 'pointer' : 'default',
        opacity: isReachable ? 1 : 0.6,
      }}
    >
      <Group justify="space-between" mb={8}>
        <Group gap={8}>
          <Text size="xl">{icon}</Text>
          <Text fw={500} c="var(--text-primary)">{name}</Text>
          {pendingCount !== undefined && pendingCount > 0 && (
            <Box
              style={{
                background: 'var(--status-danger-bg)',
                border: '0.5px solid var(--status-danger-border)',
                borderRadius: 999,
                color: 'var(--status-danger-text)',
                fontSize: 11,
                fontWeight: 600,
                lineHeight: 1,
                padding: '2px 8px',
              }}
            >
              {pendingCount}
            </Box>
          )}
        </Group>
        <Box
          style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            flexShrink: 0,
            background: isReachable ? 'var(--status-success-text)' : 'var(--text-muted)',
          }}
        />
      </Group>
      {lines.map((line, i) => (
        <Text key={i} size="sm" c="var(--text-secondary)">{line}</Text>
      ))}
    </Paper>
  )

  if (!isReachable) return card

  return (
    <Anchor href={href} target="_blank" rel="noopener noreferrer" underline="never">
      {card}
    </Anchor>
  )
}
