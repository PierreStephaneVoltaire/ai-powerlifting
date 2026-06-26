import { useState, useCallback } from 'react'
import {
  Paper,
  Group,
  Text,
  Badge,
  Box,
  Stack,
  Button,
  Anchor,
  Tooltip,
  Alert,
  ThemeIcon,
} from '@mantine/core'
import {
  Brain,
  RefreshCw,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Scissors,
  Info,
  RotateCcw,
} from 'lucide-react'
import { notifications } from '@mantine/notifications'
import { fetchBudgetAiAnalysis, markBudgetItemCut } from '@/api/client'
import { formatCurrency } from './budgetShared'
import type { BudgetAiAnalysis, BudgetAiCutItem } from '@powerlifting/types'

interface AiBudgetAdvisorProps {
  readOnly: boolean
  isCoach: boolean
  monthlyCap: number
  currency?: string | null
  onItemCutToggled?: (itemId: string, cut: boolean) => void
  athleteName?: string | null
}

function Spinner() {
  return (
    <span
      role="status"
      aria-label="Loading"
      style={{
        display: 'inline-block',
        width: 28,
        height: 28,
        border: '3px solid var(--mantine-color-gray-3)',
        borderTopColor: 'var(--mantine-color-violet-6)',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
      }}
    />
  )
}

