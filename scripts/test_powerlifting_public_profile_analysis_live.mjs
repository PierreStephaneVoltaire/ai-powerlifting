#!/usr/bin/env node
/**
 * Live deployed-pod regression test for public read-only profile and analysis access.
 *
 * This intentionally uses the if-portals-test frontend/backend services through
 * kubectl port-forward. It does not start local Vite.
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
const backendPort = Number(process.env.POWERLIFTING_TEST_BACKEND_PORT || 3005)
const frontendPort = Number(process.env.POWERLIFTING_TEST_FRONTEND_PORT || 3001)
const backendOrigin = process.env.POWERLIFTING_TEST_BACKEND_ORIGIN || `http://127.0.0.1:${backendPort}`
const apiBase = (process.env.POWERLIFTING_TEST_API_BASE_URL || `${backendOrigin}/api`).replace(/\/$/, '')
const frontendUrl = (process.env.POWERLIFTING_TEST_FRONTEND_URL || `http://localhost:${frontendPort}`).replace(/\/$/, '')
const ignoredBrowserErrorFragments = [
  "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a <meta> element.",
]
const children = []

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

function spawnChild(command, args) {
  const child = spawn(command, args, { detached: true, stdio: ['ignore', 'pipe', 'pipe'] })
  children.push(child)
  return child
}

async function ensurePortForward(label, service, localPort, remotePort, healthUrl) {
  if (await canReach(healthUrl)) return

  const child = spawnChild('kubectl', [
    '-n',
    namespace,
    'port-forward',
    service,
    `${localPort}:${remotePort}`,
  ])

  let stderr = ''
  child.stderr.on('data', (chunk) => {
    stderr += String(chunk)
  })

  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (await canReach(healthUrl)) return
    if (child.exitCode !== null) {
      throw new Error(`${label} port-forward exited early: ${stderr.trim()}`)
    }
    await sleep(250)
  }

  throw new Error(`Timed out waiting for ${label} port-forward: ${healthUrl}`)
}

async function ensurePortForwards() {
  await ensurePortForward(
    'backend',
    'svc/powerlifting-app-backend',
    backendPort,
    3005,
    `${backendOrigin}/health`,
  )
  await ensurePortForward(
    'frontend',
    'svc/powerlifting-app-frontend',
    frontendPort,
    3001,
    frontendUrl,
  )
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

async function fetchRouteWithRetry(route, url) {
  let lastError
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await route.fetch({ url })
    } catch (error) {
      lastError = error
      const message = error instanceof Error ? error.message : String(error)
      if (!message.includes('socket hang up') && !message.includes('ECONNRESET')) {
        throw error
      }
      await sleep(250 * (attempt + 1))
    }
  }
  throw lastError
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

function assertVideosSorted(videos) {
  for (let index = 1; index < videos.length; index += 1) {
    const previous = `${videos[index - 1].session_date}T${videos[index - 1].video.uploaded_at}`
    const current = `${videos[index].session_date}T${videos[index].video.uploaded_at}`
    assert(previous >= current, `lift_videos are not newest-first at index ${index}`)
  }
}

async function installReadOnlyRouting(page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    if (url.pathname === '/api/auth/me') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ user: null, mapped_pk: 'test', readOnly: true }),
      })
      return
    }

    const proxiedPath = url.pathname.replace(/^\/api/, '') || '/'
    const response = await fetchRouteWithRetry(route, `${apiBase}${proxiedPath}${url.search}`)
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
  await ensurePortForwards()

  const status = (await request('/setup/status')).data
  assert(status.mapped_pk === 'test', `backend mapped_pk must be test, got ${status.mapped_pk}`)
  assert(status.hasCurrentProgram, 'test backend has no current program')

  const profile = (await request('/profiles/current')).data
  assert(profile.profile_visibility === 'public', 'test current profile must be public')
  assert(profile.display_name, 'current profile display_name is empty')
  assert(profile.summary?.total_kg > 0, 'current profile total is not populated')
  assert(profile.summary?.dots > 0, 'current profile DOTS is not populated')
  assertVideosSorted(profile.lift_videos ?? [])

  const queued = await request('/analytics/analysis/sections/queue', {
    method: 'POST',
    body: JSON.stringify({
      sections: ['overview', 'fatigue_readiness', 'peaking', 'workload', 'alerts'],
      window: 'current',
      force: true,
    }),
  })
  assert(queued.data?.accepted === true, 'deterministic analysis queue was not accepted')
  await request('/analytics/analysis/sections/overview?window=current')

  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1365, height: 900 } })
  const page = await context.newPage()
  const browserErrors = []
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
  page.on('response', (response) => {
    const url = response.url()
    if (
      response.status() >= 400 &&
      (
        url.includes('/api/profiles') ||
        url.includes('/api/analytics') ||
        url.includes('/api/programs/current')
      )
    ) {
      badResponses.push(`${response.status()} ${response.request().method()} ${url}`)
    }
  })

  await installReadOnlyRouting(page)

  await page.goto(frontendUrl, { waitUntil: 'networkidle' })
  const profileLink = page.getByTestId('dashboard-profile-link')
  await expect(profileLink).toBeVisible({ timeout: 15000 })
  await expect(profileLink).toHaveAttribute('href', '/profile')
  await expect(page.getByText('No bio yet.')).toHaveCount(0)
  const topRowChildren = await page.locator('.if-dashboard-row-top > *').count()
  assert(topRowChildren === 3, `dashboard top row should have 3 cards, found ${topRowChildren}`)

  await profileLink.click()
  await expect(page).toHaveURL(/\/profile$/)
  await expect(page.getByText('Read only')).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId('profile-save')).toHaveCount(0)
  await expect(page.getByText('No bio yet.')).toHaveCount(0)
  await expect(page.getByTestId('profile-metric-dots-value')).not.toHaveText('--')

  await page.goto(`${frontendUrl}/analysis`, { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: 'Analysis', exact: true })).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('Read-only mode.')).toBeVisible({ timeout: 15000 })

  await context.close()
  await browser.close()

  if (browserErrors.length) {
    throw new Error(`Browser console/page errors:\n${browserErrors.join('\n')}`)
  }
  if (badResponses.length) {
    throw new Error(`Unexpected API error responses:\n${badResponses.join('\n')}`)
  }

  console.log('[public-profile-analysis-live] PASS')
  console.log(`  Frontend: ${frontendUrl}`)
  console.log(`  API base: ${apiBase}`)
  console.log('  Checked: public current profile API, DOTS, video ordering, read-only dashboard profile link/layout, signed-out profile read-only view, analysis page access')
}

main().then(() => {
  stopChildren()
  process.exit(0)
}).catch((error) => {
  stopChildren()
  console.error('[public-profile-analysis-live] FAIL')
  console.error(error)
  process.exit(1)
})
