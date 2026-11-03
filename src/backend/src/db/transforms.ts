import type { Program, Session, Phase } from '@powerlifting/types'

function parseWeekNumber(weekLabel: string | number | undefined): number {
  if (typeof weekLabel === 'number') {
    return weekLabel
  }
  if (!weekLabel) {
    return 0
  }
  // Try to match "W<number>" pattern first
  const match = weekLabel.match(/W(\d+)/i)
  if (match) {
    return parseInt(match[1], 10)
  }
  // Try to parse as plain number
  const num = parseInt(weekLabel, 10)
  return isNaN(num) ? 0 : num
}

const DEFAULT_BLOCK = 'current'

function phaseBlock(p: Phase): string {
  return p.block ?? DEFAULT_BLOCK
}

function sessionBlock(s: Session): string {
  return s.block ?? DEFAULT_BLOCK
}

function resolvePhase(weekNum: number, block: string, phases: Phase[]): Phase {
  if (weekNum <= 0 || phases.length === 0) {
    return { name: 'Unscheduled', intent: '', start_week: 0, end_week: 0, block }
  }
  const phase = phases.find(
    p => phaseBlock(p) === block && weekNum >= p.start_week && weekNum <= p.end_week
  )
  return phase ?? { name: 'Unscheduled', intent: '', start_week: weekNum, end_week: weekNum, block }
}

export function transformProgram(item: Record<string, unknown>): Program {
  const program = item as unknown as Program
  const legacyBlockNotes = Array.isArray((item as { block_notes?: unknown }).block_notes)
    ? (item as { block_notes: Program['meta']['block_notes'] }).block_notes
    : []

  // Ensure sessions and phases arrays exist
  if (!program.sessions) {
    program.sessions = []
  }
  if (!program.phases) {
    program.phases = []
  }
  if (!program.competitions) {
    program.competitions = []
  }
  if (!program.diet_notes) {
    program.diet_notes = []
  }
  if (!program.supplements) {
    program.supplements = []
  }
  if (!program.supplement_phases) {
    program.supplement_phases = []
  }
  if (!Array.isArray(program.meta.block_notes) || (program.meta.block_notes.length === 0 && legacyBlockNotes.length > 0)) {
    program.meta.block_notes = legacyBlockNotes
  }

  // Derive week_number and resolve phase for each session within its block
  program.sessions = program.sessions.map(session => {
    const weekNum = typeof session.week_number === 'number'
      ? session.week_number
      : parseWeekNumber(session.week as string | number | undefined)
    const block = sessionBlock(session)
    const phase = resolvePhase(weekNum, block, program.phases)

    return {
      ...session,
      week_number: weekNum,
      phase,
      phase_name: phase.name,
    }
  })

  // Sort sessions by date
  program.sessions.sort((a, b) => a.date.localeCompare(b.date))

  return program
}

export function getCurrentWeek(programStart: string): number {
  const start = new Date(programStart)
  const now = new Date()
  const diffTime = now.getTime() - start.getTime()
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24))
  return Math.max(1, Math.floor(diffDays / 7) + 1)
}


import type {
  BudgetItem,
  BudgetConfig,
  BudgetCategory,
  BudgetPriorityTier,
  BudgetRecurrence,
  BudgetDatePrecision,
} from '@powerlifting/types'

const BUDGET_CATEGORY_VALUES: ReadonlyArray<BudgetCategory> = [
  'equipment', 'supplement', 'gym_membership', 'federation_membership',
  'coaching', 'app_subscription', 'competition_entry', 'transport',
  'accommodation', 'food_comp_day', 'food_weigh_in', 'food_prep',
  'recovery', 'other',
]
const RECURRENCE_VALUES: ReadonlyArray<BudgetRecurrence> = ['ONE_TIME', 'MONTHLY', 'QUARTERLY', 'ANNUAL']
const PRIORITY_TIER_VALUES: ReadonlyArray<BudgetPriorityTier> = ['MANDATORY', 'IMPORTANT', 'OPTIONAL']
const DATE_PRECISION_VALUES: ReadonlyArray<BudgetDatePrecision> = ['exact', 'month']

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toFiniteNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const num = Number(value)
    if (Number.isFinite(num)) return num
  }
  return 0
}

function pickEnum<T extends string>(value: unknown, allowed: ReadonlyArray<T>, fallback: T): T {
  return typeof value === 'string' && (allowed as ReadonlyArray<string>).includes(value) ? (value as T) : fallback
}

function normalizeCategory(raw: unknown): BudgetCategory {
  return pickEnum(raw, BUDGET_CATEGORY_VALUES, 'other')
}

function normalizeRecurrence(raw: unknown): BudgetRecurrence {
  return pickEnum(raw, RECURRENCE_VALUES, 'ONE_TIME')
}

function normalizePriorityTier(raw: unknown): BudgetPriorityTier {
  return pickEnum(raw, PRIORITY_TIER_VALUES, 'OPTIONAL')
}

function normalizeDatePrecision(raw: unknown): BudgetDatePrecision {
  return pickEnum(raw, DATE_PRECISION_VALUES, 'month')
}

function trimToNull(v: unknown): string | null {
  if (typeof v !== 'string') return null
  const t = v.trim()
  return t.length ? t : null
}

function defaultStartDate(precision: BudgetDatePrecision): string {
  const now = new Date().toISOString()
  return precision === 'exact' ? now.slice(0, 10) : now.slice(0, 7)
}

/**
 * Normalize a stored DynamoDB item into the canonical BudgetItem shape.
 * pk is the partition key the item lived under.
 */
