import { QueryCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, POWERLIFTING_USER_COMPETITIONS_TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import { resolveCountryIso2 } from '../utils/countries'
import type { UserCompetition, UserCompetitionUpdate, Competition, LiftResults, PostMeetReport } from '@powerlifting/types'

// ─── User-owned fields (only these can be written by the user) ──────────────
const USER_OWNED_FIELDS: (keyof UserCompetitionUpdate)[] = [
  'user_status', 'weight_class_kg', 'body_weight_kg', 'targets', 'results',
  'post_meet_report', 'hotel_required', 'counts_toward_federation_ids',
  'between_comp_plan', 'comp_day_protocol', 'decision_date',
  'attempt_selection', 'attempt_strategy_mode', 'qualifying_standard_id',
  'qualifying_total_kg', 'projected_at_t_minus_1w', 'projection_snapshot_date',
  'notes',
]

// ─── Legacy compatibility: convert UserCompetition → old Competition shape ──
function userCompToLegacy(uc: UserCompetition): Competition {
  const locParts = [uc.venue_name, uc.venue_address, uc.venue_city, uc.venue_state, uc.venue_postal_code, uc.venue_country].filter(Boolean)
  const location = locParts.length > 0 ? locParts.join(', ') : undefined
  return {
    name: uc.name,
    date: uc.start_date,
    federation: uc.federation_label || '',
    federation_id: uc.federation_id || undefined,
    counts_toward_federation_ids: uc.counts_toward_federation_ids?.length ? uc.counts_toward_federation_ids : undefined,
    location,
    hotel_required: uc.hotel_required,
    status: (uc.user_status === 'available' ? 'optional' : uc.user_status) as Competition['status'],
    weight_class_kg: uc.weight_class_kg ?? 0,
    body_weight_kg: uc.body_weight_kg ?? undefined,
    qualifying_standard_id: uc.qualifying_standard_id ?? undefined,
    qualifying_total_kg: uc.qualifying_total_kg ?? undefined,
    attempt_strategy_mode: uc.attempt_strategy_mode ?? undefined,
    targets: uc.targets ?? undefined,
    projected_at_t_minus_1w: uc.projected_at_t_minus_1w ?? undefined,
    projection_snapshot_date: uc.projection_snapshot_date ?? undefined,
    results: uc.results ?? undefined,
    post_meet_report: uc.post_meet_report ?? undefined,
    notes: uc.notes || undefined,
    decision_date: uc.decision_date ?? null,
    between_comp_plan: uc.between_comp_plan ?? undefined,
    comp_day_protocol: uc.comp_day_protocol ?? undefined,
  }
}

// ─── Query user competitions from new table ────────────────────────────────
async function queryUserComps(pk: string): Promise<UserCompetition[]> {
  const items: UserCompetition[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new QueryCommand({
      TableName: POWERLIFTING_USER_COMPETITIONS_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: { ':pk': pk, ':prefix': 'COMP#' },
      ExclusiveStartKey: lastKey,
    }))
    for (const it of resp.Items ?? []) items.push(it as UserCompetition)
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)
  return items
}

// ─── New: list with country/state filter, returns UserCompetition[] ────────
export interface CompetitionFilters {
  country?: string
  state?: string
}

export async function listUserCompetitions(
  pk: string,
  filters?: CompetitionFilters,
): Promise<UserCompetition[]> {
  let items = await queryUserComps(pk)
  if (filters?.country) {
    const filterCode = resolveCountryIso2(filters.country)
    if (filterCode) {
      items = items.filter((uc) => (uc.venue_country ?? '').toUpperCase() === filterCode)
    } else {
      const needle = filters.country.trim().toLowerCase()
      items = items.filter((uc) => (uc.venue_country ?? '').toLowerCase() === needle)
    }
  }
  if (filters?.state) {
    if (filters.state !== '__all__') {
      items = items.filter((uc) => uc.venue_state === filters.state)
    }
  }

  return items
}

// ─── New: patch a single user competition (user-owned fields only) ─────────
export async function patchUserCompetition(
  pk: string,
  masterId: string,
  updates: UserCompetitionUpdate,
): Promise<void> {
  const sets: string[] = []
  const names: Record<string, string> = {}
  const values: Record<string, unknown> = {}
  let i = 0

  for (const [k, v] of Object.entries(updates)) {
    if (!USER_OWNED_FIELDS.includes(k as keyof UserCompetitionUpdate)) continue
    const n = `#f${i}`
    const ph = `:v${i}`
    names[n] = k
    values[ph] = v ?? null
    sets.push(`${n} = ${ph}`)
    i += 1
  }

  if (sets.length === 0) return

  names['#u'] = 'updated_at'
  values[':u'] = new Date().toISOString()
  sets.push('#u = :u')

  await docClient.send(new UpdateCommand({
    TableName: POWERLIFTING_USER_COMPETITIONS_TABLE,
    Key: { pk, sk: `COMP#${masterId}` },
    UpdateExpression: 'SET ' + sets.join(', '),
    ExpressionAttributeNames: names,
    ExpressionAttributeValues: values,
  }))
}

