#!/usr/bin/env node
/**
 * Live browser regression tests for the powerlifting session page.
 *
 * The suite targets the private if-portals-test pod services and writes only
 * to mapped_pk=test. It creates temporary future-dated sessions, verifies the
 * session detail workflow, then restores all touched data before exiting.
 *
 * By default this port-forwards the deployed frontend/backend services. Set
 * POWERLIFTING_TEST_USE_LOCAL_FRONTEND=1 only for local harness debugging.
 */

import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const appRoot = path.join(repoRoot, 'utils', 'powerlifting-app')
const requireFromApp = createRequire(path.join(appRoot, 'package.json'))
const { chromium, expect } = requireFromApp('@playwright/test')
const { DynamoDBClient } = requireFromApp('@aws-sdk/client-dynamodb')
const { DynamoDBDocumentClient, GetCommand, QueryCommand } = requireFromApp('@aws-sdk/lib-dynamodb')

const namespace = process.env.POWERLIFTING_TEST_NAMESPACE || 'if-portals-test'
const useLocalFrontend = process.env.POWERLIFTING_TEST_USE_LOCAL_FRONTEND === '1'
const useDeployedFrontend = !useLocalFrontend
const backendPort = Number(process.env.POWERLIFTING_TEST_BACKEND_PORT || (useDeployedFrontend ? 3005 : 13005))
const frontendPort = Number(process.env.POWERLIFTING_TEST_FRONTEND_PORT || 3001)
const backendOrigin = process.env.POWERLIFTING_TEST_BACKEND_ORIGIN || `http://127.0.0.1:${backendPort}`
const apiBase = (process.env.POWERLIFTING_TEST_API_BASE_URL || `${backendOrigin}/api`).replace(/\/$/, '')
const frontendUrl = (process.env.POWERLIFTING_TEST_FRONTEND_URL || `http://localhost:${frontendPort}`).replace(/\/$/, '')
const awsRegion = process.env.AWS_REGION || 'ca-central-1'
const healthTableName = process.env.IF_HEALTH_TABLE_NAME || 'if-health'
const sessionsTableName = process.env.IF_SESSIONS_TABLE_NAME || 'if-sessions'
const targetPk = process.env.POWERLIFTING_TEST_MAPPED_PK || 'test'
const runId = `ui-session-detail-${Date.now()}`
const tempBlock = `ui-block-${Date.now()}`
const historicalBlock = `ui-historical-${Date.now()}`
const ignoredBrowserErrorFragments = [
  "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a <meta> element.",
  'Failed to load resource: the server responded with a status of 401 (Unauthorized)',
]

const dynamo = DynamoDBDocumentClient.from(new DynamoDBClient({ region: awsRegion }))
const children = []
const touchedDates = new Set()
const touchedExerciseIds = new Set()
let failures = 0

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function isoDateFromSeed(offset) {
  const seed = Math.floor(Date.now() / 1000) % 5000
  const date = new Date(Date.UTC(2040, 0, 1 + seed + offset))
  return date.toISOString().slice(0, 10)
}

