import { callOperation } from '../utils/operations'
import type { WeightEntry, WeightLogStore } from '@powerlifting/types'

export async function getWeightLog(pk: string, blockId?: string): Promise<WeightLogStore> {
  const result = await callOperation('weight_log_get', { pk, ...(blockId ? { block_id: blockId } : {}) })
  return {
    pk,
    sk: `weight_log#current`,
    entries: Array.isArray(result?.entries) ? result.entries : [],
    updated_at: result?.updated_at || new Date().toISOString(),
  }
}

export async function addWeightEntry(
  pk: string,
  entry: WeightEntry
): Promise<void> {
  await callOperation('weight_log_add', { pk,
    date: entry.date,
    weight_kg: entry.kg,
    entry,
  })
}

export async function removeWeightEntry(
  pk: string,
  date: string
): Promise<void> {
  await callOperation('weight_log_remove', { pk, date })
}