// ─── New: complete a competition ────────────────────────────────────────────
export async function completeUserCompetition(
  pk: string,
  masterId: string,
  results: LiftResults,
  bodyWeightKg: number,
  postMeetReport?: PostMeetReport,
): Promise<void> {
  await docClient.send(new UpdateCommand({
    TableName: POWERLIFTING_USER_COMPETITIONS_TABLE,
    Key: { pk, sk: `COMP#${masterId}` },
    UpdateExpression: 'SET #st = :st, results = :r, body_weight_kg = :bw, updated_at = :u' + (postMeetReport ? ', post_meet_report = :pmr' : ''),
    ExpressionAttributeNames: { '#st': 'user_status' },
    ExpressionAttributeValues: {
      ':st': 'completed',
      ':r': results,
      ':bw': bodyWeightKg,
      ':u': new Date().toISOString(),
      ...(postMeetReport ? { ':pmr': postMeetReport } : {}),
    },
  }))
}



// ─── Legacy: get competitions as old Competition[] shape ────────────────────
export async function getCompetitions(pk: string, version: string): Promise<Competition[]> {
  const items = await queryUserComps(pk)
  return items.map(userCompToLegacy)
}

// ─── Legacy: bulk update competitions ───────────────────────────────────────
function legacyToUserFields(legacy: Competition): Partial<UserCompetition> {
  const out: Partial<UserCompetition> = {}
  if (legacy.status !== undefined) out.user_status = legacy.status === 'completed' ? 'completed' : legacy.status === 'confirmed' ? 'confirmed' : legacy.status === 'skipped' ? 'skipped' : 'optional'
  if (legacy.weight_class_kg !== undefined) out.weight_class_kg = legacy.weight_class_kg
  if (legacy.body_weight_kg !== undefined) out.body_weight_kg = legacy.body_weight_kg
  if (legacy.counts_toward_federation_ids !== undefined) out.counts_toward_federation_ids = legacy.counts_toward_federation_ids
  if (legacy.hotel_required !== undefined) out.hotel_required = legacy.hotel_required
  if (legacy.targets !== undefined) out.targets = legacy.targets
  if (legacy.results !== undefined) out.results = legacy.results
  if (legacy.post_meet_report !== undefined) out.post_meet_report = legacy.post_meet_report
  if (legacy.notes !== undefined) out.notes = legacy.notes || ''
  if (legacy.decision_date !== undefined) out.decision_date = legacy.decision_date
  if (legacy.between_comp_plan !== undefined) out.between_comp_plan = legacy.between_comp_plan
  if (legacy.comp_day_protocol !== undefined) out.comp_day_protocol = legacy.comp_day_protocol
  if (legacy.qualifying_standard_id !== undefined) out.qualifying_standard_id = legacy.qualifying_standard_id
  if (legacy.qualifying_total_kg !== undefined) out.qualifying_total_kg = legacy.qualifying_total_kg
  if (legacy.attempt_strategy_mode !== undefined) out.attempt_strategy_mode = legacy.attempt_strategy_mode
  if (legacy.projected_at_t_minus_1w !== undefined) out.projected_at_t_minus_1w = legacy.projected_at_t_minus_1w
  if (legacy.projection_snapshot_date !== undefined) out.projection_snapshot_date = legacy.projection_snapshot_date
  return out
}

export async function updateCompetitions(
  pk: string,
  version: string,
  competitions: Competition[],
): Promise<void> {
  const existing = await queryUserComps(pk)
  const byKey = new Map<string, UserCompetition>()
  for (const uc of existing) byKey.set(`${uc.name}|${uc.start_date}`, uc)
  for (const legacy of competitions) {
    const uc = byKey.get(`${legacy.name}|${legacy.date}`)
    if (!uc) continue
    const fields = legacyToUserFields(legacy)
    const sets: string[] = []
    const names: Record<string, string> = {}
    const values: Record<string, unknown> = {}
    let i = 0
    for (const [k, v] of Object.entries(fields)) {
      const n = `#f${i}`
      const ph = `:v${i}`
      names[n] = k
      values[ph] = v ?? null
      sets.push(`${n} = ${ph}`)
      i += 1
    }
    if (sets.length === 0) continue
    names['#u'] = 'updated_at'
    values[':u'] = new Date().toISOString()
    sets.push('#u = :u')
    await docClient.send(new UpdateCommand({
      TableName: POWERLIFTING_USER_COMPETITIONS_TABLE,
      Key: { pk, sk: `COMP#${uc.master_id}` },
      UpdateExpression: 'SET ' + sets.join(', '),
      ExpressionAttributeNames: names,
      ExpressionAttributeValues: values,
    }))
  }
}

export async function migrateLastComp(pk: string, version: string): Promise<Competition[]> {
  return getCompetitions(pk, version)
}

export async function completeCompetition(
  pk: string,
  version: string,
  compDate: string,
  results: LiftResults,
  bodyWeightKg: number,
  postMeetReport?: PostMeetReport,
): Promise<void> {
  const existing = await queryUserComps(pk)
  const target = existing.find((uc) => uc.start_date === compDate)
  if (!target) throw new AppError(`Competition with date ${compDate} not found`, 404)
  await completeUserCompetition(pk, target.master_id, results, bodyWeightKg, postMeetReport)
}
