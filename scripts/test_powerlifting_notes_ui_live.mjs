#!/usr/bin/env node
/**
 * Live regression test for dated program notes.
 *
 * Defaults to the private if-portals-test pod services. It seeds pk=test with
 * multiple dated notes through the deployed backend, verifies DynamoDB storage,
 * exercises the deployed frontend in Chromium, verifies reload persistence, and
 * restores the original notes before exit.
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
const { DynamoDBDocumentClient, GetCommand } = requireFromApp('@aws-sdk/lib-dynamodb')

const namespace = process.env.POWERLIFTING_TEST_NAMESPACE || 'if-portals-test'
const useLocalFrontend = process.env.POWERLIFTING_TEST_USE_LOCAL_FRONTEND === '1'
const backendPort = Number(process.env.POWERLIFTING_TEST_BACKEND_PORT || (useLocalFrontend ? 13005 : 3005))
const frontendPort = Number(process.env.POWERLIFTING_TEST_FRONTEND_PORT || 3001)
const backendOrigin = process.env.POWERLIFTING_TEST_BACKEND_ORIGIN || `http://127.0.0.1:${backendPort}`
const apiBase = (process.env.POWERLIFTING_TEST_API_BASE_URL || `${backendOrigin}/api`).replace(/\/$/, '')
const frontendUrl = (process.env.POWERLIFTING_TEST_FRONTEND_URL || `http://localhost:${frontendPort}`).replace(/\/$/, '')
const awsRegion = process.env.AWS_REGION || 'ca-central-1'
const healthTableName = process.env.IF_HEALTH_TABLE_NAME || 'if-health'
const targetPk = process.env.POWERLIFTING_TEST_MAPPED_PK || 'test'
const runId = `notes-live-${Date.now()}`
const dynamo = DynamoDBDocumentClient.from(new DynamoDBClient({ region: awsRegion }))
const children = []
const ignoredBrowserErrorFragments = [
  "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a <meta> element.",
]

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function isoDaysAgo(daysAgo) {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
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
      throw new Error(`kubectl backend port-forward exited early: ${stderr.trim()}`)
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
  if (useLocalFrontend) {
    await ensureLocalFrontendServer()
    return
  }
  await ensureDeployedFrontendPortForward()
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

async function putBlockNotes(blockNotes) {
  await request('/block-notes/current', {
    method: 'PUT',
    body: JSON.stringify({ blockNotes }),
  })
}

async function getBlockNotes() {
  return (await request('/block-notes/current')).data || []
}

async function getCurrentProgramItem() {
  const pointer = await dynamo.send(new GetCommand({
    TableName: healthTableName,
    Key: { pk: targetPk, sk: 'program#current' },
    ConsistentRead: true,
  }))
  const refSk = pointer.Item?.ref_sk
  if (!refSk) {
    throw new Error(`Current program pointer missing in ${healthTableName} for pk=${targetPk}`)
  }

  const program = await dynamo.send(new GetCommand({
    TableName: healthTableName,
    Key: { pk: targetPk, sk: String(refSk) },
    ConsistentRead: true,
  }))
  if (!program.Item) {
    throw new Error(`Current program item missing in ${healthTableName}: pk=${targetPk} sk=${refSk}`)
  }
  return program.Item
}

async function expectDynamoNotes(expectedNotes, label) {
  let item = null
  for (let attempt = 0; attempt < 20; attempt += 1) {
    item = await getCurrentProgramItem()
    const actual = item.meta?.block_notes
    if (
      Array.isArray(actual) &&
      actual.length === expectedNotes.length &&
      expectedNotes.every((note) => actual.some((actualNote) => (
        actualNote.date === note.date && actualNote.notes === note.notes
      )))
    ) {
      if (Object.prototype.hasOwnProperty.call(item, 'block_notes')) {
        throw new Error(`${label}: top-level block_notes should have been removed after save`)
      }
      return
    }
    await sleep(250)
  }
  throw new Error(`${label}: DynamoDB notes did not match. Expected ${JSON.stringify(expectedNotes)}, got ${JSON.stringify(item?.meta?.block_notes)}`)
}

async function currentBlockFingerprint() {
  const blocks = (await request('/analytics/blocks')).data || []
  const current = blocks.find((block) => block.blockKey === 'current' || block.isCurrent)
  if (!current?.sourceFingerprint) {
    throw new Error(`Current block sourceFingerprint missing: ${JSON.stringify(blocks)}`)
  }
  return current.sourceFingerprint
}

async function fulfillAuth(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user: { discord_id: 'test-notes', username: 'test-notes', avatar: null },
      mapped_pk: 'test',
      readOnly: false,
    }),
  })
}

async function installApiRouting(page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    if (url.pathname === '/api/auth/me') {
      await fulfillAuth(route)
      return
    }

    if (useLocalFrontend) {
      await route.continue()
      return
    }

    const proxiedPath = url.pathname.replace(/^\/api/, '') || '/'
    const response = await route.fetch({ url: `${apiBase}${proxiedPath}${url.search}` })
    await route.fulfill({ response })
  })
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

async function main() {
  await ensureBackendPortForward()
  await ensureFrontendServer()

  const status = (await request('/setup/status')).data
  if (status.mapped_pk !== 'test' || status.readOnly || !status.hasCurrentProgram) {
    throw new Error(`Test backend is not mapped to writable pk=test: ${JSON.stringify(status)}`)
  }

  const originalNotes = clone(await getBlockNotes())
  const beforeFingerprint = await currentBlockFingerprint()
  const seededNotes = [
    {
      date: isoDaysAgo(2),
      notes: `${runId} older context: low back fatigue was elevated.`,
      updated_at: new Date().toISOString(),
    },
    {
      date: isoDaysAgo(1),
      notes: `${runId} newer context: fatigue resolved and normal pulling resumed.`,
      updated_at: new Date().toISOString(),
    },
  ]

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
    await putBlockNotes(seededNotes)
    await expectDynamoNotes(seededNotes, 'Seeded dated notes')
    const seededFingerprint = await currentBlockFingerprint()
    if (seededFingerprint === beforeFingerprint) {
      throw new Error('Current block sourceFingerprint did not change after dated notes changed')
    }

    await installApiRouting(page)
    await page.goto(`${frontendUrl}/notes`, { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'Notes' })).toBeVisible({ timeout: 15000 })
    await expect(page.getByTestId('program-note-card')).toHaveCount(2)

    await expect(page.getByTestId('program-note-card').nth(0)).toContainText(seededNotes[1].notes)
    await expect(page.getByTestId('program-note-card').nth(1)).toContainText(seededNotes[0].notes)

    const editedLatest = `${seededNotes[1].notes}\n${runId} browser edit persisted.`
    await page.getByTestId('program-note-card').nth(0).click()
    await expect(page.getByTestId('program-note-text')).toHaveValue(seededNotes[1].notes)
    await page.getByTestId('program-note-text').fill(editedLatest)
    await expect(page.getByTestId('program-note-edit-save')).toBeEnabled()
    const editRequest = page.waitForRequest((req) => req.method() === 'PUT' && req.url().includes('/api/block-notes/current'))
    await page.getByTestId('program-note-edit-save').click()
    await editRequest
    await expect(page.getByTestId('program-note-edit-save')).toHaveCount(0, { timeout: 10000 })

    const editedNotes = [
      seededNotes[0],
      { ...seededNotes[1], notes: editedLatest },
    ]
    await expectDynamoNotes(editedNotes, 'Edited dated note')
    const editedFingerprint = await currentBlockFingerprint()
    if (editedFingerprint === seededFingerprint) {
      throw new Error('Current block sourceFingerprint did not change after browser note edit')
    }

    await page.reload({ waitUntil: 'networkidle' })
    await expect(page.getByTestId('program-note-card')).toHaveCount(2)
    await expect(page.getByTestId('program-note-card').nth(0)).toContainText(editedLatest)

    const newNoteText = `${runId} additional dated note created from deployed UI.`
    await page.getByTestId('notes-new-text').fill(newNoteText)
    await expect(page.getByTestId('notes-new-save')).toBeEnabled()
    const addRequest = page.waitForRequest((req) => req.method() === 'PUT' && req.url().includes('/api/block-notes/current'))
    await page.getByTestId('notes-new-save').click()
    await addRequest
    await expect(page.getByTestId('notes-new-text')).toHaveValue('', { timeout: 10000 })

    const apiNotes = await getBlockNotes()
    if (apiNotes.length !== 3 || !apiNotes.some((note) => note.notes === newNoteText)) {
      throw new Error(`Saved additional dated note not returned by API: ${JSON.stringify(apiNotes)}`)
    }

    await page.reload({ waitUntil: 'networkidle' })
    await expect(page.getByTestId('program-note-card')).toHaveCount(3)
    await expect(page.getByTestId('program-note-card').nth(0)).toContainText(newNoteText)

    if (browserErrors.length || requestFailures.length || badResponses.length) {
      throw new Error([
        browserErrors.length ? `Browser errors:\n${browserErrors.join('\n')}` : '',
        requestFailures.length ? `Request failures:\n${requestFailures.join('\n')}` : '',
        badResponses.length ? `Bad responses:\n${badResponses.join('\n')}` : '',
      ].filter(Boolean).join('\n\n'))
    }

    console.log('[notes-ui-live] PASS')
    console.log(`  Mode:        ${useLocalFrontend ? 'local frontend opt-in' : 'deployed frontend service'}`)
    console.log(`  Frontend:    ${frontendUrl}`)
    console.log(`  API base:    ${apiBase}`)
    console.log(`  DynamoDB:    ${healthTableName} pk=${targetPk}`)
    console.log('  Checked:     multiple dated cards render newest-first; edit persists through API/DynamoDB/reload; add-entry persists; analysis source fingerprint changes when dated notes change')
  } finally {
    await browser.close()
    await putBlockNotes(originalNotes)
    await expectDynamoNotes(originalNotes, 'Restore original notes')
    stopChildren()
  }
}

main().then(() => {
  process.exit(0)
}).catch((error) => {
  stopChildren()
  console.error('[notes-ui-live] FAIL')
  console.error(error)
  process.exit(1)
})
