import { invokeLambda } from '../utils/lambda'
import type { AthleteGoal } from '@powerlifting/types'

export async function getGoals(pk: string): Promise<AthleteGoal[]> {
  const result = await invokeLambda('pod_goals', { function: 'goals_list',  pk })
  return Array.isArray(result) ? (result as AthleteGoal[]) : []
}

export async function updateGoals(pk: string, goals: unknown[]): Promise<void> {
  await invokeLambda('pod_goals', { function: 'goals_replace',  pk, goals })
}
