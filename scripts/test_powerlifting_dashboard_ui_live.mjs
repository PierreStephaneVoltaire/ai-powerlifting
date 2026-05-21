#!/usr/bin/env node
/**
 * Live browser regression test for dashboard edit controls.
 *
 * Defaults to the private if-portals-test pod services and writes only to
 * mapped_pk=test. It exercises the first-screen dashboard numeric inputs that
 * are easy to break with controlled input parsing: target maxes, body weight,
 * and anthropometrics. Touched meta is restored before exit.
 */

import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const appRoot = path.join(repoRoot, 'utils', 'powerlifting-app')
const requireFromApp = createRequire(path.join(appRoot, 'package.json'))
const { chromium, expect } = requireFromApp('@playwright/test')

const namespace = process.env.POWERLIFTING_TEST_NAMESPACE || 'if-portals-test'
const useLocalFrontend = process.env.POWERLIFTING_TEST_USE_LOCAL_FRONTEND === '1'
const useDeployedFrontend = !useLocalFrontend
const backendPort = Number(process.env.POWERLIFTING_TEST_BACKEND_PORT || (useDeployedFrontend ? 3005 : 13005))
const frontendPort = Number(process.env.POWERLIFTING_TEST_FRONTEND_PORT || 3001)
const backendOrigin = process.env.POWERLIFTING_TEST_BACKEND_ORIGIN || `http://127.0.0.1:${backendPort}`
const apiBase = (process.env.POWERLIFTING_TEST_API_BASE_URL || `${backendOrigin}/api`).replace(/\/$/, '')
const frontendUrl = (process.env.POWERLIFTING_TEST_FRONTEND_URL || `http://localhost:${frontendPort}`).replace(/\/$/, '')
const children = []
const ignoredBrowserErrorFragments = [
  "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a <meta> element.",
]

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

  throw new Error(`Timed out waiting for frontend port-forward: ${frontendUrl}`)
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

async function fulfillAuth(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user: { discord_id: 'dashboard-test', username: 'dashboard-test', avatar: null },
      mapped_pk: 'test',
      readOnly: false,
    }),
  })
}

async function fulfillSettings(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      data: {
        discord_id: 'dashboard-test',
        discord_username: 'dashboard-test',
        avatar_url: null,
        nickname: 'dashboard-test',
        profile_visibility: 'public',
        display_name: 'Dashboard Test',
        bio: 'Seeded profile settings for dashboard tests.',
        public_training_summary_enabled: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    }),
  })
}

async function installApiRouting(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (url.pathname === '/api/auth/me') {
      await fulfillAuth(route)
      return
    }
    if (url.pathname === '/api/settings') {
      await fulfillSettings(route)
      return
    }

    if (useLocalFrontend) {
      await route.continue()
      return
    }

    const proxiedPath = url.pathname.replace(/^\/api/, '') || '/'
    try {
      const response = await route.fetch({ url: `${apiBase}${proxiedPath}${url.search}` })
      await route.fulfill({ response })
    } catch {
      await route.abort('failed').catch(() => {})
    }
  })
}

