#!/usr/bin/env node
/**
 * Browser-level live regression test for session save/autosave.
 *
 * This runs the frontend against the live if-portals-test backend data, edits
 * the session UI in Chromium, proves button state transitions, waits for
 * autosave, reloads the page, and verifies persistence. The edited session is
 * restored through the backend API before exit.
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
const useDeployedFrontend = (
  process.env.POWERLIFTING_TEST_DEPLOYED_FRONTEND === '1' ||
  process.env.POWERLIFTING_TEST_USE_DEPLOYED_FRONTEND === '1'
)
const backendPort = Number(process.env.POWERLIFTING_TEST_BACKEND_PORT || (useDeployedFrontend ? 3005 : 13005))
const frontendPort = Number(process.env.POWERLIFTING_TEST_FRONTEND_PORT || 3001)
const backendOrigin = process.env.POWERLIFTING_TEST_BACKEND_ORIGIN || `http://127.0.0.1:${backendPort}`
const apiBase = (process.env.POWERLIFTING_TEST_API_BASE_URL || `${backendOrigin}/api`).replace(/\/$/, '')
const frontendUrl = (process.env.POWERLIFTING_TEST_FRONTEND_URL || `http://localhost:${frontendPort}`).replace(/\/$/, '')
const awsRegion = process.env.AWS_REGION || 'ca-central-1'
const healthTableName = process.env.IF_HEALTH_TABLE_NAME || 'if-health'
const sessionsTableName = process.env.IF_SESSIONS_TABLE_NAME || 'if-sessions'
const targetPk = process.env.POWERLIFTING_TEST_MAPPED_PK || 'test'
const runId = `ui-session-save-${Date.now()}`
const ignoredBrowserErrorFragments = [
  "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a <meta> element.",
]
const dynamo = DynamoDBDocumentClient.from(new DynamoDBClient({ region: awsRegion }))

const children = []
let pendingPutGate = null

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
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

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

async function loadProgram() {
  return (await request('/programs/current')).data
}

async function putSession(date, index, session) {
  await request(`/sessions/current/${encodeURIComponent(date)}/${index}`, {
    method: 'PUT',
    body: JSON.stringify(session),
  })
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
    throw new Error(
      `DynamoDB session missing: table=${sessionsTableName} pk=${targetPk} program=${programSk} date=${date} id=${sessionId}`,
    )
  }
  return match
}

async function expectDynamoSessionNote(date, sessionId, expectedNote, label) {
  let lastItem = null
  for (let attempt = 0; attempt < 30; attempt += 1) {
    lastItem = await loadDynamoSession(date, sessionId)
    if ((lastItem.session_notes || '') === expectedNote) return
    await sleep(250)
  }
  throw new Error(
    `${label} did not persist to DynamoDB. Expected session_notes=${JSON.stringify(expectedNote)}, got ${JSON.stringify(lastItem?.session_notes || '')}; sk=${lastItem?.sk}`,
  )
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

function isSessionPut(request) {
  return request.method() === 'PUT' && request.url().includes('/api/sessions/current/')
}

async function delayIfArmedSessionPut(request) {
  if (!isSessionPut(request) || !pendingPutGate) return
  const gate = pendingPutGate
  pendingPutGate = null
  await gate.wait
}

async function fulfillAuth(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user: { discord_id: 'test-ui', username: 'test-ui', avatar: null },
      mapped_pk: 'test',
      readOnly: false,
    }),
  })
}

async function installApiRouting(page) {
  if (!useDeployedFrontend) {
    await page.route('**/api/auth/me', fulfillAuth)
    await page.route('**/api/sessions/current/**', async (route) => {
      await delayIfArmedSessionPut(route.request())
      await route.continue()
    })
    return
  }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname === '/api/auth/me') {
      await fulfillAuth(route)
      return
    }

    await delayIfArmedSessionPut(request)
    const proxiedPath = url.pathname.replace(/^\/api/, '') || '/'
    const response = await route.fetch({ url: `${apiBase}${proxiedPath}${url.search}` })
    await route.fulfill({ response })
  })
}

