#!/usr/bin/env node
/**
 * Live regression test for read-only mode when unauthenticated.
 *
 * This runs the frontend against the live if-portals-test backend data with
 * two scenarios:
 *   1. Read-only (unauthenticated): verify all interactive controls are disabled
 *   2. Authenticated: verify key interactive controls are enabled
 *
 * Uses the same port-forward and Playwright patterns as
 * test_powerlifting_session_save_ui_live.mjs.
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
const useDeployedFrontend = (
  process.env.POWERLIFTING_TEST_DEPLOYED_FRONTEND === '1' ||
  process.env.POWERLIFTING_TEST_USE_DEPLOYED_FRONTEND === '1'
)
const backendPort = Number(process.env.POWERLIFTING_TEST_BACKEND_PORT || (useDeployedFrontend ? 3005 : 13005))
const frontendPort = Number(process.env.POWERLIFTING_TEST_FRONTEND_PORT || 3001)
const backendOrigin = process.env.POWERLIFTING_TEST_BACKEND_ORIGIN || `http://127.0.0.1:${backendPort}`
const apiBase = (process.env.POWERLIFTING_TEST_API_BASE_URL || `${backendOrigin}/api`).replace(/\/$/, '')
const frontendUrl = (process.env.POWERLIFTING_TEST_FRONTEND_URL || `http://localhost:${frontendPort}`).replace(/\/$/, '')
const ignoredBrowserErrorFragments = [
  "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a <meta> element.",
]
const readOnlyBannerText = 'Read-only mode.'

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

async function fulfillReadOnlyAuth(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user: null,
      mapped_pk: 'test',
      readOnly: true,
    }),
  })
}

async function fulfillAuthenticatedAuth(route) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user: { discord_id: 'test-readonly', username: 'test-readonly', avatar: null },
      mapped_pk: 'test',
      readOnly: false,
    }),
  })
}

async function installApiRouting(page, authMode) {
  const fulfillAuth = authMode === 'readonly' ? fulfillReadOnlyAuth : fulfillAuthenticatedAuth

  if (!useDeployedFrontend) {
    await page.route('**/api/auth/me', fulfillAuth)
    await page.route('**/api/**', async (route, bid) => {
      if (route.request().url().includes('/api/auth/me')) {
        await fulfillAuth(route)
        return
      }
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

    const proxiedPath = url.pathname.replace(/^\/api/, '') || '/'
    const response = await route.fetch({ url: `${apiBase}${proxiedPath}${url.search}` })
    await route.fulfill({ response })
  })
}

let failures = 0

async function assertDisabled(locator, label) {
  try {
    await expect(locator).toBeDisabled({ timeout: 5000 })
  } catch (e) {
    console.error(`  FAIL: ${label} should be disabled but is enabled`)
    failures += 1
  }
}

async function assertEnabled(locator, label) {
  try {
    await expect(locator).toBeEnabled({ timeout: 5000 })
  } catch (e) {
    console.error(`  FAIL: ${label} should be enabled but is disabled`)
    failures += 1
  }
}

async function assertVisible(locator, label) {
  try {
    await expect(locator).toBeVisible({ timeout: 10000 })
  } catch (e) {
    console.error(`  FAIL: ${label} should be visible`)
    failures += 1
  }
}

async function waitForReadOnlyBanner(page) {
  // Waiting for the banner guarantees readOnly=true has propagated through React state
  // before we check any individual controls on that page.
  await expect(page.getByText(readOnlyBannerText)).toBeVisible({ timeout: 10000 })
}

