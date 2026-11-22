import { createRequire } from 'node:module'

const { request } = createRequire(new URL('../src/package.json', import.meta.url))('@playwright/test')
const state = process.env.PL_STORAGE_STATE || '/tmp/nolift-test-session.json'
const baseURL = 'https://dev.nolift.training'
const context = await request.newContext({ baseURL, storageState: state, extraHTTPHeaders: { Origin: baseURL } })
async function call(method, path, data) {
  const response = await context.fetch(path, { method, ...(data ? { data } : {}) })
  const text = await response.text()
  if (!response.ok()) throw new Error(`${method} ${path}: ${response.status()} ${text.slice(0, 500)}`)
  try { return JSON.parse(text).data } catch { throw new Error(`${method} ${path} did not return JSON`) }
}
try {
  const response = await context.get('/api/auth/me')
  const me = await response.json()
  if (me.readOnly !== false || me.person_pk !== 'person_be8959131fea4ca395a38e8f' || me.mapped_pk !== me.person_pk) throw new Error('Refusing to seed an unexpected account')
  const status = await call('GET', '/api/onboarding/status')
  if (!status.is_onboarded) {
    await call('PUT', '/api/onboarding/role', { roles: ['athlete'], active_role: 'athlete' })
    await call('PUT', '/api/onboarding/profile', { display_name: 'NoLift Test Athlete', bio: 'Synthetic account for automated testing.', profile_visibility: 'private', federations: [] })
    await call('PUT', '/api/onboarding/athlete-basics', { sex: 'male', country: 'ca', region: 'on', bodyweight_kg: 82.5, training_maxes: { squat_kg: 180, bench_kg: 120, deadlift_kg: 220 } })
  }
  let setup = await call('GET', '/api/setup/status')
  if (!setup.hasCurrentProgram) {
    await call('POST', '/api/setup/initialize', { mode: 'manual_sessions', programName: 'Automated Test Program', startDate: '2026-11-02', weekStartDay: 'Monday', maxes: { squat: 180, bench: 120, deadlift: 220 } })
    setup = await call('GET', '/api/setup/status')
  }
  if (!setup.hasCurrentProgram) throw new Error('Program setup did not complete')
  let program = await call('GET', '/api/programs/current')
  for (const [week, date, weight] of [[1, '2026-11-02', 100], [2, '2026-11-09', 105], [3, '2026-11-16', 110]]) {
    const id = `automated-test-week-${week}`
    let existing = (program.sessions || []).find(session => session.id === id)
    if (existing?.completed) continue
    const exercise = { name: 'Squat', sets: 3, reps: 5, kg: weight, rpe: 8, notes: 'Synthetic test data', set_statuses: ['completed', 'completed', 'completed'], sets_data: [{ kg: weight, reps: 5, rpe: 8 }, { kg: weight + 2.5, reps: 5, rpe: 8.5 }, { kg: weight, reps: 5, rpe: 9 }] }
    if (!existing) {
      await call('POST', '/api/sessions/current', { id, date, day: 'Monday', week: `W${week}`, week_number: week, planned_exercises: [{ name: 'Squat', sets: 3, reps: 5, kg: weight - 5, rpe_target: 8 }], exercises: [exercise], session_notes: 'Synthetic test session', body_weight_kg: 82.5 })
      program = await call('GET', '/api/programs/current')
      existing = program.sessions.find(session => session.id === id)
    }
    const index = program.sessions.findIndex(session => session.id === id)
    if (index < 0) throw new Error(`Created session ${id} was not returned`)
    await call('PATCH', `/api/sessions/current/${date}/${index}/complete`, { session_id: id, rpe: 8, bodyWeightKg: 82.5 })
    program = await call('GET', '/api/programs/current')
  }
  console.log(`Test athlete ready: ${program.sessions.filter(session => String(session.id).startsWith('automated-test-week-')).length} synthetic sessions`)
} finally {
  await context.dispose()
}
