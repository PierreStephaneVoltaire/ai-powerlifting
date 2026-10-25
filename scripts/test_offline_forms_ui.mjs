import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium } from '@playwright/test'
import react from '@vitejs/plugin-react'
import { otherAthlete, ownAthlete, program, me, relationships, settings } from './fixtures/backlog-ui.mjs'
import {
  offlineCompetition,
  offlineAttachment,
  offlineMe,
  offlineNote,
  offlinePerson,
  offlineProgram,
  offlineRelationships,
} from './fixtures/offline-ui.mjs'

const root = resolve(fileURLToPath(new URL('.', import.meta.url)), '..', 'frontend')
const server = await createServer({
  root,
  appType: 'spa',
  configFile: false,
  logLevel: 'error',
  server: { host: '127.0.0.1', port: 0 },
  plugins: [react()],
  resolve: { alias: { '@': resolve(root, 'src') } },
  css: { postcss: { plugins: [] } },
})

const passed = []
const check = (condition, name) => {
  assert.ok(condition, name)
  passed.push(name)
}

function response(data, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(data) }
}

function bodyOf(request) {
  try { return request.postDataJSON() } catch { return undefined }
}

function state(overrides = {}) {
  return {
    requests: [],
    phase: 'load',
    expectedFailures: [],
    expectedConsoleResponses: 0,
    mode: 'success',
    program: offlineProgram(),
    note: { ...offlineNote },
    attachments: [{ ...offlineAttachment }],
    competitions: [{ ...offlineCompetition, post_meet_report: { ...offlineCompetition.post_meet_report, attempts: [...offlineCompetition.post_meet_report.attempts] } }],
    publication: { domains: [], revision: 2 },
    unhandled: [],
    browserErrors: [],
    ...overrides,
  }
}

function setPhase(current, phase) {
  current.phase = phase
}

function expectFailure(current, failure) {
  current.expectedFailures.push({ ...failure, scenario: current.mode })
}

function consumeExpectedFailure(current, kind, details) {
  const index = current.expectedFailures.findIndex(failure => failure.scenario === current.mode && failure.kind === kind && failure.phase === details.phase && (kind === 'console' || (!failure.method || failure.method === details.method) && (!failure.path || failure.path === details.path) && (!failure.status || failure.status === details.status)) && (!failure.error || failure.error.test(details.text)))
  if (index < 0) return false
  current.expectedFailures.splice(index, 1)
  return true
}

function authData(selected) {
  return selected === otherAthlete
    ? offlineMe({ mapped: otherAthlete, permissions: ['profile:read', 'program:read', 'sessions:read'] })
    : offlineMe()
}

