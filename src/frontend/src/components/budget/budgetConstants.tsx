import {
  Dumbbell, Pill, Building2, Trophy, Users, Smartphone, Flag, Plane, Sandwich,
  UtensilsCrossed, Scale, CookingPot, HeartPulse, MoreHorizontal,
  Repeat, Dot
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { BudgetCategory, BudgetRecurrence, BudgetPriorityTier } from '@powerlifting/types'

interface OptionRow {
  value: BudgetCategory
  label: string
  icon: LucideIcon
}

export const CATEGORY_OPTIONS: OptionRow[] = [
  { value: 'equipment', label: 'Equipment', icon: Dumbbell },
  { value: 'supplement', label: 'Supplement', icon: Pill },
  { value: 'gym_membership', label: 'Gym membership', icon: Building2 },
  { value: 'federation_membership', label: 'Federation membership', icon: Trophy },
  { value: 'coaching', label: 'Coaching', icon: Users },
  { value: 'app_subscription', label: 'App subscription', icon: Smartphone },
  { value: 'competition_entry', label: 'Competition entry', icon: Flag },
  { value: 'transport', label: 'Transport', icon: Plane },
  { value: 'accommodation', label: 'Accommodation', icon: Sandwich },
  { value: 'food_comp_day', label: 'Comp-day food', icon: UtensilsCrossed },
  { value: 'food_weigh_in', label: 'Weigh-in food', icon: Scale },
  { value: 'food_prep', label: 'Prep food', icon: CookingPot },
  { value: 'recovery', label: 'Recovery', icon: HeartPulse },
  { value: 'other', label: 'Other', icon: MoreHorizontal },
]

const CATEGORY_BY_VALUE: Record<BudgetCategory, OptionRow> =
  Object.fromEntries(CATEGORY_OPTIONS.map((o) => [o.value, o])) as Record<BudgetCategory, OptionRow>

export function categoryIcon(category: BudgetCategory): LucideIcon {
  return CATEGORY_BY_VALUE[category]?.icon ?? MoreHorizontal
}

export const RECURRENCE_OPTIONS: { value: BudgetRecurrence; label: string }[] = [
  { value: 'ONE_TIME', label: 'One-time' },
  { value: 'MONTHLY', label: 'Monthly' },
  { value: 'QUARTERLY', label: 'Quarterly' },
  { value: 'ANNUAL', label: 'Annual' },
]

export function recurrenceIcon(recurrence: BudgetRecurrence): LucideIcon {
  return recurrence === 'ONE_TIME' ? Dot : Repeat
}

interface PriorityStyle {
  label: string
  color: string
  variant: 'filled' | 'light' | 'outline'
}

export const PRIORITY_STYLES: Record<BudgetPriorityTier, PriorityStyle> = {
  MANDATORY: { label: 'Mandatory', color: 'blue', variant: 'filled' },
  IMPORTANT: { label: 'Important', color: 'indigo', variant: 'filled' },
  OPTIONAL: { label: 'Optional', color: 'gray', variant: 'outline' },
}
