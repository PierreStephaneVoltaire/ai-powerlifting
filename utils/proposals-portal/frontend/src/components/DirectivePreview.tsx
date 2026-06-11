import { Box, Group, Stack, Text, Skeleton } from '@mantine/core'
import type { Directive } from '../types'

interface DirectivePreviewProps {
  directive: Directive | null
  loading?: boolean
}

export function DirectivePreview({ directive, loading }: DirectivePreviewProps) {
  if (loading) {
    return (
      <Box p="sm" style={{ background: 'var(--color-background-secondary)', borderRadius: 'var(--border-radius-lg)' }}>
        <Stack gap={6}>
          <Skeleton height={14} width="33%" />
          <Skeleton height={14} />
          <Skeleton height={14} width="75%" />
        </Stack>
      </Box>
    )
  }

  if (!directive) {
    return (
      <Box p="sm" style={{ background: 'var(--color-background-secondary)', borderRadius: 'var(--border-radius-lg)' }}>
        <Text size="sm" c="var(--color-text-secondary)">Directive not found</Text>
      </Box>
    )
  }

  return (
    <Box style={{ background: 'var(--color-background-secondary)', border: '0.5px solid var(--color-border-tertiary)', borderRadius: 'var(--border-radius-lg)', overflow: 'hidden' }}>
      <Box p="sm" style={{ background: 'var(--bg-elevated)', borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
        <Group gap={6}>
          <Text fw={600} size="sm" c="var(--text-primary)">{directive.label}</Text>
          <Text size="xs" c="var(--color-text-secondary)">(v{directive.version})</Text>
        </Group>
        <Text size="xs" c="var(--color-text-secondary)" mt={2}>
          Alpha: {directive.alpha} · Beta: {directive.beta} · Types: {directive.types.join(', ')}
        </Text>
      </Box>
      <Box p="sm">
        <pre className="if-prose-pre">{directive.content}</pre>
      </Box>
    </Box>
  )
}
