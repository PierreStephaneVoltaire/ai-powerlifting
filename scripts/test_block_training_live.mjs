import fs from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'

const require = createRequire('/home/sirsimpalot/Downloads/discord-ai-bot/utils/powerlifting-app/package.json')
const { request } = require('@playwright/test')

const base = process.env.PL_BASE_URL || 'https://dev.nolift.training'
const state = process.env.PL_STORAGE_STATE || '/tmp/live-acceptance-luna-storage-state.json'
const evidencePath = process.env.PL_BLOCK_EVIDENCE || '/tmp/block-training-live-acceptance.json'
const evidence = { base, state, started_at: new Date().toISOString(), checks: [], failures: [] }
const ctx = await request.newContext({ baseURL: base, storageState: state })
const run = String(Date.now())

async function call(method, path, body, headers = {}) {
  const response = await ctx.fetch(path, {
    method,
    headers: { ...(body ? { 'content-type': 'application/json' } : {}), ...headers },
    ...(body ? { data: body } : {}),
  })
  const text = await response.text()
  let parsed = null
  try { parsed = text ? JSON.parse(text) : null } catch { parsed = text.slice(0, 500) }
  return { status: response.status(), body: parsed }
}

function check(name, condition, detail) {
  const row = { name, passed: Boolean(condition), detail }
  evidence.checks.push(row)
  if (!row.passed) evidence.failures.push(row)
  if (!row.passed) throw new Error(`${name}: ${JSON.stringify(detail)}`)
}

async function expectConflict(name, path, body) {
  const result = await call('POST', path, body)
  check(name, result.status === 409, result)
  return result
}

const me = await call('GET', '/api/auth/me')
check('authenticated Luna session', me.status === 200 && me.body?.person_pk === 'live-acceptance-luna' && me.body?.readOnly === false, me)
const onboarding = await call('GET', '/api/onboarding/status')
check('onboarding complete', onboarding.status === 200 && onboarding.body?.data?.is_onboarded === true, onboarding)

const programResponse = await call('GET', '/api/programs/current')
check('current program readable', programResponse.status === 200 && programResponse.body?.data?.meta, programResponse)
let program = programResponse.body.data
let revision = Number(program.meta.revision || 0)
let blockId = String(program.meta.current_block_id || 'current')
const startMaxes = { squat: 130, bench: 80, deadlift: 160 }
const seedSessionId = `live-acceptance-unfinished-${run}`
const seeded = await call('POST', '/api/sessions/current', {
  id: seedSessionId, date: '2026-09-20', day: 'Sunday', week: 'W1', week_number: 1,
  status: 'planned', completed: false, planned_exercises: [], exercises: [], session_notes: 'preservation probe',
  expected_revision: revision, idempotency_key: `live-session-seed-${run}`,
})
check('unfinished session can be seeded in isolated partition', seeded.status === 200 && seeded.body?.data?.session?.id === seedSessionId, seeded)
program = (await call('GET', '/api/programs/current')).body.data
revision = Number(program.meta.revision || 0)
blockId = String(program.meta.current_block_id || 'current')
const plan = {
  phases: [{ id: 'live-acceptance-phase', name: 'Acceptance phase', intent: 'strength', start_week: 1, end_week: 2 }],
  sessions: [{ id: 'live-acceptance-session', session_id: 'live-acceptance-session', date: '2026-10-05', week_number: 1, status: 'planned', completed: false, exercises: [] }],
}

const combinedBody = {
  action: 'complete_and_start', block_id: blockId, expected_revision: revision,
  idempotency_key: `live-block-combined-${run}`, name: 'Live acceptance next',
  current_name: 'Live acceptance archived', start_date: '2026-10-01', week_start_day: 'Thursday',
  start_maxes_kg: startMaxes, next_program: plan,
}
const combined = await call('POST', '/api/programs/current/blocks/transition', combinedBody)
check('complete and start succeeds', combined.status === 200 && combined.body?.data?.next_block_id && Number(combined.body?.data?.revision) === revision + 1, combined)
const firstResult = combined.body.data
program = firstResult.program
const archivedId = String(firstResult.block_id === 'current' ? (program.meta.blocks || []).find((b) => b.status === 'completed')?.id : firstResult.block_id)
const nextId = String(firstResult.next_block_id)
check('archive and next have stable distinct ids', archivedId && nextId && archivedId !== nextId && program.meta.current_block_id === nextId, { archivedId, nextId, blocks: program.meta.blocks })
check('next block week numbering and settings reset', program.meta.blocks.some((b) => b.id === nextId && b.start_week === 1 && b.start_date === '2026-10-01' && b.week_start_day === 'Thursday'), program.meta.blocks)
check('confirmed start maxes captured', JSON.stringify(program.meta.block_start_maxes?.[nextId]) === JSON.stringify(startMaxes), program.meta.block_start_maxes)
check('unfinished session status preserved in archive', program.sessions?.some((s) => s.id === seedSessionId && s.status === 'planned' && s.completed === false && s.block_id === archivedId), program.sessions?.filter((s) => s.id === seedSessionId))
const replay = await call('POST', '/api/programs/current/blocks/transition', combinedBody)
check('combined retry is idempotent', replay.status === 200 && replay.body?.data?.next_block_id === nextId && Number(replay.body?.data?.revision) === Number(firstResult.revision), replay)
const changedReplay = { ...combinedBody, name: 'different payload' }
const changed = await call('POST', '/api/programs/current/blocks/transition', changedReplay)
check('idempotency payload mismatch rejected', changed.status === 422, changed)