function isoDateFromLocalParts(year, monthIndex, day) {
  return `${year}-${String(monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function freeDateInCurrentMonth(sessions) {
  const used = new Set(sessions.map((session) => session.date))
  const today = new Date()
  const year = today.getFullYear()
  const month = today.getMonth()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  for (let day = today.getDate(); day <= daysInMonth; day += 1) {
    const candidate = isoDateFromLocalParts(year, month, day)
    if (!used.has(candidate)) return candidate
  }
  return null
}

function dayOfWeek(dateStr) {
  return new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: 'UTC' }).format(new Date(`${dateStr}T00:00:00Z`))
}

async function canReach(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1500) })
    return response.ok
  } catch {
    return false
  }
}

function isLocalUrl(url) {
  try {
    const hostname = new URL(url).hostname
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
  } catch {
    return false
  }
}

function spawnChild(command, args, options) {
  const child = spawn(command, args, { ...options, detached: true })
  children.push(child)
  return child
}

function stopChildren() {
  for (const child of children.reverse()) {
    if (child.exitCode === null && child.signalCode === null) {
      try {
        process.kill(-child.pid, 'SIGTERM')
      } catch {
        child.kill('SIGTERM')
      }
    }
  }
}

async function ensureBackendPortForward() {
  const healthUrl = `${apiBase.replace(/\/api$/, '')}/health`
  if (await canReach(healthUrl)) return
  if (!isLocalUrl(healthUrl)) {
    throw new Error(`Cannot reach configured backend health endpoint: ${healthUrl}`)
  }

  const child = spawnChild(
    'kubectl',
    ['-n', namespace, 'port-forward', 'svc/powerlifting-app-backend', `${backendPort}:3005`],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  )

  let stderr = ''
  child.stderr.on('data', (chunk) => {
    stderr += String(chunk)
  })

  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await canReach(healthUrl)) return
    if (child.exitCode !== null) {
      throw new Error(`kubectl port-forward exited early: ${stderr.trim()}`)
    }
    await sleep(250)
  }

  throw new Error(`Timed out waiting for backend port-forward: ${healthUrl}`)
}

async function ensureDeployedFrontendPortForward() {
  if (await canReach(frontendUrl)) return
  if (!isLocalUrl(frontendUrl)) {
    throw new Error(`Cannot reach configured frontend URL: ${frontendUrl}`)
  }

  const child = spawnChild(
    'kubectl',
    ['-n', namespace, 'port-forward', 'svc/powerlifting-app-frontend', `${frontendPort}:3001`],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  )

  let stderr = ''
  child.stderr.on('data', (chunk) => {
    stderr += String(chunk)
  })

  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await canReach(frontendUrl)) return
    if (child.exitCode !== null) {
      throw new Error(`kubectl frontend port-forward exited early: ${stderr.trim()}`)
    }
    await sleep(250)
  }

  throw new Error(`Timed out waiting for deployed frontend port-forward: ${frontendUrl}`)
}

async function ensureLocalFrontendServer() {
  const child = spawnChild(
    'npm',
    ['run', 'dev', '--workspace=frontend', '--', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'],
    {
      cwd: appRoot,
      env: {
        ...process.env,
        VITE_API_BASE_URL: '/api',
        VITE_DEV_API_PROXY: backendOrigin,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )

  let stderr = ''
  child.stderr.on('data', (chunk) => {
    stderr += String(chunk)
  })

  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (await canReach(frontendUrl)) return
    if (child.exitCode !== null) {
      throw new Error(`Vite frontend exited early: ${stderr.trim()}`)
    }
    await sleep(250)
  }

  throw new Error(`Timed out waiting for local frontend: ${frontendUrl}`)
}

async function ensureFrontendServer() {
  if (useDeployedFrontend) {
    await ensureDeployedFrontendPortForward()
    return
  }
  await ensureLocalFrontendServer()
}

async function request(pathname, init = {}) {
  const response = await fetch(`${apiBase}${pathname}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  })
  const text = await response.text()
  const body = text ? JSON.parse(text) : null
  if (!response.ok) {
    throw new Error(`${init.method || 'GET'} ${pathname} failed ${response.status}: ${JSON.stringify(body)}`)
  }
  return body
}

async function loadProgram() {
  return (await request('/programs/current')).data
}

async function updateMeta(field, value) {
  await request('/programs/current/meta', {
    method: 'PUT',
    body: JSON.stringify({ field, value }),
  })
}

async function createSession(session) {
  touchedDates.add(session.date)
  const created = (await request('/sessions/current', {
    method: 'POST',
    body: JSON.stringify(session),
  })).data.session
  if ((session.block ?? 'current') !== (created.block ?? 'current')) {
    const index = await findSessionIndex(created.date)
    const corrected = {
      ...created,
      ...session,
      id: created.id || session.id,
      block: session.block,
      phase: session.phase,
    }
    await putSession(created.date, index, corrected)
    return corrected
  }
  return created
}

async function upsertExercise(exercise) {
  touchedExerciseIds.add(exercise.id)
  await request('/exercises', {
    method: 'POST',
    body: JSON.stringify(exercise),
  })
}

async function deleteExerciseIfExists(id) {
  try {
    await request(`/exercises/${encodeURIComponent(id)}`, { method: 'DELETE' })
  } catch (error) {
    if (!String(error).includes('404')) throw error
  }
}

async function putSession(date, index, session) {
  await request(`/sessions/current/${encodeURIComponent(date)}/${index}`, {
    method: 'PUT',
    body: JSON.stringify(session),
  })
}

async function deleteSessionIfExists(date) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const program = await loadProgram()
    const index = program.sessions.findIndex((session) => session.date === date)
    if (index < 0) return
    await request(`/sessions/current/${encodeURIComponent(date)}/${index}`, { method: 'DELETE' })
  }
}

function makeSession(date, block = 'current', exercises = []) {
  return {
    id: `${runId}-${date}`,
    date,
    day: dayOfWeek(date),
    week: 'W1',
    week_number: 1,
    phase: { name: 'UI Test', intent: 'regression', start_week: 1, end_week: 1, block },
    block,
    status: 'planned',
    completed: false,
    planned_exercises: [],
    exercises,
    session_notes: '',
    session_rpe: null,
    body_weight_kg: null,
  }
}

async function currentProgramSkFromDynamo() {
  const result = await dynamo.send(new GetCommand({
    TableName: healthTableName,
    Key: { pk: targetPk, sk: 'program#current' },
    ConsistentRead: true,
  }))
  const refSk = result.Item?.ref_sk
  if (!refSk) {
    throw new Error(`DynamoDB current pointer missing: table=${healthTableName} pk=${targetPk}`)
  }
  return String(refSk)
}

