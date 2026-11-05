import { callOperation } from '../utils/operations'
import type { AthleteGoal } from '@powerlifting/types'

export async function getGoals(pk: string): Promise<AthleteGoal[]> {
  const result = await callOperation('goals_list', { pk })
  return Array.isArray(result) ? (result as AthleteGoal[]) : []
}

export async function updateGoals(pk: string, goals: unknown[]): Promise<void> {
  await callOperation('goals_replace', { pk, goals })
}