function control(page, testId) {
  return page.locator([
    `[data-testid="${testId}"] input`,
    `input[data-testid="${testId}"]`,
    `[data-testid="${testId}"]`,
  ].join(', ')).first()
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

async function expectDashboardStillMounted(page, browserErrors) {
  await expect(page.getByTestId('dashboard-page')).toBeVisible({ timeout: 10000 })
  await expect(page.getByTestId('dashboard-page').getByText('Target Maxes', { exact: true })).toBeVisible()
  if (browserErrors.length > 0) {
    throw new Error(`Browser errors while editing dashboard:\n${browserErrors.join('\n')}`)
  }
}

function finiteOrZero(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

async function restoreDashboardMeta(meta) {
  await request('/maxes/current', {
    method: 'PUT',
    body: JSON.stringify({
      squat_kg: finiteOrZero(meta.target_squat_kg),
      bench_kg: finiteOrZero(meta.target_bench_kg),
      deadlift_kg: finiteOrZero(meta.target_dl_kg),
    }),
  })
  await request('/programs/current/body-weight', {
    method: 'PUT',
    body: JSON.stringify({ weightKg: finiteOrZero(meta.current_body_weight_kg) }),
  })
  for (const field of ['height_cm', 'arm_wingspan_cm', 'leg_length_cm']) {
    await request('/programs/current/meta', {
      method: 'PUT',
      body: JSON.stringify({
        field,
        value: Object.prototype.hasOwnProperty.call(meta, field) ? meta[field] ?? null : null,
      }),
    })
  }
}

async function editTargetMaxes(page, browserErrors) {
  await page.getByTestId('dashboard-edit-target-maxes').click()
  await expect(control(page, 'dashboard-target-squat')).toBeVisible()

  await control(page, 'dashboard-target-squat').fill('')
  await expectDashboardStillMounted(page, browserErrors)
  await page.getByTestId('dashboard-save-target-maxes').click()
  await expect(page.getByText('Enter valid target maxes before saving')).toBeVisible({ timeout: 5000 })
  await expectDashboardStillMounted(page, browserErrors)

  await control(page, 'dashboard-target-squat').fill('201.5')
  await control(page, 'dashboard-target-bench').fill('122.5')
  await control(page, 'dashboard-target-deadlift').fill('230')
  await Promise.all([
    page.waitForResponse((response) => (
      response.request().method() === 'PUT' &&
      response.url().includes('/api/maxes/current')
    ), { timeout: 20000 }),
    page.getByTestId('dashboard-save-target-maxes').click(),
  ])
  await expectDashboardStillMounted(page, browserErrors)
  await expect.poll(async () => (await loadProgram()).meta.target_squat_kg, { timeout: 15000 }).toBe(201.5)
  await expect.poll(async () => (await loadProgram()).meta.target_bench_kg, { timeout: 15000 }).toBe(122.5)
  await expect.poll(async () => (await loadProgram()).meta.target_dl_kg, { timeout: 15000 }).toBe(230)
}

async function editBodyWeight(page, browserErrors) {
  await page.getByTestId('dashboard-edit-body-weight').click()
  await expect(control(page, 'dashboard-body-weight')).toBeVisible()

  await control(page, 'dashboard-body-weight').fill('')
  await expectDashboardStillMounted(page, browserErrors)
  await page.getByTestId('dashboard-save-body-weight').click()
  await expect(page.getByText('Enter a valid body weight before saving')).toBeVisible({ timeout: 5000 })
  await expectDashboardStillMounted(page, browserErrors)

  await control(page, 'dashboard-body-weight').fill('93.4')
  await Promise.all([
    page.waitForResponse((response) => (
      response.request().method() === 'PUT' &&
      response.url().includes('/api/programs/current/body-weight')
    ), { timeout: 20000 }),
    page.getByTestId('dashboard-save-body-weight').click(),
  ])
  await expectDashboardStillMounted(page, browserErrors)
  await expect.poll(async () => (await loadProgram()).meta.current_body_weight_kg, { timeout: 15000 }).toBe(93.4)
}

async function editMeasurements(page, browserErrors) {
  await page.getByTestId('dashboard-edit-measurements').click()
  await expect(control(page, 'dashboard-height')).toBeVisible()

  await control(page, 'dashboard-height').fill('')
  await control(page, 'dashboard-wingspan').fill('181.5')
  await control(page, 'dashboard-leg-length').fill('95')
  await expectDashboardStillMounted(page, browserErrors)

  await Promise.all([
    page.waitForResponse((response) => (
      response.request().method() === 'PUT' &&
      response.url().includes('/api/programs/current/meta')
    ), { timeout: 20000 }),
    page.getByTestId('dashboard-save-measurements').click(),
  ])
  await expectDashboardStillMounted(page, browserErrors)
  await expect.poll(async () => (await loadProgram()).meta.height_cm ?? null, { timeout: 15000 }).toBe(null)
  await expect.poll(async () => (await loadProgram()).meta.arm_wingspan_cm, { timeout: 15000 }).toBe(181.5)
  await expect.poll(async () => (await loadProgram()).meta.leg_length_cm, { timeout: 15000 }).toBe(95)
}

async function main() {
  await ensureBackendPortForward()
  await ensureFrontendServer()

  const status = (await request('/setup/status')).data
  if (status.mapped_pk !== 'test' || status.readOnly || !status.hasCurrentProgram) {
    throw new Error(`Test backend is not mapped to writable pk=test: ${JSON.stringify(status)}`)
  }

  const originalProgram = await loadProgram()
  const originalMeta = JSON.parse(JSON.stringify(originalProgram.meta))

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
    if (request.failure()?.errorText === 'net::ERR_ABORTED') return
    requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`.trim())
  })
  page.on('response', (response) => {
    if (response.status() >= 400) {
      badResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`)
    }
  })

  try {
    await installApiRouting(page)
    await page.goto(frontendUrl, { waitUntil: 'networkidle' })
    await ensureUnit(page, 'kg')
    await expectDashboardStillMounted(page, browserErrors)

    await editTargetMaxes(page, browserErrors)
    await editBodyWeight(page, browserErrors)
    await editMeasurements(page, browserErrors)

    if (requestFailures.length || badResponses.length) {
      throw new Error([
        requestFailures.length ? `Request failures:\n${requestFailures.join('\n')}` : '',
        badResponses.length ? `Bad responses:\n${badResponses.join('\n')}` : '',
      ].filter(Boolean).join('\n\n'))
    }
  } finally {
    await context.close()
    await browser.close()
    await restoreDashboardMeta(originalMeta).catch((error) => {
      console.error(`Cleanup failed for dashboard meta: ${error instanceof Error ? error.message : String(error)}`)
    })
    stopChildren()
  }

  console.log('[dashboard-ui-live] PASS')
  console.log(`  Mode:     ${useDeployedFrontend ? 'deployed frontend service' : 'local Vite frontend'}`)
  console.log(`  Frontend: ${frontendUrl}`)
  console.log(`  API base: ${apiBase}`)
  console.log('  Checked:  dashboard target max, body weight, and anthropometric inputs handle empty/intermediate edits without crashing; saves persist and cleanup restores test meta')
}

main().then(() => {
  process.exit(0)
}).catch((error) => {
  stopChildren()
  console.error('[dashboard-ui-live] FAIL')
  console.error(error)
  process.exit(1)
})
