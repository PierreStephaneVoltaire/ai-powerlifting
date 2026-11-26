import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

const { request } = createRequire(new URL('../src/package.json', import.meta.url))('@playwright/test')
const context = await request.newContext({ baseURL: process.env.PL_APP_ORIGIN || 'https://dev.nolift.training', storageState: process.env.PL_STORAGE_STATE || '/tmp/nolift-test-session.json' })
try {
  async function get(path) {
    const response = await context.get(path)
    assert.equal(response.status(), 200, `${path}: HTTP ${response.status()}`)
    return response
  }
  const me = await (await get('/api/auth/me')).json()
  assert.equal(me.person_pk, 'person_be8959131fea4ca395a38e8f')
  assert.equal(me.readOnly, false)
  const program = (await (await get('/api/programs/current')).json()).data
  const sessions = program.sessions.filter(session => String(session.id).startsWith('automated-test-week-'))
  assert.equal(sessions.length, 3)
  assert.ok(sessions.every(session => session.completed && session.planned_exercises.length && session.exercises[0].sets_data.length === 3))
  const weekly = (await (await get('/api/analytics/analysis/weekly?weeks=3&block=current&weekStart=1&weekEnd=3&windowStart=2026-11-02&windowEnd=2026-11-22&refDate=2026-11-22')).json()).data
  assert.deepEqual([weekly.compliance.pct, weekly.compliance.set_pct, weekly.compliance.vol_pct], [100, 100, 105])
  const markdown = await (await get('/api/export/markdown?week_start=1&week_end=3&window_start=2026-11-02&window_end=2026-11-22')).text()
  const missing = []
  if (!/\| Squat \| 1 x 5 \| 102\.5 \| 8\.5 \|/.test(markdown)) missing.push('actual per-set load and RPE')
  if (!/\| Squat \| 3 x 5 \| 95 \| 8 \|/.test(markdown)) missing.push('planned prescription')
  if (!/Squat change \(kg\)/.test(markdown)) missing.push('weekly e1RM changes')
  assert.equal(missing.length, 0, `Export missing: ${missing.join(', ')}`)
  console.log('Live API checks passed')
} finally {
  await context.dispose()
}
