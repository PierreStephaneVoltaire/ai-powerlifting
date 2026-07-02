import { invokeLambda } from '../utils/lambda'
import type { DietNote } from '@powerlifting/types'

export async function updateDietNotes(
  pk: string,
  _version: string,
  dietNotes: DietNote[]
): Promise<void> {
  // TODO: full replacement is emulated date-by-date because no bulk
  // `health_replace_diet_notes` handler exists yet.
  const current = await getDietNotes(pk, _version)
  const newDates = new Set(dietNotes.map((n) => n.date))
  const currentDates = new Set(current.map((n) => n.date))

  for (const note of dietNotes) {
    await invokeLambda('health_update_diet_note', {
      pk,
      date: note.date,
      notes: note.notes,
    })
  }

  for (const date of currentDates) {
    if (!newDates.has(date)) {
      await invokeLambda('health_delete_diet_note', { pk, date })
    }
  }
}

export async function getDietNotes(pk: string, _version: string): Promise<DietNote[]> {
  const result = await invokeLambda('health_get_diet_notes', { pk })
  return Array.isArray(result) ? result : []
}
