import { useMemo } from 'react'
import {
  Alert,
  Badge,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
} from '@mantine/core'
import { Zap, Dumbbell, Pill, CalendarClock } from 'lucide-react'
import { useMediaQuery } from '@mantine/hooks'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from 'recharts'
import type { BudgetItem, BudgetConfig } from '@powerlifting/types'
import {
  buildBudgetSummary,
  buildMonthSpendTrend,
  hasEnoughTrendData,
  formatCurrency,
  isRecurring,
  itemTier,
  monthlyCost,
  monthLabel,
  compLinked,
  type BudgetPriorityTier,
} from '@/components/budget/budgetShared'

interface BudgetOverviewProps {
  items: BudgetItem[]
  config: BudgetConfig
  readOnly: boolean
  athleteName?: string | null
  onTierSelect: (tier: BudgetPriorityTier) => void
}

const TIER_LABELS: Record<BudgetPriorityTier, string> = {
  MANDATORY: 'Mandatory',
  IMPORTANT: 'Important',
  OPTIONAL: 'Optional',
}

function tierBadgeVariant(tier: BudgetPriorityTier): 'filled' | 'light' | 'outline' {
  if (tier === 'MANDATORY') return 'filled'
  if (tier === 'IMPORTANT') return 'filled'
  return 'outline'
}

function tierColor(tier: BudgetPriorityTier): string {
  return tier === 'MANDATORY' ? 'blue' : tier === 'IMPORTANT' ? 'indigo' : 'gray'
}

function categoryIcon(category: string) {
  switch (category) {
    case 'equipment':
      return <Dumbbell size={14} />
    case 'supplement':
      return <Pill size={14} />
    default:
      return <CalendarClock size={14} />
  }
}