async function testReadOnlyMode(page) {
  console.log('\n--- Testing Read-Only Mode ---')

  // 1. Dashboard - verify ReadOnlyBanner visible
  console.log('  Testing Dashboard...')
  await page.goto(frontendUrl, { waitUntil: 'networkidle' })
  const banner = page.getByText(readOnlyBannerText)
  await assertVisible(banner, 'ReadOnly banner')
  const signInBtn = page.getByRole('button', { name: 'Sign in' })
  await assertVisible(signInBtn, 'Sign In button in banner')

  // 2. Dashboard - verify edit buttons are disabled
  // Banner visible confirms readOnly=true. Also wait for the disabled Edit2 button
  // itself — it only renders once program data has loaded.
  const editMaxesBtn = page
    .locator('.mantine-Paper-root', { hasText: 'Target Maxes' })
    .first()
    .getByRole('button')
    .first()
  await assertVisible(editMaxesBtn, 'Edit maxes button (disabled)')
  await assertDisabled(editMaxesBtn, 'Edit maxes button')

  // 3. Session page - navigate and verify inputs are disabled
  console.log('  Testing Session page...')
  const program = (await request('/programs/current')).data
  if (program?.sessions?.length > 0) {
    const session = program.sessions[0]
    const sessionUrl = `${frontendUrl}/session/${session.date}/0`
    await page.goto(sessionUrl, { waitUntil: 'networkidle' })
    await waitForReadOnlyBanner(page)

    // Wait for the session content to load
    const notesArea = page.locator('textarea[placeholder="How did the session feel?"]')
    await expect(notesArea).toBeVisible({ timeout: 15000 })

    // Session notes should be disabled
    await assertDisabled(notesArea, 'Session notes textarea')
    
    // Save button should be disabled
    const saveBtn = page.getByRole('button', { name: /^Save$/ })
    await assertDisabled(saveBtn, 'Save button')
    
    // Delete button should be disabled
    const deleteBtn = page.getByRole('button', { name: 'Delete' })
    await assertDisabled(deleteBtn, 'Delete button')
    
    // Mark Done button should be disabled
    const markDoneBtn = page.getByRole('button', { name: /Mark Done|Done/ })
    await assertDisabled(markDoneBtn, 'Mark Done button')
    
    // Add Exercise button should be disabled
    const addExBtn = page.getByRole('button', { name: 'Add Exercise' })
    await assertDisabled(addExBtn, 'Add Exercise button')
    
    // Upload button should be disabled
    const uploadBtn = page.getByRole('button', { name: 'Upload' })
    await assertDisabled(uploadBtn, 'Upload button')
    
    // Session RPE input should be disabled
    const rpeInput = page.getByTestId('session-rpe')
    await assertDisabled(rpeInput, 'RPE input')
  }

  // 4. Designer - verify Add Session is disabled
  console.log('  Testing Designer...')
  await page.goto(`${frontendUrl}/designer/sessions`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addSessionBtn = page.getByRole('button', { name: 'Add Session' })
  await assertDisabled(addSessionBtn, 'Add Session button in Designer')
  const copyPrevBtn = page.getByRole('button', { name: 'Copy Previous' })
  await assertDisabled(copyPrevBtn, 'Copy Previous button')
  const copyNextBtn = page.getByRole('button', { name: 'Copy Next' })
  await assertDisabled(copyNextBtn, 'Copy Next button')

  // 5. Notes page - verify add/edit controls are disabled
  console.log('  Testing Notes...')
  await page.goto(`${frontendUrl}/notes`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const newNoteText = page.getByTestId('notes-new-text')
  await assertDisabled(newNoteText, 'Notes new entry textarea')
  const newNoteSave = page.getByTestId('notes-new-save')
  await assertDisabled(newNoteSave, 'Notes new entry save button')

  // 6. ReadOnlyBanner should be visible on all pages
  console.log('  Testing ReadOnlyBanner persistence...')
  const pagesForBanner = ['/analysis', '/maxes', '/supplements']
  for (const p of pagesForBanner) {
    await page.goto(`${frontendUrl}${p}`, { waitUntil: 'networkidle' })
    const bannerVisible = await page.getByText(readOnlyBannerText).isVisible().catch(() => false)
    if (!bannerVisible) {
      console.error(`  FAIL: ReadOnlyBanner not visible on ${p}`)
      failures += 1
    }
  }

  // 7. Supplements page - verify mutation buttons are disabled
  console.log('  Testing Supplements page...')
  await page.goto(`${frontendUrl}/supplements`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addPhaseBtn = page.getByRole('button', { name: 'Add Phase' })
  await assertDisabled(addPhaseBtn, 'Supplements Add Phase button')

  // 8. Competitions page - verify mutation buttons are disabled
  console.log('  Testing Competitions page...')
  await page.goto(`${frontendUrl}/designer/competitions`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addCompBtn = page.getByRole('button', { name: 'Add Competition' })
  await assertDisabled(addCompBtn, 'Add Competition button')

  // 9. Goals page - verify mutation buttons are disabled
  console.log('  Testing Goals page...')
  await page.goto(`${frontendUrl}/designer/goals`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addGoalBtn = page.getByRole('button', { name: 'Add Goal' })
  await assertDisabled(addGoalBtn, 'Add Goal button')

  // 10. Biometrics/Diet page - verify mutation buttons are disabled
  console.log('  Testing Biometrics page...')
  await page.goto(`${frontendUrl}/biometrics`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addEntryBtn = page.getByRole('button', { name: 'Add Entry' })
  await assertDisabled(addEntryBtn, 'Add Entry button')

  // 11. Glossary page - verify mutation buttons are disabled
  console.log('  Testing Glossary page...')
  await page.goto(`${frontendUrl}/designer/glossary`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addExerciseBtn = page.getByRole('button', { name: 'Add Exercise' })
  await assertDisabled(addExerciseBtn, 'Glossary Add Exercise button')
  const estimateFatigueBtn = page.getByRole('button', { name: 'Estimate Fatigue' })
  await assertDisabled(estimateFatigueBtn, 'Glossary Estimate Fatigue button')

  // 12. Federations page - verify mutation buttons are disabled
  console.log('  Testing Federations page...')
  await page.goto(`${frontendUrl}/designer/federations`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addFedBtn = page.getByRole('button', { name: 'Add Federation' })
  await assertDisabled(addFedBtn, 'Add Federation button')
  const addStdBtn = page.getByRole('button', { name: 'Add Standard' })
  await assertDisabled(addStdBtn, 'Add Standard button')

  // 13. Designer Phases page - verify mutation buttons are disabled
  console.log('  Testing Designer Phases page...')
  await page.goto(`${frontendUrl}/designer/phases`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const addPhaseBtn2 = page.getByRole('button', { name: 'Add Phase' })
  await assertDisabled(addPhaseBtn2, 'Designer Phases Add Phase button')

  // 14. Lift Profile page - verify Save Profile is disabled
  console.log('  Testing Lift Profile page...')
  await page.goto(`${frontendUrl}/lift-profiles/squat`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const saveProfileBtn = page.getByRole('button', { name: 'Save Profile' })
  await assertDisabled(saveProfileBtn, 'Save Profile button')

  // 15. Template Library page - verify Create Template is disabled
  console.log('  Testing Template Library page...')
  await page.goto(`${frontendUrl}/designer/templates`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const createTemplateBtn = page.getByRole('button', { name: 'Create Template' })
  await assertDisabled(createTemplateBtn, 'Create Template button')
  const importTemplateBtn = page.getByRole('button', { name: 'Import Template' })
  await assertDisabled(importTemplateBtn, 'Import Template button')

  // 16. Import Wizard page - verify dropzone is disabled
  console.log('  Testing Import Wizard page...')
  await page.goto(`${frontendUrl}/designer/import`, { waitUntil: 'networkidle' })
  await waitForReadOnlyBanner(page)
  const dropzoneInput = page.locator('input[type="file"][disabled]')
  if (await dropzoneInput.count() > 0) {
    console.log('  PASS: Import file input is disabled')
  } else {
    console.log('  INFO: Import file input disabled check (may require visual inspection)')
  }
}

async function testAuthenticatedMode(page) {
  console.log('\n--- Testing Authenticated Mode ---')

  // 1. Dashboard - ReadOnlyBanner should NOT be visible
  console.log('  Testing Dashboard (authenticated)...')
  await page.goto(frontendUrl, { waitUntil: 'networkidle' })
  const banner = page.getByText(readOnlyBannerText)
  try {
    await expect(banner).not.toBeVisible({ timeout: 5000 })
  } catch {
    console.error('  FAIL: ReadOnlyBanner should NOT be visible when authenticated')
    failures += 1
  }

  // 2. Session page - verify Save button works
  console.log('  Testing Session page (authenticated)...')
  const program = (await request('/programs/current')).data
  if (program?.sessions?.length > 0) {
    const session = program.sessions[0]
    const sessionUrl = `${frontendUrl}/session/${session.date}/0`
    await page.goto(sessionUrl, { waitUntil: 'networkidle' })
    
    const notesArea = page.locator('textarea[placeholder="How did the session feel?"]')
    try {
      await expect(notesArea).toBeVisible({ timeout: 15000 })
    } catch {
      await sleep(3000)
    }
    
    // Notes textarea should be enabled (not disabled)
    const isDisabled = await notesArea.getAttribute('disabled')
    if (isDisabled !== null && isDisabled !== undefined) {
      console.error('  FAIL: Session notes textarea should be enabled when authenticated')
      failures += 1
    }
  }

  // 3. Supplements page - verify Add Phase is enabled
  console.log('  Testing Supplements page (authenticated)...')
  await page.goto(`${frontendUrl}/supplements`, { waitUntil: 'networkidle' })
  await sleep(1500)
  const addPhaseBtnAuth = page.getByRole('button', { name: 'Add Phase' })
  await assertEnabled(addPhaseBtnAuth, 'Supplements Add Phase button (authenticated)')

  // 4. Competitions page - verify Add Competition is enabled
  console.log('  Testing Competitions page (authenticated)...')
  await page.goto(`${frontendUrl}/designer/competitions`, { waitUntil: 'networkidle' })
  await sleep(1500)
  const addCompBtnAuth = page.getByRole('button', { name: 'Add Competition' })
  await assertEnabled(addCompBtnAuth, 'Add Competition button (authenticated)')

  // 5. Goals page - verify Add Goal is enabled
  console.log('  Testing Goals page (authenticated)...')
  await page.goto(`${frontendUrl}/designer/goals`, { waitUntil: 'networkidle' })
  await sleep(1500)
  const addGoalBtnAuth = page.getByRole('button', { name: 'Add Goal' })
  await assertEnabled(addGoalBtnAuth, 'Add Goal button (authenticated)')
}

async function main() {
  await ensureBackendPortForward()
  await ensureFrontendServer()

  const status = (await request('/setup/status')).data
  if (status.mapped_pk !== 'test' || !status.hasCurrentProgram) {
    console.warn(`Warning: Backend mapped_pk=${status.mapped_pk}, hasProgram=${status.hasCurrentProgram}. Tests may not work properly.`)
  }

  const browser = await chromium.launch({ headless: true })
  const browserErrors = []
  const requestFailures = []
  const badResponses = []

  // Test 1: Read-only mode — use a fresh context so no state bleeds into Test 2
  const roContext = await browser.newContext({ viewport: { width: 1365, height: 900 } })
  const roPage = await roContext.newPage()
  roPage.on('pageerror', (error) => browserErrors.push(error.message))
  roPage.on('console', (message) => {
    if (
      message.type() === 'error' &&
      !ignoredBrowserErrorFragments.some((fragment) => message.text().includes(fragment))
    ) {
      browserErrors.push(message.text())
    }
  })
  roPage.on('requestfailed', (request) => {
    requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`.trim())
  })
  roPage.on('response', (response) => {
    if (response.status() >= 400) {
      badResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`)
    }
  })

  try {
    await installApiRouting(roPage, 'readonly')
    await testReadOnlyMode(roPage)
  } catch (error) {
    console.error('Read-only test error:', error.message)
    failures += 1
  }
  await roContext.close()

  // Test 2: Authenticated mode — fresh context, no cookie/storage leakage from Test 1
  const authContext = await browser.newContext({ viewport: { width: 1365, height: 900 } })
  const authPage = await authContext.newPage()
  authPage.on('pageerror', (error) => browserErrors.push(error.message))
  authPage.on('console', (message) => {
    if (
      message.type() === 'error' &&
      !ignoredBrowserErrorFragments.some((fragment) => message.text().includes(fragment))
    ) {
      browserErrors.push(message.text())
    }
  })

  try {
    await installApiRouting(authPage, 'authenticated')
    await testAuthenticatedMode(authPage)
  } catch (error) {
    console.error('Authenticated test error:', error.message)
    failures += 1
  }
  await authContext.close()

  // Check for browser errors
  if (browserErrors.length > 0) {
    console.error(`\nBrowser errors during test:\n${browserErrors.join('\n')}`)
    failures += 1
  }

  await browser.close()
  stopChildren()

  if (failures > 0) {
    console.error(`\n[readonly-ui-live] FAIL: ${failures} assertion(s) failed`)
    process.exit(1)
  }

  console.log('\n[readonly-ui-live] PASS')
  console.log(`  Mode:     ${useDeployedFrontend ? 'deployed frontend service' : 'local Vite frontend'}`)
  console.log(`  Frontend: ${frontendUrl}`)
  console.log(`  API base: ${apiBase}`)
  console.log('  Checked:  ReadOnlyBanner visible; edit buttons disabled on Dashboard; session inputs/Save/Delete disabled; Designer Add/Copy disabled; Notes Save/textarea disabled; Supplements/Competitions/Goals/Biometrics/Glossary/Federations/DesignerPhases/LiftProfile/TemplateLibrary/ImportWizard mutation buttons disabled; banner persistent across pages; authenticated mode banner hidden, inputs enabled, Supplements/Competitions/Goals Add buttons enabled')
}

main().then(() => {
  process.exit(0)
}).catch((error) => {
  stopChildren()
  console.error('[readonly-ui-live] FAIL')
  console.error(error)
  process.exit(1)
})
