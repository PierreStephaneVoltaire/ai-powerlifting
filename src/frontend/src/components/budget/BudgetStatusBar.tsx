import { useEffect, useState } from 'react'
import {
  Box,
  Group,
  NumberInput,
  Paper,
  Stack,
  Text,
  ActionIcon,
} from '@mantine/core'
import { AlertTriangle, Pencil, Check, X } from 'lucide-react'
import { useMediaQuery } from '@mantine/hooks'
import type { BudgetConfig } from '@powerlifting/types'
import { formatCurrency, currencySymbol } from '@/components/budget/budgetShared'

interface BudgetStatusBarProps {
  config: BudgetConfig
  spentThisMonth: number
  recurringMonthlyTotal: number
  readOnly: boolean
  athleteName?: string | null
  onCapChange: (cap: number, currency: string) => void
}

export default function BudgetStatusBar({
  config,
  spentThisMonth,
  recurringMonthlyTotal,
  readOnly,
  athleteName,
  onCapChange,
}: BudgetStatusBarProps) {
  const isMobile = useMediaQuery('(max-width: 480px)')
  const [editing, setEditing] = useState(false)
  const [draftCap, setDraftCap] = useState<number>(config.monthly_cap)

  useEffect(() => {
    setDraftCap(config.monthly_cap)
  }, [config.monthly_cap])

  const cap = config.monthly_cap
  const currency = config.currency
  const sym = currencySymbol(currency) || '$'
  const capSet = cap > 0
  const remaining = cap - spentThisMonth
  const overBudget = capSet && spentThisMonth > cap
  const overAmount = overBudget ? spentThisMonth - cap : 0

  function handleSave() {
    const next = Math.max(0, Number.isFinite(draftCap) ? draftCap : 0)
    onCapChange(next, currency)
    setEditing(false)
  }

  function handleCancel() {
    setDraftCap(cap)
    setEditing(false)
  }

  if (!capSet && !readOnly && !editing) {
    return (
      <Paper withBorder p="sm" radius="md" onClick={() => setEditing(true)} style={{ cursor: 'pointer' }} data-testid="budget-status-bar">
        <Group gap="xs" align="center">
          <AlertTriangle size={16} color="var(--mantine-color-yellow-6)" />
          <Text size="sm" fw={500}>Set a monthly cap to start tracking</Text>
          <Text size="sm" c="dimmed">→</Text>
        </Group>
      </Paper>
    )
  }

  if (editing && !readOnly) {
    return (
      <Paper withBorder p="sm" radius="md" data-testid="budget-status-bar">
        <Group gap="sm" align="center" wrap="nowrap">
          <Text size="sm" fw={500} style={{ whiteSpace: 'nowrap' }}>Monthly cap:</Text>
          <NumberInput value={draftCap} onChange={(v) => setDraftCap(typeof v === 'number' ? v : 0)} min={0} decimalScale={2} hideControls leftSection={<Text size="xs" c="dimmed">{sym}</Text>} size="sm" style={{ width: isMobile ? 110 : 140 }} autoFocus onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') handleCancel() }} aria-label="Monthly budget cap" />
          <ActionIcon variant="filled" color="brand" size="sm" onClick={handleSave} aria-label="Save monthly cap"><Check size={16} /></ActionIcon>
          <ActionIcon variant="subtle" size="sm" onClick={handleCancel} aria-label="Cancel cap edit"><X size={16} /></ActionIcon>
        </Group>
      </Paper>
    )
  }

  const warningStyle = overBudget ? { borderLeft: '3px solid var(--mantine-color-orange-6)', paddingLeft: '10px' } : undefined
  const warningColor = overBudget ? 'var(--mantine-color-orange-6)' : undefined

  return (
    <Paper withBorder p="sm" radius="md" data-testid="budget-status-bar" style={warningStyle}>
      {isMobile ? (
        <Stack gap={2}>
          <Group gap="xs" align="center" justify="space-between">
            <Group gap="xs">
              {overBudget ? <AlertTriangle size={14} color="var(--mantine-color-orange-6)" /> : null}
              <Text size="sm" fw={700} c={warningColor}>
                {overBudget ? `OVER BUDGET by ${formatCurrency(overAmount, currency)}` : `${currency} ${formatCurrency(cap, currency)}/month cap`}
              </Text>
            </Group>
            {!readOnly && (
              <ActionIcon variant="subtle" size="sm" onClick={() => setEditing(true)} aria-label="Edit monthly cap"><Pencil size={14} /></ActionIcon>
            )}
          </Group>
          <Text size="xs" c={warningColor ?? 'dimmed'}>
            {overBudget ? `Cap: ${formatCurrency(cap, currency)} · Spent: ${formatCurrency(spentThisMonth, currency)}` : `Spent: ${formatCurrency(spentThisMonth, currency)} · Left: ${formatCurrency(Math.max(0, remaining), currency)}`}
          </Text>
        </Stack>
      ) : (
        <Group gap="md" align="center" justify="space-between" wrap="nowrap">
          <Group gap="sm" align="center" wrap="nowrap">
            {overBudget ? <AlertTriangle size={16} color="var(--mantine-color-orange-6)" /> : null}
            <Text size="sm" fw={700} c={warningColor}>
              {overBudget ? `OVER BUDGET by ${formatCurrency(overAmount, currency)}` : `${currency} ${formatCurrency(cap, currency)} / month`}
            </Text>
            {!overBudget && <Text size="sm" c="dimmed">Spent this month: {formatCurrency(spentThisMonth, currency)}</Text>}
            {overBudget && <Text size="sm" c="dimmed">Monthly cap: {formatCurrency(cap, currency)} · Spent: {formatCurrency(spentThisMonth, currency)}</Text>}
            {!overBudget && capSet && (
              <Text size="sm" fw={500} c={remaining < 0 ? 'var(--mantine-color-orange-6)' : undefined}>Remaining: {formatCurrency(remaining, currency)}</Text>
            )}
          </Group>
          {!readOnly && <ActionIcon variant="subtle" size="sm" onClick={() => setEditing(true)} aria-label="Edit monthly cap"><Pencil size={14} /></ActionIcon>}
        </Group>
      )}
      {readOnly && athleteName && (
        <Box mt={4}><Text size="xs" c="dimmed">Viewing {athleteName}&apos;s budget — read only.</Text></Box>
      )}
      {overBudget && recurringMonthlyTotal > cap && (
        <Box mt={4}><Text size="xs" c="var(--mantine-color-orange-6)">Recurring costs alone ({formatCurrency(recurringMonthlyTotal, currency)}/mo) exceed your cap.</Text></Box>
      )}
    </Paper>
  )
}
