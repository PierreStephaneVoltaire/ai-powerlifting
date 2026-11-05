import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Sex } from '@powerlifting/types'
import { normalizePlateInventory } from '@/utils/plateInventory'
import { lbToKg } from '@/utils/units'

export type Unit = 'kg' | 'lb'
export type Theme = 'light' | 'dark' | 'system'
type SessionsView = 'Month' | 'Agenda' | 'Compact'

export const CURRENCY_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'CAD', label: 'CAD — Canadian Dollar' },
  { value: 'USD', label: 'USD — US Dollar' },
  { value: 'EUR', label: 'EUR — Euro' },
  { value: 'GBP', label: 'GBP — British Pound' },
  { value: 'AUD', label: 'AUD — Australian Dollar' },
  { value: 'NZD', label: 'NZD — New Zealand Dollar' },
  { value: 'JPY', label: 'JPY — Japanese Yen' },
  { value: 'CNY', label: 'CNY — Chinese Yuan' },
  { value: 'HKD', label: 'HKD — Hong Kong Dollar' },
  { value: 'SGD', label: 'SGD — Singapore Dollar' },
]

interface SettingsState {
  unit: Unit
  barWeightKg: number
  barWeightCustomized: boolean
  sex: Sex
  theme: Theme
  defaultSessionsView: SessionsView
  plateInventoryKg: number[]
  plateInventoryLb: number[]
  currency: string

  // Actions
  toggleUnit: () => void
  setBarWeight: (kg: number) => void
  setSex: (sex: Sex) => void
  setTheme: (theme: Theme) => void
  setDefaultSessionsView: (view: SessionsView) => void
  setPlateInventoryKg: (plates: number[]) => void
  setPlateInventoryLb: (plates: number[]) => void
  setCurrency: (currency: string) => void
}

const DEFAULT_BAR_WEIGHT_KG: Record<Unit, number> = {
  kg: 20,
  lb: lbToKg(45),
}
const MANTINE_COLOR_SCHEME_KEY = 'mantine-color-scheme-value'

function isNear(value: number, target: number, tolerance = 0.02): boolean {
  return Math.abs(value - target) <= tolerance
}

export function defaultBarWeightKgForUnit(unit: Unit): number {
  return DEFAULT_BAR_WEIGHT_KG[unit]
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  const resolved = theme === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme

  try {
    window.localStorage.setItem(MANTINE_COLOR_SCHEME_KEY, theme === 'system' ? 'auto' : theme)
  } catch {
    // Ignore storage errors; the DOM attributes still keep the current page in sync.
  }

  if (resolved === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }

  // Set Mantine color scheme attribute
  root.setAttribute('data-mantine-color-scheme', resolved)
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      unit: 'kg',
      barWeightKg: defaultBarWeightKgForUnit('kg'),
      barWeightCustomized: false,
      sex: 'male',
      theme: 'system',
      defaultSessionsView: 'Agenda',
      plateInventoryKg: [],
      plateInventoryLb: [],
      currency: 'CAD',

      toggleUnit: () =>
        set((s) => {
          const nextUnit: Unit = s.unit === 'kg' ? 'lb' : 'kg'
          return {
            unit: nextUnit,
            barWeightKg: s.barWeightCustomized
              ? s.barWeightKg
              : defaultBarWeightKgForUnit(nextUnit),
          }
        }),

      setBarWeight: (kg) =>
        set((s) => ({
          barWeightKg: kg,
          barWeightCustomized: !isNear(kg, defaultBarWeightKgForUnit(s.unit)),
        })),

      setSex: (sex) => set({ sex }),

      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },

      setDefaultSessionsView: (defaultSessionsView) => set({ defaultSessionsView }),

      setPlateInventoryKg: (plates) => set({ plateInventoryKg: normalizePlateInventory(plates) }),

      setPlateInventoryLb: (plates) => set({ plateInventoryLb: normalizePlateInventory(plates) }),

      setCurrency: (currency) => set({ currency }),
    }),
    {
      name: 'pl-settings',
      onRehydrateStorage: () => (state) => {
        // Apply theme on load
        if (state?.theme) {
          applyTheme(state.theme)
        }
      },
    }
  )
)
