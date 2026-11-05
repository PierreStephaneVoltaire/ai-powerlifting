import type { BudgetItem, BudgetRecurrence } from '@powerlifting/types'

function parseLocalDate(dateStr: string): Date | null {
  if (!dateStr) return null
  const [y, m, d] = dateStr.slice(0, 10).split('-').map(Number)
  if (!y || !m) return null
  const date = d ? new Date(y, m - 1, d) : new Date(y, m - 1, 1)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatExact(dateStr?: string | null): string {
  const d = parseLocalDate(dateStr ?? '')
  if (!d) return '—'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function monthLabel(key: string): string {
  const [y, m] = key.split('-').map(Number)
  if (!y || !m) return key
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
}

export function monthOf(dateStr?: string | null): string {
  return (dateStr ?? '').slice(0, 7)
}

export function datePeriodLabel(item: BudgetItem): string {
  const start = monthOf(item.start_date)
  if (item.recurrence === 'ONE_TIME') {
    if (!item.start_date) return '—'
    if (item.date_precision === 'month' || start === item.start_date) return monthLabel(start)
    return formatExact(item.start_date)
  }
  const end = monthOf(item.end_date)
  if (start && end) return `${monthLabel(start)} – ${monthLabel(end)}`
  if (start) return `${monthLabel(start)} – ongoing`
  return '—'
}

function recurrenceCostSuffix(recurrence: BudgetRecurrence): string {
  switch (recurrence) {
    case 'MONTHLY': return '/mo'
    case 'QUARTERLY': return '/qtr'
    case 'ANNUAL': return '/yr'
    default: return ''
  }
}

export function formatCost(cost: number, currency?: string, recurrence?: BudgetRecurrence): string {
  const sym = currency ? `${currency} ` : '$'
  const suffix = recurrence ? recurrenceCostSuffix(recurrence) : ''
  return `${sym}${cost.toFixed(2)}${suffix}`
}

export function toPickerValue(value?: string | null): string | null {
  if (typeof value !== 'string' || !value) return null
  return value.slice(0, 10) || null
}

export function fromPickerValue(value: string | null): string | null {
  return value || null
}

export function toMonthPickerValue(value?: string | null): string | null {
  if (typeof value !== 'string' || !value) return null
  return value.slice(0, 7) || null
}

export function fromMonthPickerValue(value: string | null): string | null {
  return value ? `${value}-01` : null
}
