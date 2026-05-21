#!/usr/bin/env node
/**
 * Live browser regression test for powerlifting navigation.
 *
 * Defaults to the private if-portals-test pod services. It verifies the
 * parent-level desktop nav, mobile bottom nav, and hub-card links against the
 * deployed frontend/backend services. Local Vite is available only by explicit
 * opt-in with POWERLIFTING_TEST_USE_LOCAL_FRONTEND=1.
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

async function fulfillAuth(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user: { discord_id: 'test', username: 'test', avatar: null },
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
        discord_id: 'test',
        discord_username: 'test',
        avatar_url: null,
        nickname: 'test',
        profile_visibility: 'public',
        display_name: 'Powerlifting Test',
        bio: 'Seeded profile settings for navigation tests.',
        public_training_summary_enabled: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
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
    if (url.pathname === '/api/settings') {
      await fulfillSettings(route)
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

async function expectCardLinks(page, labels) {
  for (const label of labels) {
    await expect(page.getByText(label, { exact: true })).toBeVisible({ timeout: 15000 })
  }
}

async function verifyDesktop(page) {
  await page.setViewportSize({ width: 1365, height: 900 })
  await page.goto(frontendUrl, { waitUntil: 'networkidle' })

  const desktopLabels = ['Dashboard', 'Sessions', 'Designer', 'Analysis', 'Log', 'Tools', 'Profile', 'About']
  for (const label of desktopLabels) {
    await expect(page.getByTestId(`desktop-nav-${label.toLowerCase()}`)).toBeVisible()
  }
  await expect(page.getByTestId('desktop-nav-dashboard')).toHaveText(/Dashboard/)
  await expect(page.locator('nav').getByText('Charts', { exact: true })).toHaveCount(0)

  await page.getByTestId('desktop-nav-designer').click()
  await expect(page).toHaveURL(/\/designer$/)
  await expectCardLinks(page, ['Phase Design', 'Session Design', 'Templates', 'Import', 'Glossary', 'Competitions', 'Goals', 'Federations'])

  await page.getByTestId('desktop-nav-analysis').click()
  await expect(page).toHaveURL(/\/analysis$/)
  await expect(page.getByTestId('analysis-hub')).toBeVisible()
  await expectCardLinks(page, ['Weekly', 'Past Blocks', 'Lifetime Compare', 'Maxes'])
  await page.getByTestId('analysis-link-weekly').click()
  await expect(page).toHaveURL(/\/analysis\?type=weekly/)
  await expect(page.getByRole('heading', { name: 'Weekly Analysis' })).toBeVisible({ timeout: 15000 })
  await page.goto(`${frontendUrl}/analysis?type=maxes`, { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: 'Maxes' })).toBeVisible({ timeout: 15000 })

  await page.getByTestId('desktop-nav-log').click()
  await expect(page).toHaveURL(/\/log$/)
  await expect(page.getByTestId('log-page')).toBeVisible()
  await expectCardLinks(page, ['Notes', 'Supplements', 'Biometrics'])
  await page.getByTestId('log-link-notes').click()
  await expect(page.getByRole('heading', { name: 'Notes' })).toBeVisible({ timeout: 15000 })

  await page.getByTestId('desktop-nav-tools').click()
  await expect(page).toHaveURL(/\/tools$/)
  await expectCardLinks(page, ['Plate Calc', 'DOTS', 'Weight Tracker', '% of Max', 'Unit Converter', 'Attempt Selector', 'Rankings'])

  await page.getByTestId('desktop-nav-profile').click()
  await expect(page).toHaveURL(/\/profile$/)
  await expect(page.getByTestId('profile-page')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Profile' })).toBeVisible()

  await page.getByTestId('desktop-nav-about').click()
  await expect(page).toHaveURL(/\/about$/)
  await expect(page.getByRole('heading', { name: 'About the Peaking Portal' })).toBeVisible()
}

async function verifyMobile(page) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(frontendUrl, { waitUntil: 'networkidle' })

  const footer = page.locator('footer')
  await expect(footer.getByTestId('mobile-nav-dashboard')).toBeVisible()
  await expect(footer.getByTestId('mobile-nav-sessions')).toBeVisible()
  await expect(footer.getByTestId('mobile-nav-analysis')).toBeVisible()
  await expect(footer.getByTestId('mobile-nav-log')).toBeVisible()
  await expect(footer.getByTestId('mobile-nav-more')).toBeVisible()
  await expect(footer.getByText('Designer', { exact: true })).toHaveCount(0)
  await expect(footer.getByText('Tools', { exact: true })).toHaveCount(0)

  await footer.getByTestId('mobile-nav-analysis').click()
  await expect(page).toHaveURL(/\/analysis$/)
  await expect(page.getByTestId('analysis-hub')).toBeVisible()

  await footer.getByTestId('mobile-nav-log').click()
  await expect(page).toHaveURL(/\/log$/)
  await expect(page.getByTestId('log-page')).toBeVisible()

  await footer.getByTestId('mobile-nav-more').click()
  await expect(page.getByRole('menuitem', { name: 'Designer' })).toBeVisible()
  await expect(page.getByRole('menuitem', { name: 'Tools' })).toBeVisible()
  await expect(page.getByRole('menuitem', { name: 'Profile' })).toBeVisible()
  await expect(page.getByRole('menuitem', { name: 'About' })).toBeVisible()
  await page.getByRole('menuitem', { name: 'Tools' }).click()
  await expect(page).toHaveURL(/\/tools$/)
}

async function main() {
  await ensureBackendPortForward()
  await ensureFrontendServer()

  const status = (await request('/setup/status')).data
  if (status.mapped_pk !== 'test' || status.readOnly || !status.hasCurrentProgram) {
    throw new Error(`Test backend is not mapped to writable pk=test: ${JSON.stringify(status)}`)
  }

  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext()
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
    await verifyDesktop(page)
    await verifyMobile(page)

    if (browserErrors.length || requestFailures.length || badResponses.length) {
      throw new Error([
        browserErrors.length ? `Browser errors:\n${browserErrors.join('\n')}` : '',
        requestFailures.length ? `Request failures:\n${requestFailures.join('\n')}` : '',
        badResponses.length ? `Bad responses:\n${badResponses.join('\n')}` : '',
      ].filter(Boolean).join('\n\n'))
    }

    console.log('[navigation-ui-live] PASS')
    console.log(`  Mode:     ${useDeployedFrontend ? 'deployed frontend service' : 'local Vite frontend'}`)
    console.log(`  Frontend: ${frontendUrl}`)
    console.log(`  API base: ${apiBase}`)
    console.log('  Checked:  desktop parent nav; Designer/Analysis/Log/Tools/Profile hubs; Analysis Maxes tab; mobile Dashboard/Sessions/Analysis/Log/More bottom nav')
  } finally {
    await browser.close()
    stopChildren()
  }
}

main().then(() => {
  process.exit(0)
}).catch((error) => {
  stopChildren()
  console.error('[navigation-ui-live] FAIL')
  console.error(error)
  process.exit(1)
})
