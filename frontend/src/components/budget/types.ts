import type {
  BudgetItem,
  BudgetCategory,
  BudgetRecurrence,
  BudgetPriorityTier,
  BudgetDatePrecision,
} from '@powerlifting/types'

export type {
  BudgetItem,
  BudgetCategory,
  BudgetRecurrence,
  BudgetPriorityTier,
  BudgetDatePrecision,
}

export const PRIORITY_VALUES: ReadonlyArray<BudgetPriorityTier> = ['MANDATORY', 'IMPORTANT', 'OPTIONAL']

export const PRIORITY_ORDER: Record<BudgetPriorityTier, number> = {
  MANDATORY: 0,
  IMPORTANT: 1,
  OPTIONAL: 2,
}

export const COMP_LINK_CATEGORIES: ReadonlyArray<BudgetCategory> = [
  'competition_entry', 'transport', 'accommodation', 'food_comp_day', 'food_weigh_in',
]

export function newItemId(): string {
  return `item-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`
}

export function nowIso(): string { return new Date().toISOString() }
export function todayIso(): string { return new Date().toISOString().slice(0, 10) }
export function currentMonth(): string { return new Date().toISOString().slice(0, 7) }

export function defaultRecurrence(category: BudgetCategory): BudgetRecurrence {
  switch (category) {
    case 'gym_membership':
    case 'coaching':
    case 'supplement':
      return 'MONTHLY'
    case 'federation_membership':
      return 'ANNUAL'
    default:
      return 'ONE_TIME'
  }
}

export function defaultPriority(category: BudgetCategory, compLinked: boolean): BudgetPriorityTier {
  if (compLinked) return 'MANDATORY'
  switch (category) {
    case 'competition_entry':
    case 'federation_membership':
      return 'MANDATORY'
    case 'gym_membership':
    case 'coaching':
    case 'equipment':
      return 'IMPORTANT'
    default:
      return 'OPTIONAL'
  }
}

export function nextPriority(p: BudgetPriorityTier): BudgetPriorityTier {
  if (p === 'MANDATORY') return 'IMPORTANT'
  if (p === 'IMPORTANT') return 'OPTIONAL'
  return 'MANDATORY'
}

export function makeBlankItem(category: BudgetCategory = 'other', userPk = ''): BudgetItem {
  const recurrence = defaultRecurrence(category)
  const compLinked = COMP_LINK_CATEGORIES.includes(category)
  const precision: BudgetDatePrecision = recurrence === 'ONE_TIME' && !compLinked ? 'month' : 'exact'
  const now = nowIso()
  return {
    id: newItemId(),
    user_pk: userPk,
    name: '',
    category,
    priority_tier: defaultPriority(category, compLinked),
    cost: 0,
    currency: 'CAD',
    recurrence,
    date_precision: precision,
    start_date: recurrence === 'ONE_TIME' ? (precision === 'month' ? currentMonth() : todayIso()) : currentMonth(),
    end_date: null,
    comp_linked: compLinked,
    competition_id: null,
    purchased: false,
    purchased_date: null,
    notes: null,
    photo_s3_key: null,
    cut_by_ai: false,
    created_at: now,
    updated_at: now,
  }
}