const stale = { ...combinedBody, idempotency_key: 'live-block-stale-20260915', expected_revision: revision }
await expectConflict('stale expected revision rejected', '/api/programs/current/blocks/transition', stale)

const completion = await call('POST', '/api/programs/current/blocks/transition', {
  action: 'complete', block_id: nextId, expected_revision: Number(firstResult.revision),
  idempotency_key: `live-block-complete-${run}`, current_name: 'Second archived acceptance',
})
check('complete preserves the active block as an archive', completion.status === 200 && !completion.body?.data?.next_block_id && Number(completion.body?.data?.revision) === Number(firstResult.revision) + 1, completion)
const secondRevision = Number(completion.body.data.revision)
const second = await call('POST', '/api/programs/current/blocks/transition', {
  action: 'start_next', block_id: nextId, expected_revision: secondRevision,
  idempotency_key: `live-block-start-next-${run}`, name: 'Second acceptance next',
  start_date: '2026-11-01', week_start_day: 'Sunday', start_maxes_kg: { squat: 135, bench: 82.5, deadlift: 165 },
  next_program: { phases: [{ name: 'Second phase', start_week: 1, end_week: 1 }], sessions: [] },
})
check('start_next requires completed source and succeeds', second.status === 200 && second.body?.data?.next_block_id, second)

const mcpLines = [
  'import json,httpx,os',
  'from services.principal import principal_token',
  "person=athlete='live-acceptance-luna'",
  "headers=lambda op:{'X-Internal-Token':os.environ['INTERNAL_API_TOKEN'],'X-Person-Pk':person,'X-Athlete-Pk':athlete,'X-PL-Principal':principal_token(person,athlete,op)}",
  "program=httpx.post('http://127.0.0.1:8000/operations/program_get',headers=headers('program_get'),json={'pk':athlete}).json()",
  "meta=program.get('meta',{})",
  `args={'action':'rename','block_id':${JSON.stringify(String(second.body.data.next_block_id))},'expected_revision':int(meta.get('revision',0)),'idempotency_key':${JSON.stringify(`live-block-rename-${run}`)},'name':'Renamed acceptance block'}`,
  "r=httpx.post('http://127.0.0.1:8000/mcp',headers=headers('block_transition'),json={'jsonrpc':'2.0','id':'block-mcp-live','method':'tools/call','params':{'name':'block_transition','arguments':args}})",
  "after=httpx.post('http://127.0.0.1:8000/operations/program_get',headers=headers('program_get'),json={'pk':athlete}).json()",
  "print(json.dumps({'status':r.status_code,'body':r.json(),'after':after}))",
]
const mcpProcess = spawnSync('kubectl', ['-n', 'if-portals', 'exec', '-i', 'deploy/pl-program', '--', 'python', '-'], { input: mcpLines.join('\n'), encoding: 'utf8' })
let mcp = null
try { mcp = JSON.parse(mcpProcess.stdout.trim()) } catch { mcp = { status: 0, body: { exit: mcpProcess.status, error: mcpProcess.stderr.trim().slice(0, 500) } } }
check('MCP block transition route succeeds', mcp.status === 200 && mcp.body?.result?.isError === false, mcp)
check('MCP rename is visible after reread', mcp.after?.meta?.revision && mcp.after.meta.revision >= Number(second.body.data.revision) && mcp.after.meta.blocks?.some((block) => block.id === String(second.body.data.next_block_id) && block.name === 'Renamed acceptance block'), mcp.after)

evidence.finished_at = new Date().toISOString()
evidence.revision = { initial: revision, combined: firstResult.revision, start_next: second.body?.data?.revision }
fs.writeFileSync(evidencePath, JSON.stringify(evidence, null, 2), { mode: 0o600 })
await ctx.dispose()
console.log(JSON.stringify({ passed: evidence.checks.length, failed: evidence.failures.length, evidencePath }))
