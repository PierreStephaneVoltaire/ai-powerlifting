import { otherAthlete, ownAthlete, me, program } from './backlog-ui.mjs'

export const offlinePerson = 'person-offline'

export function offlineMe({ mapped = ownAthlete, permissions } = {}) {
  return me({
    person: offlinePerson,
    mapped,
    own: ownAthlete,
    roles: ['athlete', 'coach'],
    activeRole: 'athlete',
    access: permissions ?? [
      'program:read', 'program:write', 'sessions:read', 'sessions:write',
      'competition:read', 'competition:write', 'settings:read', 'settings:write',
      'profile:read', 'profile:write', 'analytics:read',
    ],
  })
}

export function offlineProgram() {
  const value = program({ revision: 7, unfinished: true })
  return { ...value, sessions: value.sessions.map(session => structuredClone(session)) }
}

export const offlineNote = {
  note_id: 'offline-note',
  author_person_pk: offlinePerson,
  text: 'Original private note',
  revision: 2,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

export const offlineAttachment = {
  attachment_id: 'attachment-1',
  note_id: 'offline-note',
  text: 'Previously shared revision',
  author_person_pk: offlinePerson,
  source_revision: 2,
  revision: 1,
  context_domain: 'program',
}

export const offlineCompetition = {
  master_id: 'offline-meet',
  name: 'Offline Meet',
  start_date: '2026-09-01',
  end_date: '2026-09-01',
  federation_label: 'CPU',
  federation_slug: 'cpu',
  federation_website_url: null,
  venue_name: 'Test Hall',
  venue_address: null,
  venue_city: 'Toronto',
  venue_state: 'ON',
  venue_country: 'CA',
  venue_postal_code: null,
  website_url: null,
  testing_status: 'unknown',
  registration_status: 'closed',
  registration_url: null,
  registration_end_date: null,
  source_url: null,
  source_name: null,
  last_verified_at: null,
  event_type: 'powerlifting',
  cancelled: false,
  user_status: 'completed',
  weight_class_kg: 76,
  body_weight_kg: 74.5,
  targets: null,
  results: { squat_kg: 140, bench_kg: 85, deadlift_kg: 180, total_kg: 405 },
  post_meet_report: {
    attempts: [
      { attempt_id: 'attempt-squat-1', lift: 'squat', attempt_number: 1, kg: 130, result: 'made', miss_reasons: [], miss_category: null },
    ],
    sleep_hours: 7,
    travel_notes: '',
    warmup_timing: '',
    pre_meet_food: '',
    during_meet_food: '',
    caffeine_mg: null,
    caffeine_timing: '',
    equipment_issues: '',
    commands_missed: '',
    attempt_selection_grade: 4,
    notes: '',
  },
  hotel_required: false,
  counts_toward_federation_ids: [],
  between_comp_plan: null,
  comp_day_protocol: null,
  decision_date: null,
  attempt_selection: null,
  attempt_strategy_mode: null,
  qualifying_standard_id: null,
  qualifying_total_kg: null,
  projected_at_t_minus_1w: null,
  projection_snapshot_date: null,
  notes: '',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  units: 'kg',
  revision: 2,
}

export const offlineRelationships = {
  sent: [],
  received: [{
    relationship_id: 'offline-grant', state: 'approved', active: true,
    athlete_display_name: 'Coach Client', athlete_mapped_pk: otherAthlete,
    athlete_person_pk: 'person-client', recipient_person_pk: offlinePerson,
    relationship_type: 'coach', permissions: ['program:read', 'sessions:read'],
    tied_competition_ids: [], expires_at: '2027-01-01T00:00:00Z',
    created_at: '2026-09-01T00:00:00Z',
  }],
  history: [],
}