async function routeApi(route, current) {
  const request = route.request()
  const url = new URL(request.url())
  const path = url.pathname.replace(/^\/api/, '')
  const method = request.method()
  const body = bodyOf(request)
  current.requests.push({ request, method, path, body, phase: current.phase, selected: request.headers()['x-selected-athlete-pk'] })

  if (path === '/auth/me' && method === 'GET') return route.fulfill(response(authData(request.headers()['x-selected-athlete-pk'])))
  if (path === '/programs/current' && method === 'GET') return route.fulfill(response({ data: current.program }))
  if (path === '/exercises' && method === 'GET') return route.fulfill(response({ data: [] }))
  if (path === '/grants/requests' && method === 'GET') return route.fulfill(response({ data: offlineRelationships }))
  if (path === '/notifications' && method === 'GET') return route.fulfill(response({ data: { notifications: [] } }))
  if (path === '/stats/countries' && method === 'GET') return route.fulfill(response({ data: { countries: [], country_regions: {} } }))
  if (path === '/stats/categories' && method === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ countries: [], country_regions: {} }) })
  if (path === '/competitions' && method === 'GET') return route.fulfill(response({ data: current.competitions }))
  if (path === '/authored-notes/private' && method === 'GET') return route.fulfill(response({ data: { notes: [current.note], next_cursor: null } }))
  if (path === '/authored-notes/attachments/program' && method === 'GET') return route.fulfill(response({ data: { attachments: current.attachments, next_cursor: null } }))
  if (path === '/settings/publication' && method === 'GET') return route.fulfill(response({ data: current.publication }))
  if (path === '/settings' && method === 'GET') return route.fulfill(response({ data: settings({ roles: ['athlete', 'coach'] }) }))
  if (path === '/profiles/current' && method === 'GET') return route.fulfill(response({ data: { athlete_pk: ownAthlete, nickname: 'luna', display_name: 'Luna', profile_visibility: 'private', public_training_summary_enabled: false, is_self: true, tags: [], bio: '' } }))
  if (path === '/videos' && method === 'GET') return route.fulfill(response({ data: { videos: [], exercises: [] } }))
  if (path === '/profiles/tags' && method === 'GET') return route.fulfill(response({ data: [] }))

  if (path === '/authored-notes/private' && method === 'PUT') {
    if (current.mode === 'conflict') return route.fulfill(response({ code: 'conflict', current_revision: 4, current_record: { ...current.note, text: 'Server note' } }, 409))
    if (current.mode === 'failed') return route.fulfill(response({ message: 'temporary failure' }, 503))
    current.note = { ...current.note, text: body.text, revision: current.note.revision + 1, updated_at: new Date().toISOString() }
    return route.fulfill(response({ data: current.note }))
  }
  if (path === '/authored-notes/share' && method === 'POST') {
    current.shared = body
    const shared = { ...current.attachments.find(item => item.note_id === body.note_id), text: current.note.text, source_revision: body.wanted_revision, context_domain: body.context_domain }
    current.attachments = current.attachments.map(item => item.note_id === body.note_id ? shared : item)
    return route.fulfill(response({ data: shared }))
  }
  if (path === '/settings/publication' && method === 'PUT') {
    current.publication = { domains: body.domains, revision: current.publication.revision + 1 }
    return route.fulfill(response({ data: current.publication }))
  }

  if (method === 'PUT' && /^\/sessions\/current\/2026-09-14\/[01]$/.test(path)) {
    const index = Number(path.split('/').pop())
    const sessionIndex = current.program.sessions.findIndex(session => session.id === body?.id || session.id === body?.session_id)
    if (sessionIndex < 0) return route.fulfill(response({ code: 'session_identity_conflict', current_revision: 8, current_record: null }, 409))
    if (current.mode === 'conflict') return route.fulfill(response({ code: 'conflict', current_revision: 8, current_record: { ...current.program.sessions[sessionIndex], session_notes: 'Server logged work' } }, 409))
    if (current.mode === 'failed') return route.fulfill(response({ message: 'temporary failure' }, 503))
    current.program.sessions[sessionIndex] = { ...current.program.sessions[sessionIndex], ...body }
    return route.fulfill(response({ data: { success: true, session: current.program.sessions[sessionIndex], revision: 8 } }))
  }
  if (path === '/competitions/offline-meet' && method === 'PATCH') {
    const index = current.competitions.findIndex(item => item.master_id === 'offline-meet')
    current.competitions[index] = { ...current.competitions[index], ...body }
    return route.fulfill(response({ data: current.competitions[index] }))
  }
  if (path === '/competitions/offline-meet/complete' && method === 'POST') {
    current.attemptBody = body
    return route.fulfill(response({ data: { ...current.competitions[0], results: body.results, post_meet_report: body.postMeetReport } }))
  }
  current.unhandled.push({ method, path, query: url.search })
  return route.fulfill(response({ error: `Unhandled mock request: ${method} ${path}${url.search}` }, 500))
}

async function clearDatabases(page) {
  await page.evaluate(async () => {
    for (const name of ['pl-offline', 'pl-api-cache']) {
      await new Promise(resolve => {
        const request = indexedDB.deleteDatabase(name)
        request.onsuccess = request.onerror = request.onblocked = () => resolve()
      })
    }
  })
}