async function armNextPut(page) {
  let release
  const requestPromise = page.waitForRequest((request) => (
    isSessionPut(request)
  ), { timeout: 10000 })
  const wait = new Promise((resolve) => {
    release = resolve
  })
  pendingPutGate = { wait }

  return {
    started: requestPromise,
    release: () => release?.(),
  }
}

async function main() {
  await ensureBackendPortForward()
  await ensureFrontendServer()

  const status = (await request('/setup/status')).data
  if (status.mapped_pk !== 'test' || status.readOnly || !status.hasCurrentProgram) {
    throw new Error(`Test backend is not mapped to writable pk=test: ${JSON.stringify(status)}`)
  }

  const program = await loadProgram()
  const index = 0
  const original = clone(program.sessions[index])
  const date = original.date
  const sessionUrl = `${frontendUrl}/session/${date}/${index}`

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
    if (response.status() >= 400) {
      badResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`)
    }
  })

  try {
    await installApiRouting(page)

    await page.goto(sessionUrl, { waitUntil: 'networkidle' })
    const notes = page.locator('textarea[placeholder="How did the session feel?"]')
    const saveButton = page.getByRole('button', { name: /^Save$/ })
    try {
      await expect(notes).toBeVisible({ timeout: 15000 })
    } catch (error) {
      throw new Error([
        error.message,
        browserErrors.length ? `Browser errors:\n${browserErrors.join('\n')}` : '',
        requestFailures.length ? `Request failures:\n${requestFailures.join('\n')}` : '',
        badResponses.length ? `Bad responses:\n${badResponses.join('\n')}` : '',
        `Current URL: ${page.url()}`,
      ].filter(Boolean).join('\n\n'))
    }
    await expect(saveButton).toBeDisabled()

    const manualMarker = `${runId}-manual`
    await notes.fill(manualMarker)
    await expect(saveButton).toBeEnabled()
    const manualPut = await armNextPut(page)
    await saveButton.click()
    await manualPut.started
    await expect(saveButton).toBeDisabled()
    manualPut.release()
    await expect(saveButton).toBeDisabled({ timeout: 10000 })
    await expectDynamoSessionNote(date, original.id, manualMarker, 'Manual UI save')

    await page.reload({ waitUntil: 'networkidle' })
    await expect(notes).toHaveValue(manualMarker, { timeout: 15000 })
    await expect(saveButton).toBeDisabled()

    const autoMarker = `${runId}-autosave`
    const autoPut = await armNextPut(page)
    await notes.fill(autoMarker)
    await expect(saveButton).toBeEnabled()
    await autoPut.started
    await expect(saveButton).toBeDisabled()
    autoPut.release()
    await expect(saveButton).toBeDisabled({ timeout: 10000 })
    await expectDynamoSessionNote(date, original.id, autoMarker, 'Autosave')

    await page.reload({ waitUntil: 'networkidle' })
    await expect(notes).toHaveValue(autoMarker, { timeout: 15000 })
    await expect(saveButton).toBeDisabled()

    if (browserErrors.length > 0) {
      throw new Error(`Browser errors seen during test:\n${browserErrors.join('\n')}`)
    }

    console.log('[session-save-ui-live] PASS')
    console.log(`  Mode:     ${useDeployedFrontend ? 'deployed frontend service' : 'local Vite frontend'}`)
    console.log(`  Frontend: ${frontendUrl}`)
    console.log(`  API base: ${apiBase}`)
    console.log(`  DynamoDB: ${sessionsTableName} pk=${targetPk}`)
    console.log(`  Session:  ${date} index ${index}`)
    console.log('  Checked:  Save disabled with no changes; manual save disables while in flight and persists to DynamoDB plus reload; autosave fires without clicking, disables while in flight, and persists to DynamoDB plus reload')
  } finally {
    await browser.close()
    await putSession(date, index, original)
    await expectDynamoSessionNote(date, original.id, original.session_notes || '', 'Restore')
    stopChildren()
  }
}

main().then(() => {
  process.exit(0)
}).catch((error) => {
  stopChildren()
  console.error('[session-save-ui-live] FAIL')
  console.error(error)
  process.exit(1)
})