function sortDynamoSessions(items) {
  return [...items].sort((a, b) => (
    String(a.date || '').localeCompare(String(b.date || '')) ||
    Number(a.same_day_ordinal || 0) - Number(b.same_day_ordinal || 0) ||
    Number(a.source_index || 0) - Number(b.source_index || 0) ||
    String(a.sk || '').localeCompare(String(b.sk || ''))
  ))
}

async function loadDynamoSession(date, sessionId) {
  const programSk = await currentProgramSkFromDynamo()
  const items = []
  let ExclusiveStartKey
  do {
    const result = await dynamo.send(new QueryCommand({
      TableName: sessionsTableName,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: {
        ':pk': targetPk,
        ':prefix': `session#${programSk}#${date}#`,
      },
      ConsistentRead: true,
      ExclusiveStartKey,
    }))
    items.push(...(result.Items || []))
    ExclusiveStartKey = result.LastEvaluatedKey
  } while (ExclusiveStartKey)

  const sorted = sortDynamoSessions(items)
  const match = sessionId
    ? sorted.find((item) => item.id === sessionId || item.session_id === sessionId)
    : sorted[0]
  if (!match) {
    throw new Error(`DynamoDB session missing: table=${sessionsTableName} pk=${targetPk} date=${date} id=${sessionId}`)
  }
  return match
}

async function waitForDynamoSession(date, sessionId, predicate, label) {
  let lastItem = null
  for (let attempt = 0; attempt < 40; attempt += 1) {
    lastItem = await loadDynamoSession(date, sessionId)
    if (predicate(lastItem)) return lastItem
    await sleep(250)
  }
  throw new Error(`${label} did not reach DynamoDB. Last item: ${JSON.stringify(lastItem)}`)
}

async function fulfillAuth(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user: { discord_id: 'test-session-detail', username: 'test-session-detail', avatar: null },
      mapped_pk: 'test',
      readOnly: false,
    }),
  })
}

async function installApiRouting(page, options = {}) {
  const { programOverride = null } = options

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (url.pathname === '/api/auth/me') {
      await fulfillAuth(route)
      return
    }

    if (programOverride && url.pathname === '/api/programs/current' && request.method() === 'GET') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: programOverride, error: null }),
      })
      return
    }

    if (!useDeployedFrontend) {
      await route.continue()
      return
    }

    const proxiedPath = url.pathname.replace(/^\/api/, '') || '/'
    const response = await route.fetch({ url: `${apiBase}${proxiedPath}${url.search}` })
    await route.fulfill({ response })
  })
}

async function record(label, fn) {
  try {
    await fn()
    console.log(`  PASS: ${label}`)
  } catch (error) {
    failures += 1
    console.error(`  FAIL: ${label}`)
    console.error(`        ${error instanceof Error ? error.message : String(error)}`)
  }
}

function control(page, testId) {
  const root = page.getByTestId(testId)
  const input = page.locator([
    `[data-testid="${testId}"] input`,
    `[data-testid="${testId}"] textarea`,
    `input[data-testid="${testId}"]`,
    `textarea[data-testid="${testId}"]`,
    `button[data-testid="${testId}"]`,
    `[data-testid="${testId}"]`,
  ].join(', ')).first()
  return { root, input }
}

async function fillControl(page, testId, value) {
  const { root, input } = control(page, testId)
  if (await input.count()) {
    await input.fill(String(value))
    return
  }
  await root.fill(String(value))
}

async function blurControl(page, testId) {
  const { input } = control(page, testId)
  if (await input.count()) {
    await input.blur()
  }
}

async function controlValue(page, testId) {
  const { root, input } = control(page, testId)
  if (await input.count()) return input.inputValue()
  return root.inputValue()
}

async function selectByLabel(page, testId, label) {
  const { root } = control(page, testId)
  await root.click()
  const option = page.getByRole('option', { name: label }).first()
  if (await option.count()) {
    await option.click()
    return
  }
  await page.getByText(label, { exact: true }).last().click()
}

async function pickVisibleCalendarDate(page, testId, date) {
  const day = String(Number(date.slice(8, 10)))
  await page.getByTestId(testId).click()
  const exactDay = page.getByRole('button', { name: new RegExp(`^${day}$`) }).first()
  if (await exactDay.count()) {
    await exactDay.click()
    return
  }
  await page.locator('button').filter({ hasText: new RegExp(`^${day}$`) }).last().click()
}

async function expandWeek(page, weekNumber) {
  const week = page.getByTestId(`session-week-${weekNumber}`)
  if (!(await week.count())) return
  const visibleRows = await week.locator('[data-testid^="session-list-row-"]').count()
  if (visibleRows > 0) return
  await week.locator('button').first().click()
}