async function openScenario(current, path) {
  const context = await browser.newContext()
  const page = await context.newPage()
  page.on('pageerror', error => {
    const text = `${error.name}: ${error.message}`
    if (!consumeExpectedFailure(current, 'console', { phase: current.phase, text })) current.browserErrors.push(`pageerror: ${text}`)
  })
  page.on('console', message => {
    const text = message.text()
    if (message.type() !== 'error') return
    if (consumeExpectedFailure(current, 'console', { phase: current.phase, text })) return
    if (text.includes('Failed to load resource') && current.expectedConsoleResponses > 0) { current.expectedConsoleResponses -= 1; return }
    current.browserErrors.push(`console[${current.phase}]: ${text}`)
  })
  page.on('response', response => {
    if (response.status() < 400) return
    const request = response.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api/, '')
    const record = current.requests.find(item => item.request === request)
    if (consumeExpectedFailure(current, 'response', { phase: record?.phase, method: request.method(), path, status: response.status(), text: '' })) {
      current.expectedConsoleResponses += 1
      return
    }
    current.browserErrors.push(`response: ${response.status()} ${response.url()}`)
  })
  await page.route('**/api/**', route => new URL(route.request().url()).pathname.startsWith('/api/') ? routeApi(route, current) : route.continue())
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}${path}`)
  await clearDatabases(page)
  await page.reload()
  check(current.unhandled.length === 0 && current.browserErrors.length === 0, `${path} has no unhandled mock requests or browser errors`)
  return { context, page }
}

async function queue(page) {
  return page.evaluate(async () => {
    const { listMutations } = await import('/src/api/drafts.ts')
    return listMutations()
  })
}

async function waitForQueueStatus(page, status) {
  await page.waitForFunction(async expected => {
    const { listMutations } = await import('/src/api/drafts.ts')
    return (await listMutations()).some(record => record.status === expected)
  }, status, { timeout: 5000 })
}

async function waitForQueueLength(page, length) {
  await page.waitForFunction(async expected => {
    const { listMutations } = await import('/src/api/drafts.ts')
    return (await listMutations()).length === expected
  }, length, { timeout: 5000 })
}

async function synchronize(page) {
  await page.waitForFunction(() => navigator.onLine)
}

let browser
try {
  await server.listen()
  browser = await chromium.launch({ headless: true })

  const sessionState = state()
  const session = await openScenario(sessionState, '/session/2026-09-14/0')
  await session.page.getByTestId('session-detail').waitFor()
  await session.page.getByTestId('session-notes').fill('Offline session edit')
  setPhase(sessionState, 'offline-session-save')
  expectFailure(sessionState, { kind: 'console', method: 'PUT', path: '/sessions/current/2026-09-14/0', phase: 'offline-session-save', error: /OfflineQueuedError|Saved locally/i })
  expectFailure(sessionState, { kind: 'console', phase: 'offline-session-save', error: /OfflineQueuedError|Saved locally/i })
  await session.context.setOffline(true)
  await session.page.getByTestId('session-save').click()
  await waitForQueueLength(session.page, 1)
  check(await session.page.getByText(/waiting to sync/).count() === 0, 'offline save stays silent with no sync banner')
  const sessionQueue = await queue(session.page)
  check(sessionQueue.length === 1 && sessionQueue[0].data.session_notes === 'Offline session edit' && sessionQueue[0].person_pk === offlinePerson && sessionQueue[0].athlete_pk === ownAthlete, 'offline Session edit persists in the Person/Athlete queue')
  await session.page.getByTestId('desktop-nav-sessions').click()
  await session.page.getByRole('button', { name: 'Compact', exact: true }).click()
  await session.page.getByTestId('session-list-row-2026-09-14').nth(1).click()
  await session.page.getByTestId('session-detail').waitFor()
  await session.page.getByTestId('session-notes').fill('Second offline session')
  setPhase(sessionState, 'offline-session-save-second')
  expectFailure(sessionState, { kind: 'console', phase: 'offline-session-save-second', error: /OfflineQueuedError|Saved locally/i })
  await session.page.getByTestId('session-save').click()
  await waitForQueueLength(session.page, 2)
  const sameDateQueue = await queue(session.page)
  check(sameDateQueue.length === 2 && new Set(sameDateQueue.map(record => record.data.id)).size === 2, `same-date Session drafts retain separate stable record identities: ${JSON.stringify(sameDateQueue)}`)
  await session.context.close()

  const attemptState = state()
  const attempt = await openScenario(attemptState, '/designer/competitions')
  await attempt.page.getByText('Offline Meet').waitFor()
  await attempt.page.getByText('Offline Meet').click()
  await attempt.page.getByRole('button', { name: 'Edit Post-Meet Report' }).click()
  const attemptInputs = attempt.page.locator('[role="dialog"] input[type="number"]')
  await attemptInputs.nth(3).fill('135')
  setPhase(attemptState, 'offline-attempt-save')
  expectFailure(attemptState, { kind: 'console', method: 'POST', path: '/competitions/offline-meet/complete', phase: 'offline-attempt-save', error: /OfflineQueuedError|Saved locally/i })
  await attempt.context.setOffline(true)
  await attempt.page.getByRole('button', { name: 'Complete', exact: true }).click()
  await waitForQueueLength(attempt.page, 1)
  const attemptQueue = await queue(attempt.page)
  check(attemptQueue.length === 1 && attemptQueue[0].url === '/competitions/offline-meet/complete' && attemptQueue[0].data.postMeetReport.attempts[0].kg === 135, 'offline Attempt edit persists as a queued mutation')
  await attempt.context.close()

  const reconnectState = state()
  const reconnect = await openScenario(reconnectState, '/session/2026-09-14/0')
  await reconnect.page.getByTestId('session-detail').waitFor()
  await reconnect.page.getByTestId('session-notes').fill('Sync unchanged base')
  setPhase(reconnectState, 'offline-session-save')
  expectFailure(reconnectState, { kind: 'console', method: 'PUT', path: '/sessions/current/2026-09-14/0', phase: 'offline-session-save', error: /OfflineQueuedError|Saved locally/i })
  await reconnect.context.setOffline(true)
  await reconnect.page.getByTestId('session-save').click()
  await waitForQueueLength(reconnect.page, 1)
  reconnectState.program.sessions.reverse()
  setPhase(reconnectState, 'online-session-replay')
  const replayed = reconnect.page.waitForRequest(request => request.method() === 'PUT' && new URL(request.url()).pathname === '/api/sessions/current/2026-09-14/0')
  await reconnect.context.setOffline(false)
  const replayRequest = await replayed
  await waitForQueueLength(reconnect.page, 0)
  await reconnect.page.waitForFunction(async () => {
    const { readDraft } = await import('/src/api/drafts.ts')
    return !(await readDraft('session:current:session-squat'))
  }, null, { timeout: 5000 })
  const replayBody = replayRequest.postDataJSON()
  check(replayBody.id === 'session-squat' && replayBody.session_notes === 'Sync unchanged base' && reconnectState.program.sessions.find(session => session.id === 'session-squat').session_notes === 'Sync unchanged base', 'replay resolves the intended Session after same-day reorder and clears its queue and draft records')
  await reconnect.context.close()

  const failedState = state({ mode: 'failed' })
  const failed = await openScenario(failedState, '/session/2026-09-14/0')
  await failed.page.getByTestId('session-detail').waitFor()
  await failed.page.getByTestId('session-notes').fill('Retry me')
  setPhase(failedState, 'offline-session-save')
  expectFailure(failedState, { kind: 'console', method: 'PUT', path: '/sessions/current/2026-09-14/0', phase: 'offline-session-save', error: /OfflineQueuedError|Saved locally/i })
  await failed.context.setOffline(true)
  await failed.page.getByTestId('session-save').click()
  await waitForQueueLength(failed.page, 1)
  setPhase(failedState, 'online-failed-sync')
  expectFailure(failedState, { kind: 'response', method: 'PUT', path: '/sessions/current/2026-09-14/0', phase: 'online-failed-sync', status: 503 })
  await failed.context.setOffline(false)
  await synchronize(failed.page)
  await waitForQueueStatus(failed.page, 'failed')
  const failedQueue = await queue(failed.page)
  check(failedQueue.length === 1 && ['failed', 'pending'].includes(failedQueue[0].status) && failedQueue[0].data.session_notes === 'Retry me', 'failed sync keeps the queued Session edit for retry')
  setPhase(failedState, 'failed-session-retention')
  for (let retry = 0; retry < 6; retry += 1) expectFailure(failedState, { kind: 'response', method: 'PUT', path: '/sessions/current/2026-09-14/0', phase: 'failed-session-retention', status: 503 })
  await failed.page.goto(`http://127.0.0.1:${server.httpServer.address().port}/sessions`)
  await failed.page.goto(`http://127.0.0.1:${server.httpServer.address().port}/session/2026-09-14/0`)
  await failed.page.getByTestId('session-detail').waitFor()
  check(await failed.page.getByTestId('session-notes').inputValue() === 'Retry me', 'failed Session editor reopens with the typed draft')
  await failed.page.reload()
  await failed.page.getByTestId('session-detail').waitFor()
  check(await failed.page.getByTestId('session-notes').inputValue() === 'Retry me', 'failed Session editor reloads with the typed draft')
  const drafts = await failed.page.evaluate(async () => {
    const { readDraft } = await import('/src/api/drafts.ts')
    return {
      own: await readDraft('session:current:session-squat', '["person-offline","athlete-own"]'),
      other: await readDraft('session:current:session-squat', '["person-offline","athlete-other"]'),
    }
  })
  check(drafts.own?.value?.session_notes === 'Retry me' && !drafts.other, `Session drafts are partitioned by Athlete: ${JSON.stringify(drafts)}`)
  await failed.context.close()

  const noteState = state()
  const notes = await openScenario(noteState, '/my-notes')
  await notes.page.getByTestId('authored-notes').waitFor()
  await notes.page.getByText('Previously shared revision').waitFor()
  check(await notes.page.getByText('Attached revision 1').count() === 1, 'private note edit leaves the old shared attachment visible')
  await notes.page.getByTestId('authored-notes').locator('textarea').first().fill('Private offline revision')
  setPhase(noteState, 'offline-note-save')
  expectFailure(noteState, { kind: 'console', method: 'PUT', path: '/authored-notes/private', phase: 'offline-note-save', error: /OfflineQueuedError|Saved locally/i })
  await notes.context.setOffline(true)
  await notes.page.getByRole('button', { name: 'Save private', exact: true }).click()
  await notes.page.getByText('Private note saved for when you reconnect').waitFor()
  const noteQueue = await queue(notes.page)
  check(noteQueue.length === 1 && noteQueue[0].url === '/authored-notes/private' && noteQueue[0].data.text === 'Private offline revision', 'offline authored-note edit queues as a private original')
  await notes.context.setOffline(false)
  setPhase(noteState, 'online-note-sync')
  await synchronize(notes.page)
  await notes.page.waitForFunction(async () => {
    const { listMutations } = await import('/src/api/drafts.ts')
    return (await listMutations()).length === 0
  }, null, { timeout: 5000 })
  await notes.page.getByText('Revision 3').waitFor()
  check(await notes.page.getByText('Attached revision 1').count() === 1, 'replayed private note does not replace its old attachment before sharing')
  await notes.page.getByTestId('authored-notes').locator('textarea').first().fill('Private online followup')
  setPhase(noteState, 'online-note-followup')
  const followupRequestPromise = notes.page.waitForRequest(request => request.method() === 'PUT' && new URL(request.url()).pathname === '/api/authored-notes/private')
  await notes.page.getByRole('button', { name: 'Save private', exact: true }).click()
  const followupRequest = await followupRequestPromise
  await notes.page.getByText('Private note saved').waitFor()
  const followupBody = followupRequest.postDataJSON()
  check(followupBody.expected_revision === 3, `post-replay private note save uses the refreshed revision: ${JSON.stringify(noteState.requests.filter(request => request.path === '/authored-notes/private'))}`)
  await notes.page.getByRole('button', { name: 'Share revision' }).click()
  check(noteState.shared?.context_domain === 'program' && noteState.shared?.note_id === 'offline-note' && noteState.shared?.wanted_revision === 4 && noteState.attachments[0].source_revision === 4, 'sharing explicitly publishes the latest private revision')
  await notes.context.close()

  const publicationState = state()
  const publication = await openScenario(publicationState, '/settings')
  await publication.page.getByText('Published training domains').waitFor()
  await publication.page.getByRole('checkbox', { name: 'Sessions and training logs' }).check()
  await publication.context.setOffline(true)
  await publication.page.getByRole('button', { name: 'Save publication' }).click()
  await publication.page.getByText('Connect to publish changes. Your selections are preserved.').waitFor()
  await publication.context.setOffline(false)
  await publication.page.reload()
  await publication.page.getByText('Your unsent publication choices were restored. Save when connected, or reload to discard them.').waitFor()
  check(await publication.page.getByRole('checkbox', { name: 'Sessions and training logs' }).isChecked(), 'offline publication form restores unsent selections after reload')
  await publication.context.close()

  const states = [sessionState, attemptState, reconnectState, failedState, noteState, publicationState]
  check(states.every(item => item.unhandled.length === 0 && item.browserErrors.length === 0), 'offline scenarios have no unhandled mock requests or browser errors')
  console.log(JSON.stringify({ verification: 'local Chromium DOM with simulated API interception; no deployment or Authentik evidence', passed, uncovered: ['delegated revocation UI/cache clearing', 'context switching during pending sync', 'upload and AI form preservation', 'relationship approval while offline'] }, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
