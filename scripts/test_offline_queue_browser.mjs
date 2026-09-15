import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium } from '@playwright/test'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)), 'frontend')
const server = await createServer({ root, configFile: false, logLevel: 'error', server: { host: '127.0.0.1', port: 0 }, resolve: { alias: { '@': resolve(root, 'src') } }, optimizeDeps: { entries: ['src/api/drafts.ts', 'src/api/cache.ts', 'src/api/http.ts'] } })
let browser
try {
  await server.listen()
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()
  await page.route('**/offline-check', route => route.fulfill({ contentType: 'text/html', body: '<title>Offline queue checks</title>' }))
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/offline-check`)
  const results = await page.evaluate(async () => {
    const drafts = await import('/src/api/drafts.ts')
    const context = await import('/src/api/context.ts')
    const cache = await import('/src/api/cache.ts')
    const api = (await import('/src/api/http.ts')).default
    const passed = []
    const check = (condition, name) => { if (!condition) throw new Error(name); passed.push(name) }
    const actor = (person, athlete) => { context.setRequestPerson(person); context.setRequestAthlete(athlete) }
    const input = (key, text = 'local') => ({ method: 'PUT', url: '/authored-notes/private', data: { note_id: 'note', text, expected_revision: 2, idempotency_key: key }, expected_revision: 2, idempotency_key: key })
    actor('author', 'athlete')
    const partition = context.requestPartition()
    await drafts.saveDraft('authored-note:note', { note_id: 'note', text: 'local' })
    const original = await drafts.prepareMutation(input('lost-response'))
    let attempts = 0
    const applied = new Set()
    const sender = async record => {
      attempts += 1
      applied.add(record.idempotency_key)
      if (attempts === 1) throw new Error('Connection lost after server commit')
      return { status: 200, data: { revision: 3 } }
    }
    await drafts.synchronizePendingMutations(sender)
    check((await drafts.listMutations())[0].status === 'failed', 'lost response preserves queued edit')
    const retry = await drafts.prepareMutation(input('new-browser-key'))
    check(retry.idempotency_key === original.idempotency_key, 'retry preserves original idempotency key')
    await drafts.synchronizePendingMutations(sender)
    check(applied.size === 1 && !(await drafts.listMutations()).length, 'lost response replay applies exactly once')
    check(!(await drafts.readDraft('authored-note:note')), 'successful replay clears original draft')
    const conflict = await drafts.prepareMutation(input('conflict'))
    await drafts.synchronizePendingMutations(async () => { throw { response: { status: 409, data: { code: 'revision_conflict', current_revision: 4, current_record: { text: 'server' } } } } })
    const savedConflict = (await drafts.listMutations())[0]
    check(savedConflict.status === 'conflict' && savedConflict.conflict.current_record.text === 'server' && savedConflict.data.text === 'local', 'conflict preserves server and local versions')
    let sent = 0
    await drafts.synchronizePendingMutations(async () => { sent++; return { status: 200 } })
    check(sent === 0, 'conflict never silently replays')
    await drafts.resolveMutation(savedConflict, { note_id: 'note', text: 'reviewed' })
    const reviewed = (await drafts.listMutations())[0]
    check(reviewed.expected_revision === 4 && reviewed.idempotency_key !== conflict.idempotency_key, 'explicit resolution uses reviewed revision and a new key')
    await drafts.synchronizePendingMutations(async () => ({ status: 200 }))
    actor('other-author', 'athlete')
    await drafts.prepareMutation(input('other-person'))
    actor('author', 'athlete')
    const own = await drafts.prepareMutation(input('own-person'))
    check(own.person_pk === 'author' && own.idempotency_key === 'own-person', 'another Person cannot shadow own retry')
    const captured = drafts.prepareMutation(input('during-switch', 'new change'))
    actor('new-person', 'new-athlete')
    const oldRecord = await captured
    check(oldRecord.person_pk === 'author' && oldRecord.athlete_pk === 'athlete' && oldRecord.partition === partition, 'IndexedDB wait keeps original context')
    await drafts.synchronizePendingMutations(async () => { throw new Error('must not send another context') }, partition)
    check((await drafts.listMutations(partition)).length === 2, 'context switch cannot replay former Athlete edits')
    actor('author', 'athlete')
    for (const record of await drafts.listMutations()) await drafts.removeMutation(record.id)
    await drafts.saveDraft('session:current:session-b', { id: 'session-b', session_notes: 'new' })
    const sessionInput = (key, text) => ({ method: 'PUT', url: '/sessions/current/2026-09-14/0', data: { id: 'session-b', session_notes: text, expected_revision: 7, idempotency_key: key }, expected_revision: 7, idempotency_key: key })
    await drafts.prepareMutation(sessionInput('a-old', 'old'))
    await drafts.prepareMutation(sessionInput('b-new', 'new'))
    const sessionReplay = []
    await drafts.synchronizePendingMutations(async record => { sessionReplay.push(record.data.session_notes); return { status: 200 } })
    check(sessionReplay.join(',') === 'old,new' && !(await drafts.readDraft('session:current:session-b')), 'newer typed Session text survives an older in-flight replay')
    await drafts.saveDraft('session:current:deleted', { id: 'deleted', session_notes: 'preserve' })
    const deleted = await drafts.prepareMutation({ method: 'PUT', url: '/sessions/current/2026-09-14/0', data: { id: 'deleted', session_notes: 'preserve', expected_revision: 7, idempotency_key: 'deleted-session' }, expected_revision: 7, idempotency_key: 'deleted-session' })
    await drafts.synchronizePendingMutations(async () => { throw { response: { status: 409, data: { code: 'session_identity_conflict', current_revision: 8, current_record: null } } } })
    const deletedConflict = (await drafts.listMutations()).find(record => record.id === deleted.id)
    check(deletedConflict.status === 'conflict' && (await drafts.readDraft('session:current:deleted')).value.session_notes === 'preserve', 'deleted Session preserves a structured conflict and the editable draft')
    await drafts.prepareMutation(input('blocked'))
    await cache.setCached('/private', { private: 'cached' }, ['program:current'])
    await drafts.saveDraft('unsent', { text: 'preserved' })
    await drafts.synchronizePendingMutations(async () => { throw { response: { status: 403 } } })
    await cache.clearDelegatedCachedRecords(partition)
    check((await drafts.listMutations()).some(record => record.status === 'blocked') && (await drafts.readDraft('unsent')).value.text === 'preserved' && await cache.getCached('/private') === undefined, 'revocation clears cache and preserves unsent edits')
    let complete
    let started
    const inFlight = new Promise(resolve => { started = resolve })
    api.defaults.adapter = config => new Promise(resolve => { complete = () => resolve({ status: 200, data: {}, headers: {}, config }); started() })
    const request = api.get('/read')
    await inFlight
    actor('new-person', 'new-athlete')
    complete()
    let cancelled = false
    try { await request } catch (error) { cancelled = error.code === 'ERR_CANCELED' }
    check(cancelled, 'late response cannot populate switched context')
    return passed
  })
  assert.equal(results.length, 14)
  console.log(JSON.stringify({ verification: 'local browser with simulated server responses', passed: results }, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