async function ensureUnit(page, expectedUnit) {
  const toggle = page.getByTestId('unit-toggle')
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const text = (await toggle.textContent())?.trim().toLowerCase()
    if (text === expectedUnit) return
    await toggle.click()
    await sleep(200)
  }
  const text = (await toggle.textContent())?.trim().toLowerCase()
  if (text !== expectedUnit) throw new Error(`Expected unit ${expectedUnit}, got ${text}`)
}

async function saveSessionFromUi(page) {
  const save = page.getByTestId('session-save')
  try {
    await expect(save).toBeEnabled({ timeout: 3000 })
  } catch {
    await expect(save).toBeDisabled()
    await sleep(500)
    return
  }
  await Promise.all([
    page.waitForResponse((response) => (
      response.request().method() === 'PUT' &&
      response.url().includes('/api/sessions/current/')
    ), { timeout: 20000 }),
    save.click(),
  ])
  await expect(save).toBeDisabled({ timeout: 15000 })
}

async function findSessionIndex(date) {
  const program = await loadProgram()
  const index = program.sessions.findIndex((session) => session.date === date)
  if (index < 0) throw new Error(`Session ${date} missing from current program`)
  return index
}

async function openSession(page, date) {
  const index = await findSessionIndex(date)
  await page.goto(`${frontendUrl}/session/${date}/${index}`, { waitUntil: 'networkidle' })
  await expect(page.getByTestId('session-detail')).toBeVisible({ timeout: 15000 })
  return index
}

async function chooseSetStatus(page, exerciseIndex, setIndex, statusLabel) {
  await page.getByTestId(`set-status-${exerciseIndex}-${setIndex}`).click()
  await page.getByRole('menuitem', { name: statusLabel }).click()
}

async function getExerciseNamesFromApi(date) {
  const program = await loadProgram()
  const session = program.sessions.find((candidate) => candidate.date === date)
  if (!session) throw new Error(`Session ${date} missing after save`)
  return session.exercises.map((exercise) => exercise.name)
}

function fallbackNoteDraftLike(date, notes) {
  return notes.startsWith(`Session on ${date}`) && (
    notes.includes('Overall:') ||
    notes.includes('Technique:') ||
    notes.includes('Failed sets/RPE:') ||
    notes.includes('Planned vs executed:')
  )
}

async function pickGlossaryExercises() {
  const exercises = (await request('/exercises')).data || []
  let barbell = exercises.find((exercise) => ['barbell', 'hex_bar'].includes(exercise.equipment))?.name
  let nonBarbell = exercises.find((exercise) => ['machine', 'cable', 'bodyweight'].includes(exercise.equipment))?.name

  if (!barbell) {
    const id = `${runId}-barbell-glossary`
    barbell = `${runId} Test Barbell Lift`
    await upsertExercise({
      id,
      name: barbell,
      category: 'squat',
      fatigue_category: 'primary_axial',
      primary_muscles: ['quads'],
      secondary_muscles: ['glutes'],
      tertiary_muscles: [],
      equipment: 'barbell',
      description: 'Temporary barbell fixture for live UI regression tests.',
      how_to_perform: 'Temporary fixture.',
      why_do_it: 'Temporary fixture.',
      fatigue_profile_source: 'manual',
      fatigue_profile: { axial: 0.8, neural: 0.7, peripheral: 0.5, systemic: 0.4 },
      fatigue_profile_reasoning: 'Temporary fixture.',
    })
  }

  if (!nonBarbell) {
    const id = `${runId}-machine-glossary`
    nonBarbell = `${runId} Test Machine Row`
    await upsertExercise({
      id,
      name: nonBarbell,
      category: 'back',
      fatigue_category: 'accessory',
      primary_muscles: ['lats'],
      secondary_muscles: ['biceps'],
      tertiary_muscles: [],
      equipment: 'machine',
      description: 'Temporary machine fixture for live UI regression tests.',
      how_to_perform: 'Temporary fixture.',
      why_do_it: 'Temporary fixture.',
      fatigue_profile_source: 'manual',
      fatigue_profile: { axial: 0.1, neural: 0.2, peripheral: 0.5, systemic: 0.2 },
      fatigue_profile_reasoning: 'Temporary fixture.',
    })
  }

  return { barbell, nonBarbell }
}

async function testAddAndDeleteSession(page, date) {
  await deleteSessionIfExists(date)
  await page.goto(`${frontendUrl}/sessions?view=Compact`, { waitUntil: 'networkidle' })
  await page.getByTestId('session-list-add-session').click()
  await pickVisibleCalendarDate(page, 'session-create-date', date)
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'POST' && response.url().includes('/api/sessions/current'), { timeout: 20000 }),
    page.getByTestId('session-create-submit').click(),
  ])
  await expect(page.getByTestId('session-detail')).toBeVisible({ timeout: 15000 })

  page.once('dialog', (dialog) => dialog.accept())
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'DELETE' && response.url().includes('/api/sessions/current/'), { timeout: 20000 }),
    page.getByTestId('session-delete').click(),
  ])
  await expect.poll(async () => (await loadProgram()).sessions.some((session) => session.date === date)).toBe(false)
}