export function AiBudgetAdvisor({
  readOnly,
  isCoach,
  monthlyCap,
  currency,
  onItemCutToggled,
  athleteName,
}: AiBudgetAdvisorProps) {
  const [analysis, setAnalysis] = useState<BudgetAiAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmingRefresh, setConfirmingRefresh] = useState(false)
  const [cutBusyId, setCutBusyId] = useState<string | null>(null)

  const hasCap = monthlyCap > 0

  const load = useCallback(
    (refresh: boolean) => {
      if (readOnly && refresh) return
      setLoading(true)
      setError(null)
      fetchBudgetAiAnalysis(refresh)
        .then((result) => {
          setAnalysis(result)
          setLoading(false)
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : String(err))
          setLoading(false)
        })
    },
    [readOnly],
  )

  const handleRefresh = useCallback(() => {
    if (readOnly) return
    if (!confirmingRefresh) {
      setConfirmingRefresh(true)
      return
    }
    setConfirmingRefresh(false)
    load(true)
  }, [readOnly, confirmingRefresh, load])

  const handleCut = useCallback(
    (item: BudgetAiCutItem) => {
      const itemId = item.item_id
      setCutBusyId(itemId)
      markBudgetItemCut(itemId, true)
        .then(() => {
          setAnalysis((prev) =>
            prev
              ? { ...prev, suggested_cuts: prev.suggested_cuts.filter((c) => c.item_id !== itemId) }
              : prev,
          )
          onItemCutToggled?.(itemId, true)
          notifications.show({ message: `Marked "${item.name}" as cut.`, color: 'blue' })
        })
        .catch((err) => {
          notifications.show({
            message: `Failed to mark "${item.name}" as cut: ${err instanceof Error ? err.message : err}`,
            color: 'red',
          })
        })
        .finally(() => setCutBusyId(null))
    },
    [onItemCutToggled],
  )

  if (!analysis && !loading && !error) {
    return (
      <Stack gap="md">
        {isCoach && athleteName && (
          <Alert variant="light" color="yellow" icon={<Info size={16} />}>
            Viewing {athleteName}'s budget — read only.
          </Alert>
        )}
        <Paper withBorder p="xl" radius="md">
          <Stack gap="sm" align="flex-start">
            <Group gap="sm">
              <ThemeIcon variant="light" color="violet" size="lg" radius="xl">
                <Brain size={20} />
              </ThemeIcon>
              <Text fw={600} size="lg">AI Budget Advisor</Text>
            </Group>
            <Text size="sm" c="dimmed" maw={520}>
              Get an AI-powered breakdown of your budget priorities and a pre-comp cutlist if you're
              over your cap.
            </Text>
            <Text size="xs" c="dimmed" maw={520}>
              Analysis looks at: your monthly cap, current items, their priorities, and your upcoming
              competition dates.
            </Text>
            {!readOnly && (
              <Tooltip label="Set a monthly cap first (Overview tab)." disabled={hasCap} position="bottom">
                <Box>
                  <Button
                    leftSection={<Sparkles size={16} />}
                    onClick={() => load(false)}
                    loading={loading}
                    disabled={!hasCap}
                  >
                    Analyse my budget
                  </Button>
                </Box>
              </Tooltip>
            )}
          </Stack>
        </Paper>
      </Stack>
    )
  }

  if (loading && !analysis) {
    return (
      <Paper withBorder p="xl" radius="md">
        <Stack gap="sm" align="center">
          <Spinner />
          <Text size="sm" c="dimmed">Analysing your expenses and upcoming meets…</Text>
        </Stack>
      </Paper>
    )
  }

  if (error && !analysis) {
    return (
      <Stack gap="md">
        <Alert variant="light" color="red" icon={<AlertTriangle size={16} />}>
          <Text size="sm">Analysis failed: {error}</Text>
        </Alert>
        {!readOnly && (
          <Button leftSection={<RotateCcw size={16} />} variant="light" onClick={() => load(false)}>
            Try again
          </Button>
        )}
      </Stack>
    )
  }

  if (!analysis) return null

  const generated = new Date(analysis.generated_at).toLocaleString()

  return (
    <Stack gap="md">
      {isCoach && athleteName && (
        <Alert variant="light" color="yellow" icon={<Info size={16} />}>
          Viewing {athleteName}'s budget — read only.
        </Alert>
      )}

      <Paper withBorder p="md" radius="md">
        <Group gap="sm" align="flex-start" justify="space-between" wrap="wrap">
          <Stack gap={4} style={{ flex: '1 1 16rem', minWidth: 0 }}>
            <Group gap="xs">
              <Brain size={16} />
              <Text fw={600}>Overall assessment</Text>
            </Group>
            <Text size="sm">{analysis.overall_assessment}</Text>
          </Stack>
          <Stack gap={2} align="flex-end">
            <Badge variant="light" color={analysis.cached ? 'gray' : 'green'} size="xs">
              {analysis.cached ? 'Cached' : 'Fresh'}
            </Badge>
            <Text size="xs" c="dimmed">Generated {generated}</Text>
          </Stack>
        </Group>
      </Paper>

      {analysis.locked_in.length > 0 && (
        <Paper withBorder p="md" radius="md">
          <Stack gap="xs">
            <Group gap="xs">
              <CheckCircle2 size={16} color="var(--mantine-color-green-6)" />
              <Text fw={600}>What's locked in</Text>
            </Group>
            {analysis.locked_in.map((item) => (
              <Group key={item.item_id} gap="sm" align="flex-start" wrap="wrap">
                <Badge variant="filled" color="blue" size="xs">Mandatory</Badge>
                <Text size="sm" fw={500} style={{ flex: '0 1 auto' }}>{item.name}</Text>
                {item.purchased ? (
                  <Badge variant="filled" color="green" size="xs" leftSection={<CheckCircle2 size={10} />}>
                    Purchased
                  </Badge>
                ) : (
                  <Badge variant="filled" color="orange" size="xs">Not purchased</Badge>
                )}
                <Text size="xs" c="dimmed" style={{ flex: '1 1 100%' }}>{item.note}</Text>
              </Group>
            ))}
          </Stack>
        </Paper>
      )}

      {analysis.suggested_cuts.length > 0 && (
        <Paper withBorder p="md" radius="md" style={{ borderColor: 'var(--mantine-color-yellow-4)' }}>
          <Stack gap="xs">
            <Group gap="xs">
              <Scissors size={16} color="var(--mantine-color-yellow-6)" />
              <Text fw={600}>Suggested cuts</Text>
            </Group>
            {analysis.suggested_cuts.map((item) => (
              <Group key={item.item_id} gap="sm" align="flex-start" wrap="wrap">
                <Badge variant="outline" color="gray" size="xs">#{item.rank}</Badge>
                <Text size="sm" fw={500} style={{ flex: '0 1 auto' }}>{item.name}</Text>
                <Text size="sm" c="dimmed" fw={500}>{formatCurrency(item.cost, currency)}</Text>
                <Text size="xs" c="dimmed" style={{ flex: '1 1 100%' }}>{item.reason}</Text>
                {!readOnly && (
                  <Button
                    size="compact-xs"
                    variant="light"
                    color="yellow"
                    leftSection={<Scissors size={12} />}
                    loading={cutBusyId === item.item_id}
                    onClick={() => handleCut(item)}
                  >
                    Mark as cut
                  </Button>
                )}
              </Group>
            ))}
          </Stack>
        </Paper>
      )}

      {analysis.gaps.length > 0 && (
        <Paper withBorder p="md" radius="md">
          <Stack gap="xs">
            <Group gap="xs">
              <AlertTriangle size={16} color="var(--mantine-color-yellow-6)" />
              <Text fw={600}>Gaps identified</Text>
            </Group>
            {analysis.gaps.map((gap, i) => (
              <Group key={i} gap="sm" align="flex-start" wrap="wrap">
                <Badge variant="filled" color={gap.severity === 'warning' ? 'orange' : 'gray'} size="xs">
                  {gap.severity === 'warning' ? '⚠ Warning' : 'Info'}
                </Badge>
                <Text size="sm" style={{ flex: '1 1 80%' }}>{gap.description}</Text>
              </Group>
            ))}
          </Stack>
        </Paper>
      )}

      {isCoach && analysis.coach_note && (
        <Paper withBorder p="md" radius="md" style={{ background: 'var(--mantine-color-violet-0)' }}>
          <Stack gap="xs">
            <Group gap="xs">
              <Brain size={16} color="var(--mantine-color-violet-6)" />
              <Text fw={600}>Coach note</Text>
            </Group>
            <Text size="sm">{analysis.coach_note}</Text>
          </Stack>
        </Paper>
      )}

      <Group gap="sm" justify="space-between" wrap="wrap">
        {analysis.insufficient_data && analysis.insufficient_data_reason && (
          <Text size="xs" c="dimmed">{analysis.insufficient_data_reason}</Text>
        )}
        {!readOnly && (
          <Anchor
            component="button"
            size="xs"
            c="dimmed"
            onClick={handleRefresh}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
          >
            <RefreshCw size={12} />
            {confirmingRefresh ? 'Click again to confirm — this replaces the current result.' : 'Refresh analysis'}
          </Anchor>
        )}
      </Group>
    </Stack>
  )
}
