import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  ActionIcon,
  Badge,
  Box,
  Divider,
  Group,
  MultiSelect,
  Paper,
  Stack,
  Switch,
  Text,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { Zap, Repeat, Filter, ChevronLeft, ChevronRight, Calendar } from 'lucide-react'
import type { BudgetItem, BudgetConfig, UserCompetition, BudgetCategory, BudgetPriorityTier } from '@powerlifting/types'
import { BUDGET_CATEGORY_OPTIONS, BUDGET_PRIORITY_TIER_VALUES } from '@powerlifting/types'
import {
  formatCurrency,
  currencySymbol,
  monthLabel,
  monthShortLabel,
  monthKeyFromDate,
  currentMonthKey,
  isRecurring,
  itemTier,
  compLinked,
  activeInMonth,
} from '@/components/budget/budgetShared'
import { monthOf, datePeriodLabel } from '@/components/budget/dateUtils'

interface TimelineFilters {
  priorities: BudgetPriorityTier[]
  categories: BudgetCategory[]
  compLinkedOnly: boolean
}

interface BudgetTimelineProps {
  items: BudgetItem[]
  comps: UserCompetition[]
  config: BudgetConfig
  readOnly: boolean
  athleteName?: string | null
}

const TIER_ORDER: Record<BudgetPriorityTier, number> = {
  MANDATORY: 0,
  IMPORTANT: 1,
  OPTIONAL: 2,
}

const TIER_LABELS: Record<BudgetPriorityTier, string> = {
  MANDATORY: 'Mandatory',
  IMPORTANT: 'Important',
  OPTIONAL: 'Optional',
}

function addMonths(monthKey: string, n: number): string {
  const [y, m] = monthKey.split('-').map(Number)
  return monthKeyFromDate(new Date(y, m - 1 + n, 1))
}

function monthsBetween(a: string, b: string): number {
  const [ay, am] = a.split('-').map(Number)
  const [by, bm] = b.split('-').map(Number)
  return (by - ay) * 12 + (bm - am)
}

function buildTimelineWindow(items: BudgetItem[], comps: UserCompetition[]): string[] {
  const set = new Set<string>()
  const now = currentMonthKey()
  set.add(now)

  for (const item of items) {
    const sm = monthOf(item.start_date)
    if (sm) set.add(sm)
    const em = monthOf(item.end_date)
    if (em) set.add(em)
  }
  for (const comp of comps) {
    const cm = monthOf(comp.start_date)
    if (cm) set.add(cm)
  }

  const sorted = Array.from(set).sort()
  if (sorted.length === 0) return [now]
  const start = sorted[0]
  const end = addMonths(sorted[sorted.length - 1], 2)

  const result: string[] = []
  let cursor = start
  while (cursor <= end) {
    result.push(cursor)
    cursor = addMonths(cursor, 1)
  }
  return result
}