export default function BudgetOverview({
  items,
  config,
  readOnly,
  athleteName,
  onTierSelect,
}: BudgetOverviewProps) {
  const isMobile = useMediaQuery('(max-width: 480px)')
  const month = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
  const currency = config.currency

  const summary = useMemo(() => buildBudgetSummary(items, config, month), [items, config, month])
  const recurringItems = useMemo(() => items.filter(isRecurring), [items])
  const recurringTotal = summary.recurring_monthly_total

  return (
    <Stack gap="md">
      {readOnly && athleteName && (
        <Alert variant="light" color="yellow" icon={<Zap size={16} />}>
          <Text size="sm">Viewing {athleteName}&apos;s budget — read only.</Text>
        </Alert>
      )}

      <Stack gap="xs">
        <Text size="sm" fw={600}>This month&apos;s breakdown</Text>
        <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="sm">
          {(Object.keys(TIER_LABELS) as BudgetPriorityTier[]).map((tier) => {
            const data = summary.items_by_priority[tier]
            return (
              <Paper
                key={tier}
                withBorder
                p="sm"
                radius="md"
                onClick={() => onTierSelect(tier)}
                style={{ cursor: 'pointer', minHeight: 64 }}
                data-testid={`tier-tile-${tier}`}
              >
                <Group gap="xs" align="center">
                  <Badge variant={tierBadgeVariant(tier)} color={tierColor(tier)} size="xs">
                    {TIER_LABELS[tier]}
                  </Badge>
                  <Text size="xs" c="dimmed">{data.count}</Text>
                </Group>
                <Text fw={700} size="lg" mt={4}>
                  {formatCurrency(data.total, currency)}
                </Text>
              </Paper>
            )
          })}
        </SimpleGrid>
      </Stack>

      <Paper withBorder p="sm" radius="md">
        <Group justify="space-between" mb="sm">
          <Text size="sm" fw={600}>Recurring costs</Text>
          <Text size="xs" c="dimmed">Total recurring monthly: {formatCurrency(recurringTotal, currency)}</Text>
        </Group>
        {recurringItems.length === 0 ? (
          <Text size="sm" c="dimmed">No recurring expenses tracked.</Text>
        ) : (
          <Table striped layout="fixed" style={{ tableLayout: 'fixed' }}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                {!isMobile && <Table.Th style={{ width: 60 }}>Category</Table.Th>}
                <Table.Th ta="right" style={{ width: isMobile ? 90 : 110 }}>Cost/mo</Table.Th>
                {!isMobile && <Table.Th style={{ width: 110 }}>Priority</Table.Th>}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {recurringItems.map((item) => {
                const tier = itemTier(item)
                return (
                  <Table.Tr key={item.id}>
                    <Table.Td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <Text size="sm" truncate>{item.name || 'Untitled'}</Text>
                    </Table.Td>
                    {!isMobile && (
                      <Table.Td>
                        <ThemeIcon variant="subtle" size="sm" radius="xl">
                          {categoryIcon(item.category)}
                        </ThemeIcon>
                      </Table.Td>
                    )}
                    <Table.Td ta="right">
                      <Text size="sm">{formatCurrency(monthlyCost(item), currency)}</Text>
                    </Table.Td>
                    {!isMobile && (
                      <Table.Td>
                        <Badge variant={tierBadgeVariant(tier)} color={tierColor(tier)} size="xs">
                          {TIER_LABELS[tier]}
                        </Badge>
                      </Table.Td>
                    )}
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        )}
      </Paper>

      <Paper withBorder p="sm" radius="md">
        <Text size="sm" fw={600} mb="sm">Upcoming one-time expenses</Text>
        {summary.upcoming_one_time.length === 0 ? (
          <Text size="sm" c="dimmed">No upcoming expenses.</Text>
        ) : (
          <Stack gap="xs">
            {summary.upcoming_one_time.map((item) => {
              const tier = itemTier(item)
              const dateLabel = item.start_date ? monthLabel(item.start_date.slice(0, 7)) : '—'
              return (
                <Group key={item.id} gap="sm" align="center" wrap="nowrap">
                  <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                    {compLinked(item) ? (
                      <ThemeIcon variant="subtle" color="yellow" size="sm" radius="xl">
                        <Zap size={12} />
                      </ThemeIcon>
                    ) : null}
                    <Text size="sm" truncate style={{ flex: 1, minWidth: 0 }}>
                      {item.name || 'Untitled'}
                    </Text>
                  </Group>
                  <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{dateLabel}</Text>
                  <Text size="sm" fw={500} style={{ whiteSpace: 'nowrap' }}>
                    {formatCurrency(item.cost, currency)}
                  </Text>
                  <Badge variant={tierBadgeVariant(tier)} color={tierColor(tier)} size="xs">
                    {TIER_LABELS[tier]}
                  </Badge>
                </Group>
              )
            })}
          </Stack>
        )}
      </Paper>

      <BudgetTrendChart items={items} config={config} monthCount={isMobile ? 4 : 6} month={month} />
    </Stack>
  )
}

interface BudgetTrendChartProps {
  items: BudgetItem[]
  config: BudgetConfig
  monthCount: number
  month: string
}

function BudgetTrendChart({ items, config, monthCount, month }: BudgetTrendChartProps) {
  const currency = config.currency
  const cap = config.monthly_cap

  const trend = useMemo(
    () => buildMonthSpendTrend(items, cap, monthCount, month),
    [items, cap, monthCount, month],
  )
  const hasTrend = useMemo(() => hasEnoughTrendData(items, monthCount, month), [items, monthCount, month])

  if (!hasTrend) {
    return (
      <Paper withBorder p="md" radius="md">
        <Text size="sm" fw={600} mb="xs">Monthly spend trend</Text>
        <Text size="sm" c="dimmed">Keep logging expenses to see your trend.</Text>
      </Paper>
    )
  }

  const maxSpent = Math.max(...trend.map((p) => p.spent), cap)
  const yMax = Math.ceil((maxSpent * 1.1) / 10) * 10

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="sm">
        <Text size="sm" fw={600}>Monthly spend trend</Text>
        {cap > 0 && (
          <Text size="xs" c="dimmed">cap {formatCurrency(cap, currency)}/mo</Text>
        )}
      </Group>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => formatCurrency(v, currency)}
            domain={[0, yMax]}
          />
          <Tooltip
            formatter={(value: number) => [formatCurrency(value, currency), 'Spent']}
            labelFormatter={(label: string) => label}
          />
          {cap > 0 && (
            <ReferenceLine
              y={cap}
              stroke="var(--mantine-color-orange-5)"
              strokeDasharray="6 4"
              label={{ value: 'cap', fontSize: 10, fill: 'var(--mantine-color-orange-6)', position: 'insideTopRight' }}
            />
          )}
          <Bar
            dataKey="spent"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
            shape={(props: unknown) => {
              const p = props as { x: number; y: number; width: number; height: number; payload: { over: boolean } }
              const fill = p.payload.over ? 'var(--mantine-color-orange-5)' : 'var(--mantine-color-brand-5)'
              return <rect x={p.x} y={p.y} width={p.width} height={p.height} rx={4} ry={4} fill={fill} />
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </Paper>
  )
}