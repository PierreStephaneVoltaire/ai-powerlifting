import { invokeLambda } from '../utils/lambda'
import type { MaxEntry, MaxHistoryStore } from '@powerlifting/types'

export async function getMaxHistory(pk: string, version: string): Promise<MaxHistoryStore> {
  const result = await invokeLambda('max_history_get', { pk, version })
  return {
    pk,
    sk: `max_history#${version}`,
    entries: Array.isArray(result?.entries) ? result.entries : [],
    updated_at: result?.updated_at || new Date().toISOString(),
  }
}

export async function addMaxEntry(pk: string, version: string, entry: MaxEntry): Promise<void> {
  await invokeLambda('max_history_add', {
    pk,
    version,
    date: entry.date,
    squat_kg: entry.squat_kg,
    bench_kg: entry.bench_kg,
    deadlift_kg: entry.deadlift_kg,
    total_kg: entry.total_kg,
    bodyweight_kg: entry.bodyweight_kg,
    context: entry.context,
  })
}

export async function updateTargetMaxes(
  pk: string,
  version: string,
  maxes: { squat_kg: number; bench_kg: number; deadlift_kg: number }
): Promise<void> {
  await invokeLambda('max_target_update', {
    pk,
    version,
    squat_kg: maxes.squat_kg,
    bench_kg: maxes.bench_kg,
    deadlift_kg: maxes.deadlift_kg,
  })
}

export async function getTargetMaxes(pk: string, version: string): Promise<{
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
  total_kg: number
}> {
  const maxes = await invokeLambda('max_target_get', { pk, version })
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
