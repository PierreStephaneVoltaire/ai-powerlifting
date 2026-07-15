import { invokeLambda } from '../utils/lambda'
import { logger } from '../utils/logger'
import type { Competition, LiftResults, PostMeetReport, UserCompetition, UserCompetitionUpdate } from '@powerlifting/types'

export async function getUserCompetitions(
  pk: string,
  filters: { country?: string; state?: string } = {},
): Promise<UserCompetition[]> {
  const result = await invokeLambda('pod_competition', {
    function: 'health_list_competitions',
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
  updates: UserCompetitionUpdate,
): Promise<UserCompetition> {
  return (await invokeLambda('pod_competition', {
    function: 'health_list_competitions',
    op: 'update',
    pk,
    master_id: masterId,
    patch: updates,
  })) as UserCompetition
}

export async function completeUserCompetition(
  pk: string,
  masterId: string,
  results: LiftResults,
  bodyWeightKg: number,
  postMeetReport?: PostMeetReport,
): Promise<UserCompetition> {
  return (await invokeLambda('pod_competition', {
    function: 'health_list_competitions',
    op: 'complete',
    pk,
    master_id: masterId,
    results,
    body_weight_kg: bodyWeightKg,
    post_meet_report: postMeetReport,
  })) as UserCompetition
}

export async function getCompetitions(pk: string, _version: string): Promise<Competition[]> {
  return getUserCompetitions(pk) as unknown as Competition[]
}

export async function updateCompetitions(
  pk: string,
  _version: string,
  competitions: Competition[],
): Promise<void> {
  const program = await invokeLambda('health_get_program', { pk })
  const existing = Array.isArray(program?.competitions) ? (program.competitions as Competition[]) : []

  for (const legacy of competitions) {
    const match = existing.find((c) => c.date === legacy.date)
    if (!match) continue
    const patch: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(legacy)) {
      if (value !== undefined && key !== 'date') {
        patch[key] = value
      }
    }
    if (Object.keys(patch).length === 0) continue
    await invokeLambda('pod_competition', { function: 'health_update_competition',  pk, date: legacy.date, patch })
  }
}

export async function completeCompetition(
  pk: string,
  version: string,
  compDate: string,
  results: LiftResults,
  bodyWeightKg: number,
  postMeetReport?: PostMeetReport,
): Promise<Competition> {
  const compDateObj = new Date(`${compDate}T00:00:00Z`)
  compDateObj.setUTCDate(compDateObj.getUTCDate() - 7)
  const snapshotDate = compDateObj.toISOString().slice(0, 10)

  try {
    await invokeLambda('pod_competition', { function: 'health_snapshot_competition_projection', 
      pk,
      date: snapshotDate,
      version,
      allow_retrospective: true,
    })
  } catch (snapshotErr) {
    logger.warn({ err: snapshotErr, pk, module: 'competition', fn: 'completeCompetition' }, 'failed to snapshot competition projection')
  }

  return invokeLambda('pod_competition', { function: 'health_complete_competition', 
    pk,
    date: compDate,
    results,
    body_weight_kg: bodyWeightKg,
    post_meet_report: postMeetReport,
    version,
    allow_retrospective: true,
  }) as Promise<Competition>
}
