export const ownAthlete = 'athlete-own'
export const otherAthlete = 'athlete-coached'

const permissions = [
  'program:read', 'program:write', 'sessions:read', 'sessions:write',
  'settings:read', 'settings:write', 'profile:read', 'analytics:read',
  'competition:read', 'competition:write', 'templates:read', 'templates:write',
]

export function user({ roles = ['athlete'], activeRole = roles[0] ?? 'athlete', username = 'Luna', displayName = 'Luna', person = 'person-luna' } = {}) {
  return {
    provider: 'authentik',
    sub: `sub-${person}`,
    username,
    display_name: displayName,
    avatar: null,
    groups: [],
    roles,
    active_role: activeRole,
    email: `${person}@example.test`,
    discord_id: `discord-${person}`,
  }
}

export function me({ mapped = ownAthlete, own = ownAthlete, roles = ['athlete'], activeRole = roles[0] ?? 'athlete', onboarded = true, person = 'person-luna', displayName = 'Luna', access = permissions } = {}) {
  return {
    person_pk: person,
    mapped_pk: mapped,
    own_athlete_pk: own,
    user: user({ roles, activeRole, person, displayName }),
    access: { permissions: access, athlete_display_name: mapped === own ? displayName : mapped === otherAthlete ? 'Coach Client' : mapped },
    onboarding: { is_onboarded: onboarded },
    ranking_country: 'CA',
    ranking_region: 'ON',
    age_class: 'open',
  }
}

export function settings({ roles = ['athlete'], displayName = 'Luna', basics = true } = {}) {
  return {
    pk: 'person-luna', mapped_pk: ownAthlete, discord_id: 'discord-person-luna', discord_username: 'Luna', avatar_url: null,
    nickname: 'luna', profile_visibility: 'private', display_name: displayName, bio: '', public_training_summary_enabled: false,
    ranking_country: 'CA', ranking_region: 'ON', age_class: 'open', tags: [], sex: basics ? 'female' : null, bodyweight_kg: basics ? 75 : null,
    maxes_date: basics ? '2026-09-01' : undefined, training_maxes_estimated: basics ? { squat: false, bench: true, deadlift: false } : undefined,
    training_maxes: basics ? { squat_kg: 140, bench_kg: 85, deadlift_kg: 180 } : null, federations: [], roles, active_role: roles[0] ?? 'coach',
    athlete_basics_complete: basics, profile_complete: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  }
}

export const onboardingRole = {
  is_onboarded: false,
  next_step: 'role',
  state: { roles: [], active_role: null, athlete_basics_complete: false, profile_complete: false },
  has_athlete_basics: false,
}

export const onboardingAthleteBasics = {
  is_onboarded: false,
  next_step: 'athlete_basics',
  state: { roles: ['athlete'], active_role: 'athlete', athlete_basics_complete: false, profile_complete: true },
  has_athlete_basics: false,
  prefill: { bodyweight_kg: 75, training_maxes: { squat_kg: 140, bench_kg: 85, deadlift_kg: 180 } },
}

const phase = { name: 'Strength', intent: 'Build strength', start_week: 1, end_week: 4, block: 'current' }

function session({ id, date, day, name, completed = false, block = 'current' }) {
  const exercise = { id: `${id}-exercise`, name, sets: 3, reps: 3, kg: 100, notes: '', set_statuses: completed ? ['completed', 'completed', 'completed'] : ['pending', 'pending', 'pending'] }
  return { id, date, day, week: 'W1', week_number: 1, phase, block, status: completed ? 'completed' : 'planned', completed, planned_exercises: [exercise], exercises: [exercise], session_notes: '', session_rpe: null, body_weight_kg: null }
}

export const sessions = [
  session({ id: 'session-squat', date: '2026-09-14', day: 'Monday', name: 'Squat' }),
  session({ id: 'session-bench', date: '2026-09-14', day: 'Monday', name: 'Bench Press' }),
]

export function program({ revision = 7, unfinished = true } = {}) {
  const block = { id: 'block-current', name: 'Accumulation', status: 'active', start_date: '2026-09-01', start_week: 1, end_week: 4, week_start_day: 'Monday' }
  return {
    revision,
    pk: ownAthlete,
    sk: 'program#current',
    meta: {
      revision, current_block_id: block.id, blocks: [block], program_name: 'Accumulation', program_start: '2026-09-01', comp_date: '2026-12-01', federation: 'CPU', practicing_for: 'Meet', version_label: 'Current', sex: 'female', weight_class_kg: 76, weight_class_confirm_by: '2026-11-01', current_body_weight_kg: 75, current_body_weight_lb: 165.3, target_squat_kg: 150, target_bench_kg: 90, target_dl_kg: 190, training_notes: [], change_log: [], block_notes: [], updated_at: '2026-09-01T00:00:00Z', last_comp: {}, program_week_start_day: 'Monday',
    },
    phases: [phase],
    sessions: unfinished ? sessions : sessions.map(item => ({ ...item, completed: true, status: 'completed' })),
    competitions: [], diet_notes: [], supplements: [], supplement_phases: [],
    current_maxes: { squat: 140, bench: 85, deadlift: 180, method: 'manual' },
  }
}

export const relationships = {
  sent: [],
  received: [{ relationship_id: 'grant-1', state: 'approved', active: true, athlete_display_name: 'Coach Client', athlete_mapped_pk: otherAthlete, athlete_person_pk: 'person-client', recipient_person_pk: 'person-luna', relationship_type: 'coach', permissions: ['program:read', 'sessions:read'], tied_competition_ids: [], expires_at: '2027-01-01T00:00:00Z', created_at: '2026-09-01T00:00:00Z' }],
  history: [],
}

export const federation = [{ pk: 'fed-cpu', name: 'Canadian Powerlifting Union', abbreviation: 'CPU', status: 'active' }]

export const emptyProgramResponse = { data: program() }