async function testEmptySessionsState(browser, program) {
  const context = await browser.newContext({ viewport: { width: 1365, height: 900 } })
  const page = await context.newPage()
  await installApiRouting(page, { programOverride: { ...clone(program), sessions: [] } })
  try {
    await page.goto(`${frontendUrl}/sessions?view=Compact`, { waitUntil: 'networkidle' })
    await expect(page.getByText(/no sessions/i)).toBeVisible({ timeout: 5000 })
  } finally {
    await context.close()
  }
}

async function testBlockSwitching(page, currentDate, otherDate) {
  await deleteSessionIfExists(currentDate)
  await deleteSessionIfExists(otherDate)
  await createSession(makeSession(currentDate, 'current', [{ name: `${runId} Current Block Lift`, sets: 1, reps: 1, kg: 60, notes: '' }]))
  await createSession(makeSession(otherDate, tempBlock, [{ name: `${runId} Other Block Lift`, sets: 1, reps: 1, kg: 70, notes: '' }]))

  await page.goto(`${frontendUrl}/sessions?view=Compact`, { waitUntil: 'networkidle' })
  await expandWeek(page, 1)
  await expect(page.getByTestId(`session-list-row-${currentDate}`)).toBeVisible({ timeout: 15000 })
  await page.goto(`${frontendUrl}/sessions?view=Compact&block=${encodeURIComponent(tempBlock)}`, { waitUntil: 'networkidle' })
  await expandWeek(page, 1)
  await expect(page.getByTestId(`session-list-row-${otherDate}`)).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId(`session-list-row-${currentDate}`)).not.toBeVisible({ timeout: 5000 })

  await page.goto(`${frontendUrl}/sessions?view=Agenda&block=${encodeURIComponent(tempBlock)}`, { waitUntil: 'networkidle' })
  await expect(page.getByText(`${runId} Other Block Lift`)).toBeVisible({ timeout: 15000 })
  await expect(page.getByText(`${runId} Current Block Lift`)).not.toBeVisible({ timeout: 5000 })
}

