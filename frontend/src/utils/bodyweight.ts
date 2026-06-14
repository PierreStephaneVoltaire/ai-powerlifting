import type { Session, WeightEntry } from '@powerlifting/types'

export interface BodyweightTrend {
  latest: number
  oldest: number
  change: number
  entries: WeightEntry[]
  count: number
}

function validBodyweight(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

function validDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
}

export function mergeBodyweightEntries(
  weightLog: WeightEntry[],
  sessions: Session[] = [],
): WeightEntry[] {
  const byDate = new Map<string, WeightEntry>()

  for (const entry of weightLog) {
    if (validDate(entry.date) && validBodyweight(entry.kg)) {
      byDate.set(entry.date, { date: entry.date, kg: entry.kg })
    }
  }

  for (const session of [...sessions].sort((a, b) => a.date.localeCompare(b.date))) {
    if (
      session.status !== 'skipped' &&
      validDate(session.date) &&
      validBodyweight(session.body_weight_kg)
    ) {
      byDate.set(session.date, { date: session.date, kg: session.body_weight_kg })
    }
  }

  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))
}

export function latestBodyweightOnOrBefore(
  entries: WeightEntry[],
  date: string,
  fallback: number | null = null,
): number | null {
  const match = [...entries]
    .filter((entry) => entry.date <= date && validBodyweight(entry.kg))
    .sort((a, b) => b.date.localeCompare(a.date))[0]
  return match?.kg ?? fallback
}

export function buildBodyweightTrend(
  entries: WeightEntry[],
  startDate: string,
  endDate: string,
  maxEntries = 8,
): BodyweightTrend | null {
  const sorted = [...entries]
    .filter((entry) => entry.date <= endDate && validBodyweight(entry.kg))
    .sort((a, b) => a.date.localeCompare(b.date))

  const windowEntries = sorted.filter((entry) => entry.date >= startDate && entry.date <= endDate)
  const scoped = windowEntries.length >= 2 ? windowEntries : sorted
  if (scoped.length < 2) return null

  const oldest = scoped[0].kg
  const latest = scoped[scoped.length - 1].kg
  return {
    latest,
    oldest,
    change: latest - oldest,
    entries: scoped.slice(-maxEntries),
    count: scoped.length,
  }
}
