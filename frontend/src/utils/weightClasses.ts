import type { FederationSex } from '@powerlifting/types'

const DEFAULT_WEIGHT_CLASSES_MALE: number[] = [53, 59, 66, 74, 83, 93, 105, 120]
const DEFAULT_WEIGHT_CLASSES_FEMALE: number[] = [43, 47, 52, 57, 63, 69, 76, 84]

export function defaultWeightClassesForSex(sex: FederationSex): number[] {
  return sex === 'female' ? [...DEFAULT_WEIGHT_CLASSES_FEMALE] : [...DEFAULT_WEIGHT_CLASSES_MALE]
}

export function normalizeWeightClasses(values: Array<number | string | null | undefined>): number[] {
  const seen = new Set<number>()
  for (const raw of values) {
    if (raw === null || raw === undefined) continue
    const num = typeof raw === 'number' ? raw : Number(raw)
    if (Number.isFinite(num) && num > 0) seen.add(num)
  }
  return [...seen].sort((a, b) => a - b)
}

export function defaultWeightClassStringList(sex: FederationSex): string {
  return defaultWeightClassesForSex(sex).join(', ')
}

export function newEntryId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `std-${crypto.randomUUID()}`
  }
  return `std-${Date.now()}-${Math.floor(Math.random() * 1e6)}`
}