async function testSessionDetail(page, date, glossaryNames) {
  const { barbell, nonBarbell } = glossaryNames
  await deleteSessionIfExists(date)
  const created = await createSession(makeSession(date))
  await openSession(page, date)
  await ensureUnit(page, 'kg')

  const sessionRpe = control(page, 'session-rpe').input
  const exerciseRpe = control(page, 'exercise-rpe-0').input

  await page.getByTestId('session-add-exercise').click()
  await page.getByTestId('session-add-exercise').click()
  await page.getByTestId('session-add-exercise').click()
  await page.getByTestId('session-add-exercise').click()

  await fillControl(page, 'exercise-name-0', barbell)
  await fillControl(page, 'exercise-sets-0', 3)
  await fillControl(page, 'exercise-reps-0', 5)
  await fillControl(page, 'exercise-weight-0', 100)
  await fillControl(page, 'exercise-rpe-0', 8.5)
  await fillControl(page, 'exercise-notes-0', `${runId} first duplicate notes`)

  await fillControl(page, 'exercise-name-1', barbell)
  await fillControl(page, 'exercise-sets-1', 2)
  await fillControl(page, 'exercise-reps-1', 6)
  await fillControl(page, 'exercise-weight-1', 90)
  await fillControl(page, 'exercise-notes-1', `${runId} second duplicate notes`)

  await fillControl(page, 'exercise-name-2', nonBarbell)
  await fillControl(page, 'exercise-sets-2', 4)
  await fillControl(page, 'exercise-reps-2', 12)
  await fillControl(page, 'exercise-weight-2', 50)
  await fillControl(page, 'exercise-notes-2', `${runId} non-barbell notes`)

  await fillControl(page, 'exercise-name-3', `${runId} Delete Me`)
  await page.getByTestId('exercise-delete-3').click()
  await expect(page.getByTestId('session-exercise-3')).not.toBeVisible({ timeout: 5000 })

  await record('RPE inputs expose 0.5 step plus 1-10 browser bounds', async () => {
    const attrs = {
      sessionStep: await sessionRpe.getAttribute('step'),
      exerciseStep: await exerciseRpe.getAttribute('step'),
      sessionMin: await sessionRpe.getAttribute('min'),
      sessionMax: await sessionRpe.getAttribute('max'),
      exerciseMin: await exerciseRpe.getAttribute('min'),
      exerciseMax: await exerciseRpe.getAttribute('max'),
    }
    if (
      attrs.sessionStep !== '0.5' ||
      attrs.exerciseStep !== '0.5' ||
      attrs.sessionMin !== '1' ||
      attrs.sessionMax !== '10' ||
      attrs.exerciseMin !== '1' ||
      attrs.exerciseMax !== '10'
    ) {
      throw new Error(`Unexpected RPE input attributes: ${JSON.stringify(attrs)}`)
    }
  })

  await fillControl(page, 'session-rpe', -1)
  await blurControl(page, 'session-rpe')
  await expect(control(page, 'session-rpe').input).toHaveValue('')
  await fillControl(page, 'session-rpe', 11)
  await blurControl(page, 'session-rpe')
  await expect(control(page, 'session-rpe').input).toHaveValue('')
  await fillControl(page, 'exercise-rpe-0', 8.25)
  await blurControl(page, 'exercise-rpe-0')
  await expect(control(page, 'exercise-rpe-0').input).toHaveValue('')
  await fillControl(page, 'exercise-rpe-0', 8.5)
  await fillControl(page, 'session-rpe', 8.5)

  await chooseSetStatus(page, 0, 0, 'Completed')
  await chooseSetStatus(page, 0, 1, 'Failed')
  await page.getByLabel('Fatigue').check()
  await page.getByTestId('failed-set-reasons-save').click()
  await chooseSetStatus(page, 0, 2, 'Skipped')

  await fillControl(page, 'session-body-weight', 100)
  await fillControl(page, 'session-notes', `${runId} session notes with duplicate exercises and failed-set marker ${Date.now()}`)

  await saveSessionFromUi(page)
  let saved = (await loadProgram()).sessions.find((session) => session.date === date)
  if (!saved) throw new Error(`Saved session ${date} missing`)
  if (saved.exercises.length !== 3) throw new Error(`Expected 3 exercises after delete, got ${saved.exercises.length}`)
  if (saved.exercises.filter((exercise) => exercise.name === barbell).length !== 2) {
    throw new Error('Duplicate exercise names were not preserved')
  }
  if (saved.exercises[0].set_statuses.join(',') !== 'completed,failed,skipped') {
    throw new Error(`Set statuses did not persist: ${saved.exercises[0].set_statuses}`)
  }
  if (saved.exercises[0].failed_set_reasons?.[1]?.[0] !== 'fatigue') {
    throw new Error(`Failed set reason did not persist: ${JSON.stringify(saved.exercises[0].failed_set_reasons)}`)
  }
  if (saved.exercises[1].set_statuses.length !== 2) {
    throw new Error(`Reducing set count did not delete extra set status entries: ${saved.exercises[1].set_statuses.length}`)
  }
  if (saved.session_rpe !== 8.5 || saved.exercises[0].rpe !== 8.5) {
    throw new Error(`RPE values did not persist at 8.5: session=${saved.session_rpe} exercise=${saved.exercises[0].rpe}`)
  }

  await waitForDynamoSession(date, created.id, (item) => item.session_notes === saved.session_notes, 'Session detail save')
  await page.reload({ waitUntil: 'networkidle' })
  await expect(control(page, 'session-notes').input).toHaveValue(saved.session_notes, { timeout: 15000 })

  await ensureUnit(page, 'lb')
  await expect(control(page, 'exercise-weight-0').input).toHaveValue('220.5', { timeout: 10000 })
  await fillControl(page, 'exercise-weight-0', 225)
  await saveSessionFromUi(page)
  saved = (await loadProgram()).sessions.find((session) => session.date === date)
  if (Math.abs(saved.exercises[0].kg - 102.058) > 0.02) {
    throw new Error(`LB edit did not save as kg correctly: ${saved.exercises[0].kg}`)
  }
  await ensureUnit(page, 'kg')

  await page.getByTestId('exercise-drag-handle-2').dragTo(page.getByTestId('exercise-drag-handle-0'))
  await saveSessionFromUi(page)
  const order = await getExerciseNamesFromApi(date)
  if (order[0] !== nonBarbell) {
    throw new Error(`Exercise drag order was not preserved. Order: ${order.join(' | ')}`)
  }

  return { date, createdId: created.id, barbell, nonBarbell }
}

async function testAiNotes(page, detail) {
  let capturedPayload = null
  await page.route('**/api/sessions/current/**/notes/draft', async (route) => {
    capturedPayload = JSON.parse(route.request().postData() || '{}')
    await route.continue()
  })

  await page.getByTestId('session-notes-helper').click()
  await fillControl(page, 'notes-helper-overall', `${runId} AI overall marker`)
  await fillControl(page, 'notes-helper-failed-sets', `${runId} failed set reason should be summarized`)
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST' &&
    response.url().includes('/api/sessions/current/') &&
    response.url().includes('/notes/draft')
  ), { timeout: 120000 })
  await page.getByTestId('notes-helper-draft-button').click()
  const response = await responsePromise
  if (!response.ok()) {
    throw new Error(`AI notes request failed ${response.status()}: ${await response.text()}`)
  }
  const body = await response.json()
  const notes = String(body?.data?.notes || '')
  await expect(control(page, 'notes-helper-draft').input).toHaveValue(/.+/, { timeout: 15000 })

  if (!capturedPayload?.session?.exercises?.some((exercise) => exercise.name === detail.nonBarbell)) {
    throw new Error('AI notes payload did not include the current session exercises')
  }
  const firstExercise = capturedPayload.session.exercises[0]
  if (!firstExercise || firstExercise.sets == null || firstExercise.reps == null || firstExercise.kg == null) {
    throw new Error(`AI notes payload omitted set/rep/kg details: ${JSON.stringify(firstExercise)}`)
  }
  if (fallbackNoteDraftLike(detail.date, notes)) {
    throw new Error(`AI notes appear to be the local fallback, not a model draft: ${JSON.stringify(notes)}`)
  }
}

