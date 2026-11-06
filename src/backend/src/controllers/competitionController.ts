import { callOperation } from '../utils/operations'
import type { LiftResults, PostMeetReport, UserCompetition, UserCompetitionUpdate } from '@powerlifting/types'

export async function getUserCompetitions(
  pk: string,
  filters: { country?: string; state?: string } = {},
): Promise<UserCompetition[]> {
  const result = await callOperation('health_list_competitions', {
    op: 'list',
    pk,
    country: filters.country,
    state: filters.state,
  })
  const competitions = Array.isArray(result?.competitions) ? result.competitions : []
  return competitions as UserCompetition[]
}

export async function patchUserCompetition(
  pk: string,
  masterId: string,
  updates: UserCompetitionUpdate
): Promise<UserCompetition> {
  return (await callOperation('health_update_user_competition', {
    pk,
    master_id: masterId,
    patch: updates
  })) as UserCompetition
}

export async function completeUserCompetition(
  pk: string,
  masterId: string,
  results: LiftResults,
  bodyWeightKg: number,
  postMeetReport?: PostMeetReport,
): Promise<UserCompetition> {
  return (await callOperation('health_complete_user_competition', {
    pk,
    master_id: masterId,
    results,
    body_weight_kg: bodyWeightKg,
    post_meet_report: postMeetReport
  })) as UserCompetition
}