function formatCompDate(dateStr: string): string {
  const [y, m, d] = dateStr.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return dateStr
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function recurrenceLabel(rec: string): string {
  return rec === 'ONE_TIME' ? 'one-time' : rec.toLowerCase()
}

function tierBadgeVariant(tier: BudgetPriorityTier): 'outline' | 'light' | 'default' {
  if (tier === 'MANDATORY') return 'outline'
  if (tier === 'IMPORTANT') return 'light'
  return 'default'
}

function tierColor(tier: BudgetPriorityTier): string {
  return tier === 'MANDATORY' ? 'brand' : tier === 'IMPORTANT' ? 'blue' : 'gray'
}

function filterItems(items: BudgetItem[], filters: TimelineFilters): BudgetItem[] {
  return items.filter((item) => {
    if (filters.priorities.length > 0 && !filters.priorities.includes(itemTier(item))) return false
    if (filters.categories.length > 0 && !filters.categories.includes(item.category)) return false
    if (filters.compLinkedOnly && !compLinked(item)) return false
    return true
  })
}

function activeFilterCount(filters: TimelineFilters): number {
  let n = 0
  if (filters.priorities.length > 0) n += 1
  if (filters.categories.length > 0) n += 1
  if (filters.compLinkedOnly) n += 1
  return n
}

export default function BudgetTimeline({
  items,
  comps,
  config,
  readOnly,
  athleteName,
}: BudgetTimelineProps) {
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [filters, setFilters] = useState<TimelineFilters>({
    priorities: [],
    categories: [],
    compLinkedOnly: false,
  })
  const [filterOpen, setFilterOpen] = useState(false)
  const navScrollRef = useRef<HTMLDivElement>(null)

  const currency = config.currency
  const monthlyCap = config.monthly_cap

  const allMonths = useMemo(() => buildTimelineWindow(items, comps), [items, comps])
  const compMonths = useMemo(
    () => new Set(comps.map((c) => monthOf(c.start_date)).filter(Boolean)),
    [comps],
  )

  const categoryOptions = useMemo(() => {
    const known = BUDGET_CATEGORY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))
    const knownValues = new Set(known.map((o) => o.value))
    const fromItems = Array.from(
      new Set(items.map((i) => i.category).filter((c) => !knownValues.has(c))),
    ).map((c) => ({ value: c, label: c.replace(/_/g, ' ') }))
    return [...known, ...fromItems]
  }, [items])

  const priorityOptions = useMemo(
    () => BUDGET_PRIORITY_TIER_VALUES.map((t) => ({ value: t, label: TIER_LABELS[t] })),
    [],
  )

  const filteredItems = useMemo(() => filterItems(items, filters), [items, filters])

  const monthData = useMemo(
    () =>
      allMonths.map((month) => {
        const active = filteredItems.filter((it) => activeInMonth(it, month))
        const sorted = active.sort((a, b) => {
          const ta = TIER_ORDER[itemTier(a)]
          const tb = TIER_ORDER[itemTier(b)]
          if (ta !== tb) return ta - tb
          return (a.name || '').localeCompare(b.name || '')
        })
        const total = active.reduce((sum, it) => sum + it.cost, 0)
        return { month, items: sorted, total }
      }),
    [allMonths, filteredItems],
  )

  const defaultMonth = useMemo(() => {
    const now = currentMonthKey()
    const upcomingComps = comps
      .filter((c) => c.user_status !== 'completed' && c.user_status !== 'skipped')
      .map((c) => monthOf(c.start_date))
      .filter(Boolean)
      .sort()
    const nextComp = upcomingComps.find((m) => m >= now)
    if (nextComp && monthsBetween(now, nextComp) <= 3) return nextComp
    return now
  }, [comps])

  const scrollToMonth = useCallback((month: string) => {
    const el = document.getElementById(`timeline-month-${month}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      console.info('[BudgetTimeline] scrolled to month', month)
    }
  }, [])

  useEffect(() => {
    console.info('[BudgetTimeline] mounted', { items: items.length, comps: comps.length })
  }, [items.length, comps.length])

  useEffect(() => {
    if (allMonths.length === 0) return
    const t = setTimeout(() => {
      if (allMonths.includes(defaultMonth)) {
        scrollToMonth(defaultMonth)
      }
    }, 100)
    return () => clearTimeout(t)
  }, [allMonths, defaultMonth, scrollToMonth])

  const handleFilterChange = useCallback((next: Partial<TimelineFilters>) => {
    setFilters((prev) => {
      const updated = { ...prev, ...next }
      console.info('[BudgetTimeline] filter changed', updated)
      return updated
    })
  }, [])

  const scrollNav = useCallback((dir: 'left' | 'right') => {
    const el = navScrollRef.current
    if (!el) return
    el.scrollBy({ left: dir === 'left' ? -200 : 200, behavior: 'smooth' })
  }, [])

  const noItems = items.length === 0
  const noComps = comps.length === 0
  const filtCount = activeFilterCount(filters)

  if (noItems && noComps) {
    return (
      <Paper withBorder p="xl" radius="md" ta="center">
        <Stack gap="xs" align="center">
          <Calendar size={32} color="var(--mantine-color-dimmed)" />
          <Text size="sm" c="dimmed">
            Add expenses in the Items tab and link a competition in the Designer to see your timeline.
          </Text>
        </Stack>
      </Paper>
    )
  }

  return (
    <Stack gap="md">
      {readOnly && athleteName && (
        <Text size="xs" c="dimmed">
          Viewing {athleteName}&apos;s budget — read only.
        </Text>
      )}

      {noComps && (
        <Paper withBorder p="xs" radius="md" style={{ borderLeft: '3px solid var(--mantine-color-yellow-5)' }}>
          <Text size="xs" c="dimmed">
            Link a competition in the Designer to anchor your timeline.
          </Text>
        </Paper>
      )}

      <FilterBar
        filters={filters}
        onFilterChange={handleFilterChange}
        categoryOptions={categoryOptions}
        priorityOptions={priorityOptions}
        isMobile={!!isMobile}
        filterOpen={filterOpen}
        setFilterOpen={setFilterOpen}
        filtCount={filtCount}
      />

      <Box
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          background: 'var(--mantine-color-body)',
          paddingBottom: 4,
        }}
      >
        <Group gap="xs" align="center" wrap="nowrap">
          <ActionIcon variant="subtle" size="sm" onClick={() => scrollNav('left')} aria-label="Previous months">
            <ChevronLeft size={16} />
          </ActionIcon>
          <Box
            ref={navScrollRef}
            style={{ overflowX: 'auto', scrollbarWidth: 'none', flex: 1 }}
            data-testid="timeline-nav"
          >
            <Group gap={6} wrap="nowrap">
              {allMonths.map((m) => {
                const hasComp = compMonths.has(m)
                const isDefault = m === defaultMonth
                return (
                  <Paper
                    key={m}
                    withBorder
                    radius="xl"
                    px="sm"
                    py={4}
                    onClick={() => scrollToMonth(m)}
                    style={{
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      borderColor: isDefault
                        ? 'var(--mantine-color-brand-5)'
                        : undefined,
                      background: isDefault
                        ? 'var(--mantine-color-brand-1)'
                        : undefined,
                    }}
                    data-testid={`timeline-nav-${m}`}
                  >
                    <Group gap={4} align="center" wrap="nowrap">
                      {hasComp && <Zap size={11} color="var(--mantine-color-orange-6)" />}
                      <Text size="xs" fw={isDefault ? 700 : 500}>
                        {monthShortLabel(m)}
                      </Text>
                    </Group>
                  </Paper>
                )
              })}
            </Group>
          </Box>
          <ActionIcon variant="subtle" size="sm" onClick={() => scrollNav('right')} aria-label="Next months">
            <ChevronRight size={16} />
          </ActionIcon>
        </Group>
      </Box>

      <Box
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
          gap: 'var(--mantine-spacing-md)',
          alignItems: 'start',
        }}
      >
        {monthData.map(({ month, items: monthItems, total }) => {
          const compsThisMonth = comps.filter((c) => monthOf(c.start_date) === month)
          const overCap = monthlyCap > 0 && total > monthlyCap
          return (
            <Box key={month} style={{ display: 'contents' }}>
              {compsThisMonth.map((comp) => (
                <Box
                  key={`comp-${comp.master_id}`}
                  style={{ gridColumn: '1 / -1' }}
                  data-testid={`timeline-comp-${month}`}
                >
                  <Paper
                    radius="md"
                    p="sm"
                    style={{
                      background: 'var(--mantine-color-orange-0)',
                      border: '1px solid var(--mantine-color-orange-3)',
                      borderLeft: '4px solid var(--mantine-color-orange-5)',
                    }}
                  >
                    <Group gap="xs" align="center">
                      <Zap size={16} color="var(--mantine-color-orange-6)" />
                      <Text size="sm" fw={700}>
                        COMPETITION: {comp.name}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {formatCompDate(comp.start_date)}
                      </Text>
                      {comp.federation_label && (
                        <Badge variant="light" color="orange" size="xs">
                          {comp.federation_label}
                        </Badge>
                      )}
                    </Group>
                  </Paper>
                </Box>
              ))}

              <Box id={`timeline-month-${month}`} style={{ scrollMarginTop: 60 }}>
                <Paper withBorder radius="md" p="sm">
                  <Group justify="space-between" mb="xs" align="center">
                    <Text size="sm" fw={700}>
                      {monthLabel(month)}
                    </Text>
                    <Group gap="xs" align="center">
                      <Text
                        size="sm"
                        fw={600}
                        c={overCap ? 'var(--mantine-color-orange-6)' : undefined}
                      >
                        {formatCurrency(total, currency)}
                      </Text>
                      {overCap && (
                        <Badge color="orange" variant="light" size="xs">
                          over cap
                        </Badge>
                      )}
                    </Group>
                  </Group>
                  <Divider mb="xs" />
                  {monthItems.length === 0 ? (
                    <Text size="xs" c="dimmed" py="xs" ta="center">
                      No expenses this month
                    </Text>
                  ) : (
                    <Stack gap={6}>
                      {monthItems.map((item) => (
                        <MonthRow key={item.id} item={item} currency={currency} />
                      ))}
                    </Stack>
                  )}
                </Paper>
              </Box>
            </Box>
          )
        })}
      </Box>
    </Stack>
  )
}

interface MonthRowProps {
  item: BudgetItem
  currency: string
}

function MonthRow({ item, currency }: MonthRowProps) {
  const tier = itemTier(item)
  const recurring = isRecurring(item)
  const linked = compLinked(item)
  const rec = item.recurrence
  const sym = currencySymbol(currency) || ''

  const icon = linked ? (
    <Zap size={13} color="var(--mantine-color-orange-6)" />
  ) : recurring ? (
    <Repeat size={13} color="var(--mantine-color-dimmed)" />
  ) : (
    <Box
      style={{
        width: 5,
        height: 5,
        borderRadius: '50%',
        background: 'var(--mantine-color-dimmed)',
        flexShrink: 0,
      }}
    />
  )

  return (
    <Group
      gap="xs"
      align="center"
      wrap="nowrap"
      style={{
        opacity: recurring ? 0.85 : 1,
      }}
      data-testid={`timeline-item-${item.id}`}
    >
      <Box style={{ flexShrink: 0, display: 'flex', alignItems: 'center' }}>{icon}</Box>
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Group gap={6} align="center" wrap="nowrap">
          <Text size="sm" fw={500} truncate style={{ minWidth: 0 }}>
            {item.name || 'Untitled'}
          </Text>
          <Badge variant={tierBadgeVariant(tier)} color={tierColor(tier)} size="xs">
            {TIER_LABELS[tier]}
          </Badge>
        </Group>
        <Group gap={6} align="center" wrap="nowrap" mt={2}>
          <Text size="xs" c="dimmed">{recurrenceLabel(rec)}</Text>
          <Text size="xs" c="dimmed">·</Text>
          <Text size="xs" c="dimmed">{datePeriodLabel(item)}</Text>
        </Group>
      </Box>
      <Text size="sm" fw={600} style={{ whiteSpace: 'nowrap', flexShrink: 0 }}>
        {sym}{item.cost.toFixed(2)}
      </Text>
    </Group>
  )
}

interface FilterBarProps {
  filters: TimelineFilters
  onFilterChange: (next: Partial<TimelineFilters>) => void
  categoryOptions: { value: string; label: string }[]
  priorityOptions: { value: string; label: string }[]
  isMobile: boolean
  filterOpen: boolean
  setFilterOpen: (open: boolean) => void
  filtCount: number
}

function FilterBar({
  filters,
  onFilterChange,
  categoryOptions,
  priorityOptions,
  isMobile,
  filterOpen,
  setFilterOpen,
  filtCount,
}: FilterBarProps) {
  if (isMobile) {
    return (
      <Stack gap="xs">
        <Group justify="space-between" align="center">
          <ActionIcon
            variant="light"
            size="sm"
            onClick={() => setFilterOpen(!filterOpen)}
            aria-label="Toggle filters"
          >
            <Filter size={16} />
          </ActionIcon>
          {filtCount > 0 && (
            <Badge color="brand" size="xs">
              {filtCount} active
            </Badge>
          )}
        </Group>
        {filterOpen && (
          <Stack gap="xs">
            <MultiSelect
              label="Priority"
              size="xs"
              clearable
              searchable
              placeholder="All priorities"
              data={priorityOptions}
              value={filters.priorities}
              onChange={(v) => onFilterChange({ priorities: v as BudgetPriorityTier[] })}
            />
            <MultiSelect
              label="Category"
              size="xs"
              clearable
              searchable
              placeholder="All categories"
              data={categoryOptions}
              value={filters.categories}
              onChange={(v) => onFilterChange({ categories: v as BudgetCategory[] })}
            />
            <Switch
              size="xs"
              label="Comp-linked only"
              checked={filters.compLinkedOnly}
              onChange={(e) => onFilterChange({ compLinkedOnly: e.currentTarget.checked })}
            />
          </Stack>
        )}
      </Stack>
    )
  }

  return (
    <Group gap="sm" align="flex-end" wrap="wrap">
      <MultiSelect
        size="xs"
        clearable
        searchable
        placeholder="All priorities"
        data={priorityOptions}
        value={filters.priorities}
        onChange={(v) => onFilterChange({ priorities: v as BudgetPriorityTier[] })}
        style={{ width: 180 }}
      />
      <MultiSelect
        size="xs"
        clearable
        searchable
        placeholder="All categories"
        data={categoryOptions}
        value={filters.categories}
        onChange={(v) => onFilterChange({ categories: v as BudgetCategory[] })}
        style={{ width: 200 }}
      />
      <Switch
        size="xs"
        label="Comp-linked only"
        checked={filters.compLinkedOnly}
        onChange={(e) => onFilterChange({ compLinkedOnly: e.currentTarget.checked })}
      />
    </Group>
  )
}