async function testToolkitAndTools(page, detail) {
  await openSession(page, detail.date)
  await ensureUnit(page, 'kg')

  const names = await getExerciseNamesFromApi(detail.date)
  const nonBarbellIndex = names.findIndex((name) => name === detail.nonBarbell)
  const barbellIndex = names.findIndex((name) => name === detail.barbell)
  if (nonBarbellIndex < 0 || barbellIndex < 0) {
    throw new Error(`Cannot find expected exercises for toolkit test: ${names.join(' | ')}`)
  }

  await page.getByTestId(`exercise-toolkit-${barbellIndex}`).click()
  await expect(control(page, 'toolkit-bar-weight').input).toHaveValue('20')
  await fillControl(page, 'toolkit-target-weight', 100)
  await expect(page.getByTestId('toolkit-grand-total')).toHaveText('100 kg', { timeout: 10000 })
  await page.keyboard.press('Escape')

  await page.getByTestId(`exercise-toolkit-${nonBarbellIndex}`).click()
  await expect(control(page, 'toolkit-bar-weight').input).toHaveValue('0')
  await expect(page.getByText('Non-barbell exercise defaulted to 0.')).toBeVisible()
  await page.keyboard.press('Escape')

  await page.goto(`${frontendUrl}/tools/plate`, { waitUntil: 'networkidle' })
  await ensureUnit(page, 'kg')
  await fillControl(page, 'plate-target-weight', 100)
  await expect(page.getByTestId('plate-grand-total-kg')).toHaveText('100.0 kg', { timeout: 10000 })
  await expect(page.getByText('2x 20kg')).toBeVisible()
}

async function testSettingsDrawer(page, originalMeta) {
  const oppositeSex = (originalMeta.sex || 'male') === 'male' ? 'female' : 'male'
  const writeSex = oppositeSex === 'male' ? 'female' : 'male'
  const originalBlockStarts = clone(originalMeta.block_week_start_days || {})
  const stagedStarts = {
    ...originalBlockStarts,
    current: 'Tuesday',
    [historicalBlock]: 'Sunday',
  }

  await updateMeta('sex', oppositeSex)
  await updateMeta('program_week_start_day', 'Tuesday')
  await updateMeta('block_week_start_days', stagedStarts)

  await page.goto(frontendUrl, { waitUntil: 'networkidle' })
  await page.getByTestId('settings-button').click()
  await expect(page.getByText('Sex (for DOTS calculation)')).toBeVisible({ timeout: 15000 })

  await record('Settings drawer sex reflects program meta instead of stale local default', async () => {
    const checked = page.getByTestId('settings-sex').locator('input:checked')
    await expect(checked).toHaveValue(oppositeSex)
  })

  await page.getByTestId('settings-sex').getByText(oppositeSex === 'male' ? /^Male$/ : /^Female$/).click()
  await expect.poll(async () => (await loadProgram()).meta.sex).toBe(oppositeSex)
  await page.getByTestId('settings-sex').getByText(writeSex === 'male' ? /^Male$/ : /^Female$/).click()
  await expect.poll(async () => (await loadProgram()).meta.sex).toBe(writeSex)

  await record('Training week start select reflects current block meta', async () => {
    await expect(control(page, 'settings-week-start').input).toHaveValue('Tuesday')
  })

  await selectByLabel(page, 'settings-week-start', 'Wednesday')
  await expect.poll(async () => (await loadProgram()).meta.block_week_start_days?.current).toBe('Wednesday')
  const metaAfter = (await loadProgram()).meta
  if (metaAfter.block_week_start_days?.[historicalBlock] !== 'Sunday') {
    throw new Error(`Historical block week start was not preserved: ${JSON.stringify(metaAfter.block_week_start_days)}`)
  }
}

