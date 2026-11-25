import { callOperation } from '../utils/operations'
import type { MaxEntry, MaxHistoryStore } from '@powerlifting/types'


export async function getMaxHistory(pk: string): Promise<MaxHistoryStore> {
  const result = await callOperation('max_history_get', { pk })
  return {
    pk,
    sk: `max_history#current`,
    entries: Array.isArray(result?.entries) ? result.entries : [],
    updated_at: result?.updated_at || new Date().toISOString(),
  }
}

export async function addMaxEntry(pk: string, entry: MaxEntry): Promise<MaxHistoryStore> {
  return await callOperation('max_history_add', { pk,
    entry
  }) as MaxHistoryStore
}

export async function updateTargetMaxes(
  pk: string,
  maxes: { squat_kg: number; bench_kg: number; deadlift_kg: number }
): Promise<Record<string, unknown>> {
  return await callOperation('max_target_update', { pk,
    squat_kg: maxes.squat_kg,
    bench_kg: maxes.bench_kg,
    deadlift_kg: maxes.deadlift_kg
  }) as Record<string, unknown>
}

export async function getTargetMaxes(pk: string): Promise<{
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
  total_kg: number
}> {
  const maxes = await callOperation('max_target_get', { pk })
  const squat_kg = typeof maxes?.squat_kg === 'number' ? maxes.squat_kg : 0
  const bench_kg = typeof maxes?.bench_kg === 'number' ? maxes.bench_kg : 0
  const deadlift_kg = typeof maxes?.deadlift_kg === 'number' ? maxes.deadlift_kg : 0
  return {
    squat_kg,
    bench_kg,
    deadlift_kg,
    total_kg: squat_kg + bench_kg + deadlift_kg,
  }
}
