import { useState } from 'react'
import { Box, Button, Group, Loader, Stack, Text } from '@mantine/core'
import { Check, Copy, FileText } from 'lucide-react'
import { notifications } from '@mantine/notifications'

interface ImplementationPlanProps {
  plan: string | null
  isGenerating?: boolean
}

export function ImplementationPlan({ plan, isGenerating }: ImplementationPlanProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (!plan) return
    try {
      await navigator.clipboard.writeText(plan)
      setCopied(true)
      notifications.show({ title: 'Copied', message: 'Implementation plan copied to clipboard', color: 'blue' })
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
      notifications.show({ title: 'Copy failed', message: 'Could not copy to clipboard', color: 'red' })
    }
  }

  if (isGenerating) {
    return (
      <Box
        p="lg"
        style={{
          background: 'var(--status-info-bg)',
          border: '0.5px solid var(--status-info-border)',
          borderRadius: 'var(--border-radius-lg)',
        }}
      >
        <Stack align="center" gap="xs">
          <Loader size="sm" color="blue" />
          <Text size="sm" fw={600} c="var(--status-info-text)">
            Generating implementation plan...
          </Text>
          <Text size="xs" c="var(--status-info-text)">This may take a moment</Text>
        </Stack>
      </Box>
    )
  }

  if (!plan) return null

  return (
    <Box style={{ background: 'var(--color-background-primary)', border: '0.5px solid var(--color-border-tertiary)', borderRadius: 'var(--border-radius-lg)', overflow: 'hidden' }}>
      <Box p="sm" style={{ background: 'var(--bg-elevated)', borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
        <Group justify="space-between" wrap="nowrap">
          <Group gap={6}>
            <FileText size={14} color="var(--color-text-secondary)" />
            <Text fw={600} size="sm" c="var(--text-primary)">Implementation Plan</Text>
          </Group>
          <Button
            size="xs"
            variant="light"
            color="blue"
            leftSection={copied ? <Check size={12} /> : <Copy size={12} />}
            onClick={handleCopy}
          >
            {copied ? 'Copied' : 'Copy Plan'}
          </Button>
        </Group>
      </Box>
      <Box p="sm">
        <pre className="if-prose-pre">{plan}</pre>
      </Box>
    </Box>
  )
}