async function main() {
  await ensureBackendPortForward()
  await ensureFrontendServer()

  const status = (await request('/setup/status')).data
  if (status.mapped_pk !== 'test' || status.readOnly || !status.hasCurrentProgram) {
    throw new Error(`Test backend is not mapped to writable pk=test: ${JSON.stringify(status)}`)
  }

  const initialProgram = await loadProgram()
  const originalMeta = clone(initialProgram.meta)
  const addDeleteDate = freeDateInCurrentMonth(initialProgram.sessions)
  if (!addDeleteDate) {
    throw new Error('No free date remains in the current calendar month for the Add Session UI test')
  }
  const dates = {
    addDelete: addDeleteDate,
    detail: isoDateFromSeed(2),
    blockCurrent: isoDateFromSeed(3),
    blockOther: isoDateFromSeed(4),
  }
  Object.values(dates).forEach((date) => touchedDates.add(date))

  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1365, height: 900 } })
  const page = await context.newPage()
  const browserErrors = []
  const requestFailures = []
  const badResponses = []

  page.on('pageerror', (error) => browserErrors.push(error.message))
  page.on('console', (message) => {
    if (
      message.type() === 'error' &&
      !ignoredBrowserErrorFragments.some((fragment) => message.text().includes(fragment))
    ) {
      browserErrors.push(message.text())
    }
  })
  page.on('requestfailed', (request) => {
    requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`.trim())
  })
  page.on('response', (response) => {
    if (
      response.status() >= 400 &&
      !response.url().includes('/notes/draft') &&
      !(response.status() === 401 && response.url().includes('/api/settings'))
    ) {
      badResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`)
    }
  })

  try {
    await installApiRouting(page)
    const glossaryNames = await pickGlossaryExercises()

    await record('Add and delete sessions through the session list UI', () => testAddAndDeleteSession(page, dates.addDelete))
    await record('No-session state renders an explicit empty state', () => testEmptySessionsState(browser, initialProgram))
    await record('Switching blocks filters Compact and Agenda session lists', () => testBlockSwitching(page, dates.blockCurrent, dates.blockOther))

    let detail = null
    await record('Session detail supports exercise CRUD, notes, set editing, statuses, unit edits, save, reload, DynamoDB, and ordering', async () => {
      detail = await testSessionDetail(page, dates.detail, glossaryNames)
    })
    if (detail) {
      await record('AI notes helper sends full session context and returns a model draft', () => testAiNotes(page, detail))
      await record('Session toolkit and plate calculator use correct bar and plate math', () => testToolkitAndTools(page, detail))
    }
    await record('Settings drawer writes sex and week-start metadata without clobbering historical block grouping', () => testSettingsDrawer(page, originalMeta))

    if (browserErrors.length > 0) {
      throw new Error(`Browser errors seen during test:\n${browserErrors.join('\n')}`)
    }
    if (requestFailures.length > 0) {
      throw new Error(`Request failures seen during test:\n${requestFailures.join('\n')}`)
    }
    if (badResponses.length > 0) {
      throw new Error(`Unexpected bad responses seen during test:\n${badResponses.join('\n')}`)
    }
  } finally {
    await context.close()
    await browser.close()
    for (const date of touchedDates) {
      await deleteSessionIfExists(date).catch((error) => {
        console.error(`Cleanup failed for ${date}: ${error instanceof Error ? error.message : String(error)}`)
      })
    }
    for (const id of touchedExerciseIds) {
      await deleteExerciseIfExists(id).catch((error) => {
        console.error(`Cleanup failed for exercise ${id}: ${error instanceof Error ? error.message : String(error)}`)
      })
    }
    await updateMeta('sex', originalMeta.sex ?? 'male').catch((error) => {
      console.error(`Cleanup failed for meta.sex: ${error instanceof Error ? error.message : String(error)}`)
    })
    if (originalMeta.program_week_start_day !== undefined) {
      await updateMeta('program_week_start_day', originalMeta.program_week_start_day).catch((error) => {
        console.error(`Cleanup failed for meta.program_week_start_day: ${error instanceof Error ? error.message : String(error)}`)
      })
    }
    await updateMeta('block_week_start_days', originalMeta.block_week_start_days || {}).catch((error) => {
      console.error(`Cleanup failed for meta.block_week_start_days: ${error instanceof Error ? error.message : String(error)}`)
    })
    stopChildren()
  }

  if (failures > 0) {
    console.error(`\n[session-detail-ui-live] FAIL: ${failures} gap(s) found`)
    process.exit(1)
  }

  console.log('\n[session-detail-ui-live] PASS')
  console.log(`  Mode:     ${useDeployedFrontend ? 'deployed frontend service' : 'local Vite frontend'}`)
  console.log(`  Frontend: ${frontendUrl}`)
  console.log(`  API base: ${apiBase}`)
  console.log(`  DynamoDB: ${sessionsTableName} pk=${targetPk}`)
  console.log('  Checked:  session add/delete; empty state; block switching; detail editing; RPE bounds; exercise deletion/duplicates/order; set statuses/failure reasons; kg/lb persistence; AI notes context; toolkit/plate math; settings sex/week-start metadata')
}

main().then(() => {
  process.exit(0)
}).catch((error) => {
  stopChildren()
  console.error('[session-detail-ui-live] FAIL')
  console.error(error)
  process.exit(1)
})
