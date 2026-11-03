import type { BudgetItem, BudgetConfig, BudgetPriorityTier, BudgetRecurrence } from '@powerlifting/types'

export type { BudgetPriorityTier, BudgetRecurrence }

export const BUDGET_TIER_VALUES: ReadonlyArray<BudgetPriorityTier> = [
  'MANDATORY',
  'IMPORTANT',
  'OPTIONAL',
]

export interface TierTotals {
  count: number
  total: number
}

export interface BudgetSummaryLocal {
  monthly_cap: number
  currency: string
  spent_this_month: number
  recurring_monthly_total: number
  items_by_priority: {
    MANDATORY: TierTotals
    IMPORTANT: TierTotals
    OPTIONAL: TierTotals
  }
  upcoming_one_time: BudgetItem[]
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  CAD: '$',
  USD: '$',
  AUD: '$',
  NZD: '$',
  HKD: '$',
  SGD: '$',
  EUR: '\u20AC',
  GBP: '\u00A3',
  JPY: '\u00A5',
  CNY: '\u00A5',
}

export function currencySymbol(currency?: string | null): string {
  if (!currency) return ''
  return CURRENCY_SYMBOLS[currency] ?? ''
}

export function formatCurrency(amount: number, currency?: string | null): string {
  const sym = currencySymbol(currency)
  if (!sym) return amount.toFixed(2)
  return `${sym}${amount.toFixed(2)}`
}

export function currentMonthKey(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function monthKeyFromDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function monthLabel(key: string): string {
  const [y, m] = key.split('-').map(Number)
  if (!y || !m) return key
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  })
}

export function monthShortLabel(key: string): string {
  const [y, m] = key.split('-').map(Number)
  if (!y || !m) return key
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: 'short' })
}

export function isRecurring(item: BudgetItem): boolean {
  return item.recurrence !== 'ONE_TIME'
}

export function monthlyCost(item: BudgetItem): number {
  switch (item.recurrence) {
    case 'MONTHLY':
      return item.cost
    case 'QUARTERLY':
      return item.cost / 3
    case 'ANNUAL':
      return item.cost / 12
    default:
      return 0
  }
}

export function itemTier(item: BudgetItem): BudgetPriorityTier {
  return item.priority_tier
}

export function compLinked(item: BudgetItem): boolean {
  return item.comp_linked
}

function monthOf(value?: string | null): string {
  return (value ?? '').slice(0, 7)
}

export function purchasedInMonth(item: BudgetItem, month: string): boolean {
  if (!item.purchased) return false
  return monthOf(item.purchased_date) === month
}

export function activeInMonth(item: BudgetItem, month: string): boolean {
  if (item.recurrence === 'ONE_TIME') {
    return monthOf(item.start_date) === month
  }
  const startMonth = monthOf(item.start_date)
  if (!startMonth) return false
  const endMonth = monthOf(item.end_date) || '9999-99'
  return month >= startMonth && month <= endMonth
}

export function buildBudgetSummary(
  items: BudgetItem[],
  config: BudgetConfig,
  month: string,
): BudgetSummaryLocal {
  const recurring = items.filter(isRecurring)
  const recurring_monthly_total = recurring.reduce((s, i) => s + monthlyCost(i), 0)
  const spent_this_month = items
    .filter((i) => purchasedInMonth(i, month))
    .reduce((s, i) => s + i.cost, 0)

  const items_by_priority = {
    MANDATORY: { count: 0, total: 0 },
    IMPORTANT: { count: 0, total: 0 },
    OPTIONAL: { count: 0, total: 0 },
  }

  for (const i of items) {
    if (!purchasedInMonth(i, month)) continue
    const tier = itemTier(i)
    items_by_priority[tier].count += 1
    items_by_priority[tier].total += i.cost
  }

  const upcoming_one_time = items
    .filter((i) => i.recurrence === 'ONE_TIME' && !i.purchased)
    .sort((a, b) =>
      (monthOf(a.start_date) || '9999-99').localeCompare(monthOf(b.start_date) || '9999-99'),
    )

  return {
    monthly_cap: config.monthly_cap,
    currency: config.currency,
    spent_this_month,
    recurring_monthly_total,
    items_by_priority,
    upcoming_one_time,
  }
}

export interface MonthSpendPoint {
  month: string
  label: string
  spent: number
  over: boolean
}

export function buildMonthSpendTrend(
  items: BudgetItem[],
  monthlyCap: number,
  monthCount: number,
  anchorMonth = currentMonthKey(),
): MonthSpendPoint[] {
  const points: MonthSpendPoint[] = []
  const [ay, am] = anchorMonth.split('-').map(Number)
  const anchorDate = new Date(ay, am - 1, 1)
  const start = new Date(anchorDate.getFullYear(), anchorDate.getMonth() - (monthCount - 1), 1)
  for (let i = 0; i < monthCount; i++) {
    const d = new Date(start.getFullYear(), start.getMonth() + i, 1)
    const key = monthKeyFromDate(d)
    const spent = items
      .filter((it) => purchasedInMonth(it, key))
      .reduce((s, it) => s + it.cost, 0)
    points.push({
      month: key,
      label: monthShortLabel(key),
      spent,
      over: monthlyCap > 0 && spent > monthlyCap,
    })
  }
  return points
}

export function hasEnoughTrendData(
  items: BudgetItem[],
  monthCount: number,
  anchorMonth = currentMonthKey(),
): boolean {
  const trend = buildMonthSpendTrend(items, 0, monthCount, anchorMonth)
  return trend.filter((p) => p.spent > 0).length >= 2
}