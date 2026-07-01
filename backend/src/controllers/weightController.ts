import { invokeLambda } from '../utils/lambda'
import type { WeightEntry, WeightLogStore } from '@powerlifting/types'

export async function getWeightLog(pk: string, version: string): Promise<WeightLogStore> {
  const result = await invokeLambda('weight_log_get', { pk, version })
  return {
    pk,
    sk: `weight_log#${version}`,
    entries: Array.isArray(result?.entries) ? result.entries : [],
    updated_at: result?.updated_at || new Date().toISOString(),
  }
}

export async function addWeightEntry(
  pk: string,
  version: string,
  entry: WeightEntry
): Promise<void> {
  await invokeLambda('weight_log_add', {
    pk,
    version,
    date: entry.date,
    weight_kg: entry.kg,
    entry,
  })
}

export async function removeWeightEntry(
  pk: string,
  version: string,
  date: string
): Promise<void> {
  await invokeLambda('weight_log_remove', { pk, version, date })
}
