// KG plates — full set including all fractional plates
export const KG_PLATES: readonly number[] = [
  25, 20, 15, 10, 5, 2.5, 1.25, 1, 0.75, 0.5, 0.25
]

// LB plates — full set including 1.25lb fractional
export const LB_PLATES: readonly number[] = [
  45, 35, 25, 10, 5, 2.5, 1.25
]

// Bar weights in kg
export const BAR_WEIGHTS_KG = {
  standard: 20,    // standard Olympic bar
  womens: 15,      // women's / lighter bar
  deadlift: 25,    // stiff deadlift bar / Texas deadlift bar
  custom: 0,       // user-specified
} as const

export type BarPreset = keyof typeof BAR_WEIGHTS_KG

// Plate colors for visual display
export const KG_PLATE_COLORS: Record<number, string> = {
  25: '#b91c1c',   // dark red
  20: '#1d4ed8',   // blue
  15: '#d97706',   // amber
  10: '#15803d',   // green
  5: '#f3f4f6',    // near-white (bordered)
  2.5: '#d1d5db',  // light grey
  1.25: '#e5e7eb', // lighter grey
  1: '#f0fdf4',    // very light green
  0.75: '#fff7ed', // very light amber
  0.5: '#fafafa',  // off-white
  0.25: '#ffffff', // white (bordered)
}

export const LB_PLATE_COLORS: Record<number, string> = {
  45: '#7f1d1d',   // deep red
  35: '#1e3a8a',   // deep blue
  25: '#92400e',   // brown
  10: '#14532d',   // dark green
  5: '#f3f4f6',    // near-white
  2.5: '#d1d5db',  // light grey
  1.25: '#e5e7eb', // lighter grey
}
