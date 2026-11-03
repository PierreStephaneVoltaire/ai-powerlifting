import type { PlateUnit } from '@powerlifting/types'

const DEFAULT_KG_PLATE_INVENTORY = [25, 20, 15, 10, 5, 2.5, 1.25, 1, 0.5]
const DEFAULT_LB_PLATE_INVENTORY = [45, 35, 25, 10, 5, 2.5, 1.25]

export function normalizePlateInventory(plates: Array<number | null | undefined>): number[] {
  const seen = new Set<number>()
  const normalized: number[] = []

  for (const plate of plates) {
    if (typeof plate !== 'number' || !Number.isFinite(plate)) continue
    const rounded = parseFloat(plate.toFixed(2))
    if (rounded <= 0) continue
    if (seen.has(rounded)) continue
    seen.add(rounded)
    normalized.push(rounded)
  }

  return normalized.sort((a, b) => b - a)
}

export function defaultPlateInventory(unit: PlateUnit): number[] {
  return unit === 'kg'
    ? [...DEFAULT_KG_PLATE_INVENTORY]
    : [...DEFAULT_LB_PLATE_INVENTORY]
}

export function resolvePlateInventory(unit: PlateUnit, plates: Array<number | null | undefined>): number[] {
  const normalized = normalizePlateInventory(plates)
  return normalized.length > 0 ? normalized : defaultPlateInventory(unit)
}
