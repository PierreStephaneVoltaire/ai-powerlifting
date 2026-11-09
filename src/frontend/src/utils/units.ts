const KG_TO_LB = 2.20462
const LB_TO_KG = 1 / KG_TO_LB

export const kgToLb = (kg: number): number =>
  parseFloat((kg * KG_TO_LB).toFixed(1))

export const lbToKg = (lb: number): number =>
  parseFloat((lb * LB_TO_KG).toFixed(3))

export const fromDisplayBodyweight = (value: number, unit: 'kg' | 'lb'): number =>
  unit === 'lb' ? value * LB_TO_KG : value

export const toDisplayBodyweight = (kg: number, unit: 'kg' | 'lb'): number =>
  Number((unit === 'lb' ? kg * KG_TO_LB : kg).toFixed(2))

export const toDisplayUnit = (kg: number, unit: 'kg' | 'lb'): number =>
  unit === 'lb' ? Math.round(kg * KG_TO_LB) : kg

export const formatDisplayWeight = (kg: number, unit: 'kg' | 'lb'): string =>
  unit === 'lb' ? String(toDisplayUnit(kg, unit)) : toDisplayUnit(kg, unit).toFixed(1)

export const formatBodyweight = (kg: number, unit: 'kg' | 'lb'): string =>
  String(toDisplayBodyweight(kg, unit))

export const displayBodyweight = (kg: number, unit: 'kg' | 'lb'): string =>
  `${formatBodyweight(kg, unit)} ${unit}`

export const displayWeight = (kg: number, unit: 'kg' | 'lb'): string =>
  unit === 'lb' ? `${toDisplayUnit(kg, unit)} lb` : `${kg} kg`

export const fromDisplayUnit = (value: number, unit: 'kg' | 'lb'): number =>
  unit === 'lb' ? lbToKg(value) : value

export const roundToNearest = (value: number, increment: number = 2.5): number =>
  Math.round(value / increment) * increment
