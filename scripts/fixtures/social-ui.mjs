import { me, ownAthlete, program } from './backlog-ui.mjs'

export const coachPerson = 'person-coach'
export const handlerPerson = 'person-handler'
export const operatorPerson = 'person-operator'
export const coachAthlete = 'athlete-coach'
export const handlerAthlete = 'athlete-handler'

export const competition = { master_id: 'meet-1', name: 'Toronto Open', start_date: '2026-12-01', end_date: '2026-12-01', user_status: 'upcoming' }

export function dashboardProgram(selected = ownAthlete) {
  const value = program({ revision: 1 })
  return { ...value, pk: selected, meta: { ...value.meta, revision: 1 } }
}

const analysisWindows = {
  current: { key: 'current', label: 'Current Week', start: '2026-09-08', end: '2026-09-14', weekStart: 2, weekEnd: 2, weeks: 1, currentWeek: 2 },
  previous_1: { key: 'previous_1', label: 'Previous Week', start: '2026-09-01', end: '2026-09-14', weekStart: 1, weekEnd: 2, weeks: 2, currentWeek: 2 },
  previous_2: { key: 'previous_2', label: 'Previous 2 Weeks', start: '2026-09-01', end: '2026-09-14', weekStart: 1, weekEnd: 2, weeks: 2, currentWeek: 2 },
  previous_4: { key: 'previous_4', label: 'Previous 4 Weeks', start: '2026-09-01', end: '2026-09-14', weekStart: 1, weekEnd: 2, weeks: 2, currentWeek: 2 },
  previous_8: { key: 'previous_8', label: 'Previous 8 Weeks', start: '2026-09-01', end: '2026-09-14', weekStart: 1, weekEnd: 2, weeks: 2, currentWeek: 2 },
  block: { key: 'block', label: 'Full Block', start: '2026-09-01', end: '2026-09-14', weekStart: 1, weekEnd: 2, weeks: 2, currentWeek: 2 },
}

const analysisSections = ['overview', 'fatigue_readiness', 'peaking', 'workload', 'alerts', 'ai_correlation', 'program_evaluation']

function analysisStatus(sectionKey, asOfDate) {
  const payload = sectionKey === 'fatigue_readiness' ? { fatigue_index: null, fatigue_components: null } : sectionKey === 'workload' ? { lifts: {}, current_maxes: {} } : { sessions_analyzed: 0 }
  return { sectionKey, status: 'complete', cached: false, sourceFingerprint: 'social-ui', generatedAt: `${asOfDate}T00:00:00Z`, updatedAt: `${asOfDate}T00:00:00Z`, asOfDate, windowKey: 'block', payload }
}

export function analysisManifest(asOfDate) {
  return { schemaVersion: 6, asOfDate, windowKey: 'block', windows: analysisWindows, sourceFingerprint: 'social-ui', sections: Object.fromEntries(analysisSections.map(sectionKey => [sectionKey, analysisStatus(sectionKey, asOfDate)])) }
}

export function analysisSection(sectionKey, asOfDate) {
  return analysisStatus(sectionKey, asOfDate)
}

const emptyRankingCard = { squat: null, bench: null, deadlift: null, total: null, top10_mean_squat: null, top10_mean_bench: null, top10_mean_deadlift: null, top10_mean_total: null }
export const rankingPercentile = { global: emptyRankingCard, national: null, regional: null, weight_class_label: null, meta: { global_n: 0, national_n: null, regional_n: null } }

export const privateNote = { note_id: 'note-own', author_person_pk: 'person-luna', text: 'Private original', revision: 2, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
export const sharedNote = { attachment_id: 'attachment-own', note_id: 'note-own', text: 'Shared revision', author_person_pk: 'person-luna', source_revision: 2, revision: 1, context_domain: 'program' }

export const profiles = [
  { person_pk: coachPerson, athlete_pk: coachAthlete, nickname: 'coach', display_name: 'Coach Casey', profile_visibility: 'public', public_training_summary_enabled: false, is_self: false, tags: [], bio: '', roles: ['coach'] },
  { person_pk: handlerPerson, athlete_pk: handlerAthlete, nickname: 'handler', display_name: 'Handler Harper', profile_visibility: 'public', public_training_summary_enabled: false, is_self: false, tags: [], bio: '', roles: ['handler'] },
]

export function authData(actor = 'owner', selected = ownAthlete) {
  if (actor === 'coach') return me({ person: coachPerson, mapped: selected, own: ownAthlete, roles: ['coach'], activeRole: 'coach', access: ['settings:read', 'settings:write', 'profile:read', 'profile:write'] })
  if (actor === 'handler') return me({ person: handlerPerson, mapped: selected, own: ownAthlete, roles: ['handler'], activeRole: 'handler', access: ['settings:read', 'settings:write', 'profile:read', 'profile:write'] })
  if (actor === 'operator') return me({ person: operatorPerson, mapped: ownAthlete, own: ownAthlete, roles: ['athlete'], activeRole: 'athlete', access: ['settings:read', 'settings:write', 'profile:read', 'profile:write', 'operator:write'] })
  return me({ mapped: selected, own: ownAthlete, roles: ['athlete'], activeRole: 'athlete', access: ['settings:read', 'settings:write', 'profile:read', 'profile:write', 'program:read', 'program:write', 'sessions:read', 'sessions:write', 'competition:read', 'competition:write'] })
}

export function relationship({ id, direction = 'athlete_to_delegate', type = 'coach', state = 'pending', active = false, athlete = ownAthlete, recipient = coachPerson, requester = 'person-luna', permissions = [], tied = [], replacement = undefined } = {}) {
  return { relationship_id: id, state, active, request_direction: direction, athlete_display_name: 'Luna', athlete_mapped_pk: athlete, athlete_person_pk: 'person-luna', requester_person_pk: requester, recipient_person_pk: recipient, relationship_type: type, permissions, tied_competition_ids: tied, expires_at: '2027-01-01T00:00:00Z', created_at: '2026-09-01T00:00:00Z', ...(replacement ? { replaced_by_relationship_id: replacement } : {}) }
}

export function settings(tags = []) {
  return { pk: 'person-luna', mapped_pk: ownAthlete, discord_id: 'discord-person-luna', discord_username: 'Luna', avatar_url: null, nickname: 'luna', profile_visibility: 'private', display_name: 'Luna', bio: '', public_training_summary_enabled: false, ranking_country: 'CA', ranking_region: 'ON', age_class: 'open', tags, sex: 'female', bodyweight_kg: 75, maxes_date: '2026-09-01', training_maxes_estimated: { squat: false, bench: true, deadlift: false }, training_maxes: { squat_kg: 140, bench_kg: 85, deadlift_kg: 180 }, federations: [], roles: ['athlete'], active_role: 'athlete', athlete_basics_complete: true, profile_complete: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
}