export function normalizeBudgetItemFromStore(
  stored: Record<string, unknown> | BudgetItem,
  pk: string,
): BudgetItem {
  const r = (stored ?? {}) as Record<string, unknown>
  const purchasedDate = trimToNull(r.purchased_date)
  const recurrence = normalizeRecurrence(r.recurrence)
  const competitionId =
    typeof r.competition_id === 'string' && r.competition_id
      ? r.competition_id
      : null
  return {
    id: typeof r.id === 'string' && r.id ? r.id : '',
    user_pk: typeof r.user_pk === 'string' && r.user_pk ? r.user_pk : pk,
    name: typeof r.name === 'string' ? r.name : '',
    category: normalizeCategory(r.category),
    priority_tier: normalizePriorityTier(r.priority_tier),
    cost: Math.max(0, toFiniteNumber(r.cost)),
    currency: typeof r.currency === 'string' && r.currency.trim() ? r.currency.trim() : 'CAD',
    recurrence,
    date_precision: normalizeDatePrecision(r.date_precision),
    start_date: typeof r.start_date === 'string' && r.start_date ? r.start_date : defaultStartDate(normalizeDatePrecision(r.date_precision)),
    end_date: recurrence === 'ONE_TIME' ? null : trimToNull(r.end_date),
    comp_linked: typeof r.comp_linked === 'boolean' ? r.comp_linked : competitionId !== null,
    competition_id: competitionId,
    purchased: typeof r.purchased === 'boolean' ? r.purchased : false,
    purchased_date: purchasedDate,
    notes: trimToNull(r.notes),
    photo_s3_key: trimToNull(r.photo_s3_key),
    cut_by_ai: typeof r.cut_by_ai === 'boolean' ? r.cut_by_ai : false,
    created_at: typeof r.created_at === 'string' && r.created_at ? r.created_at : new Date().toISOString(),
    updated_at: typeof r.updated_at === 'string' && r.updated_at ? r.updated_at : new Date().toISOString(),
  }
}

/**
 * Normalize an inbound request body (POST/PUT item) into a storable canonical
 * BudgetItem. Carries forward preserved fields from `existing` when editing
 * and stamps updated_at = now.
 */
export function normalizeBudgetItemInput(
  raw: unknown,
  pk: string,
  id: string,
  existing: BudgetItem | undefined,
  now: string,
  existingCreatedAt?: string,
): BudgetItem {
  const r = isPlainObject(raw) ? raw : {}
  const purchased = typeof r.purchased === 'boolean' ? r.purchased : (existing?.purchased ?? false)
  const purchasedDate =
    typeof r.purchased_date === 'string'
      ? trimToNull(r.purchased_date)
      : purchased
        ? (existing?.purchased_date ?? now.slice(0, 10))
        : null
  const precision = normalizeDatePrecision(r.date_precision)
  const recurrence = normalizeRecurrence(r.recurrence ?? existing?.recurrence)
  const competitionId =
    typeof r.competition_id === 'string'
      ? trimToNull(r.competition_id)
      : (existing?.competition_id ?? null)
  const compLinked =
    typeof r.comp_linked === 'boolean'
      ? r.comp_linked
      : competitionId !== null
  const start_date =
    typeof r.start_date === 'string' && r.start_date.trim()
      ? r.start_date.trim()
      : (existing?.start_date ?? defaultStartDate(precision))

  return {
    id,
    user_pk: pk,
    name: typeof r.name === 'string' ? r.name : (existing?.name ?? ''),
    category: normalizeCategory(r.category ?? existing?.category),
    priority_tier: normalizePriorityTier(r.priority_tier ?? existing?.priority_tier),
    cost: Math.max(0, toFiniteNumber(r.cost ?? existing?.cost)),
    currency: typeof r.currency === 'string' && r.currency.trim() ? r.currency.trim() : (existing?.currency ?? 'CAD'),
    recurrence,
    date_precision: precision,
    start_date,
    end_date: recurrence === 'ONE_TIME' ? null : (typeof r.end_date === 'string' ? trimToNull(r.end_date) : (existing?.end_date ?? null)),
    comp_linked: compLinked,
    competition_id: competitionId,
    purchased,
    purchased_date: purchasedDate,
    notes: typeof r.notes === 'string' ? trimToNull(r.notes) : (existing?.notes ?? null),
    photo_s3_key: typeof r.photo_s3_key === 'string' ? trimToNull(r.photo_s3_key) : (existing?.photo_s3_key ?? null),
    cut_by_ai: typeof r.cut_by_ai === 'boolean' ? r.cut_by_ai : (existing?.cut_by_ai ?? false),
    created_at: existingCreatedAt ?? existing?.created_at ?? now,
    updated_at: now,
  }
}

/**
 * Normalize a stored (or inbound) budget config object.
 */
export function normalizeBudgetConfigFromStore(raw: unknown, pk: string): BudgetConfig {
  const maybeWrapped = isPlainObject((raw as { config?: unknown } | undefined)?.config) ? (raw as { config: Record<string, unknown> }).config : raw
  const r = isPlainObject(maybeWrapped) ? maybeWrapped : {}
  return {
    user_pk: typeof r.user_pk === 'string' && r.user_pk ? r.user_pk : pk,
    monthly_cap: Math.max(0, toFiniteNumber(r.monthly_cap)),
    currency: typeof r.currency === 'string' && r.currency.trim() ? r.currency.trim() : 'CAD',
    notes: trimToNull(r.notes),
    updated_at: typeof r.updated_at === 'string' && r.updated_at ? r.updated_at : new Date().toISOString(),
  }
}
