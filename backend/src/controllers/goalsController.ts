import { invokeLambda } from '../utils/lambda'
import type { AthleteGoal } from '@powerlifting/types'

// Goals are stored in a dedicated per-user table (if-powerlifting-goals). All
// dynamo access + the goal normalization + the full-replace reconciliation
// (query existing -> upsert incoming by id -> delete missing) live in the
// `goals_list` / `goals_replace` Fission functions (layer pl_goals). The
// backend is now a pure auth/pk router.

export async function getGoals(pk: string): Promise<AthleteGoal[]> {
  const result = await invokeLambda('pod_goals', { function: 'goals_list',  pk })
  return Array.isArray(result) ? (result as AthleteGoal[]) : []
}

export async function updateGoals(pk: string, goals: unknown[]): Promise<void> {
  await invokeLambda('pod_goals', { function: 'goals_replace',  pk, goals })
}

