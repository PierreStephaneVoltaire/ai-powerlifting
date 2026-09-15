import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium } from '@playwright/test'
import react from '@vitejs/plugin-react'
import {
  federation,
  me,
  onboardingAthleteBasics,
  onboardingRole,
  otherAthlete,
  ownAthlete,
  program,
  relationships,
  settings,
} from './fixtures/backlog-ui.mjs'

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
let browser
const passed = []
const check = (condition, name) => {
  assert.ok(condition, name)
  passed.push(name)
}

function scenario(name) {
  return {
    name,
    onboarded: false,
    role: null,
    profile: null,
    basics: null,
    program: program(),
    requests: [],
    selectedAthletes: [],
    transition: null,
    unhandled: [],
    browserErrors: [],
  }
}

function response(data, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(data) }
}

function authData(state, selected) {
  if (state.name === 'coach-onboarding') {
    return me({ roles: state.role ? ['coach'] : [], activeRole: 'coach', onboarded: state.onboarded, access: ['settings:read', 'settings:write', 'profile:read', 'profile:write'] })
  }
  if (state.name === 'athlete-onboarding') {
    return me({ roles: ['athlete'], activeRole: 'athlete', onboarded: state.onboarded, access: ['settings:read', 'settings:write', 'profile:read', 'profile:write', 'program:read', 'program:write', 'sessions:read', 'sessions:write'] })
  }
  if (state.name === 'handler') {
    return me({ mapped: otherAthlete, own: ownAthlete, roles: ['handler'], activeRole: 'handler', access: ['settings:read', 'profile:read', 'program:read', 'sessions:read', 'competition:read'] })
  }
  if (selected === otherAthlete) {
    return me({ mapped: otherAthlete, own: ownAthlete, roles: ['athlete', 'coach'], activeRole: 'athlete', access: ['profile:read', 'program:read', 'sessions:read', 'settings:read'] })
  }
  return me({ roles: ['athlete', 'coach'], activeRole: 'athlete', access: ['profile:read', 'program:read', 'sessions:read', 'settings:read', 'program:write', 'sessions:write', 'templates:read', 'templates:write'] })
}

async function routeApi(route, state) {
  const request = route.request()
  const url = new URL(request.url())
  const path = url.pathname.replace(/^\/api/, '')
  const method = request.method()
  const selected = request.headers()['x-selected-athlete-pk']
  let body
  try { body = request.postDataJSON() } catch { body = undefined }
  state.requests.push({ method, path, selected, body })

  if (path === '/auth/me' && method === 'GET') return route.fulfill(response(authData(state, selected)))
  if (path === '/onboarding/status' && method === 'GET') {
    const data = state.name === 'coach-onboarding' && !state.role ? onboardingRole : state.name === 'athlete-onboarding' && !state.basics ? onboardingAthleteBasics : { ...onboardingRole, is_onboarded: state.onboarded, next_step: state.onboarded ? 'done' : 'profile' }
    return route.fulfill(response({ data }))
  }
  if (path === '/onboarding/role' && method === 'PUT') {
    state.role = body
    return route.fulfill(response({ data: settings({ roles: body.roles, basics: false }) }))
  }
  if (path === '/onboarding/profile' && method === 'PUT') {
    state.profile = body
    if (state.name === 'coach-onboarding') state.onboarded = true
    return route.fulfill(response({ data: settings({ roles: state.role?.roles ?? ['athlete'], displayName: body.display_name, basics: false }) }))
  }
  if (path === '/onboarding/athlete-basics' && method === 'PUT') {
    state.basics = body
    state.onboarded = true
    return route.fulfill(response({ data: settings({ roles: ['athlete'], basics: true }) }))
  }
  if (path === '/settings' && method === 'GET') return route.fulfill(response({ data: settings({ roles: state.role?.roles ?? ['athlete'], basics: state.name !== 'athlete-onboarding' }) }))
  if (path === '/federations' && method === 'GET') return route.fulfill(response({ data: federation }))
  if (path === '/grants/requests' && method === 'GET') return route.fulfill(response({ data: state.name === 'multi-role' ? relationships : { sent: [], received: [], history: [] } }))
  if (path === '/templates' && method === 'GET') return route.fulfill(response([]))
  if (path === '/programs/current' && method === 'GET') return route.fulfill(response({ data: state.program }))
  if (path === '/programs' && method === 'GET') return route.fulfill(response({ data: [] }))
  if (path === '/programs/current/blocks/transition' && method === 'POST') {
    state.transition = body
    state.program = program({ revision: 8, unfinished: false })
    return route.fulfill(response({ data: { action: body.action, block_id: body.block_id, next_block_id: 'block-next', revision: 8, program: state.program } }))
  }
  if (path === '/exercises' && method === 'GET') return route.fulfill(response({ data: [] }))
  if (path === '/videos' && method === 'GET') return route.fulfill(response({ data: { videos: [], exercises: [] } }))
  if (path === '/stats/countries' && method === 'GET') return route.fulfill(response({ data: { countries: [], country_regions: {} } }))
  if (path === '/stats/categories' && method === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ countries: [], country_regions: {} }) })
  if (path === '/profiles/current' && method === 'GET') return route.fulfill(response({ data: { athlete_pk: ownAthlete, nickname: 'luna', display_name: 'Luna', profile_visibility: 'private', public_training_summary_enabled: false, is_self: true, tags: [], bio: '' } }))
  state.unhandled.push({ method, path, query: url.search })
  return route.fulfill(response({ error: `Unhandled mock request: ${method} ${path}${url.search}` }, 500))
}

async function openScenario(state, path, configure, viewport) {
  const context = await browser.newContext(viewport ? { viewport } : undefined)
  if (state.name === 'handler') {
    await context.addInitScript(() => localStorage.setItem('pl-settings', JSON.stringify({ state: { unit: 'lb' }, version: 3 })))
  }
  const page = await context.newPage()
  page.on('pageerror', error => state.browserErrors.push(`pageerror: ${error.message}`))
  page.on('console', message => { if (message.type() === 'error') state.browserErrors.push(`console: ${message.text()}`) })
  page.on('response', response => { if (response.status() >= 400) state.browserErrors.push(`response: ${response.status()} ${response.url()}`) })
  await page.route('**/api/**', route => new URL(route.request().url()).pathname.startsWith('/api/') ? routeApi(route, state) : route.continue())
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}${path}`)
  try {
    await configure(page, state)
    check(state.unhandled.length === 0 && state.browserErrors.length === 0, `${state.name} has no unhandled mock requests or browser errors`)
  } finally {
    await context.close()
  }
}

try {
  await server.listen()
  browser = await chromium.launch({ headless: true })

  const coach = scenario('coach-onboarding')
  await openScenario(coach, '/onboarding', async page => {
    await page.getByRole('button', { name: /^Coach Support/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByLabel('Display name').fill('Coach Luna')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.waitForURL(/127\.0\.0\.1:\d+\/$/)
    await page.getByText('Athlete roster').waitFor()
    check(await page.getByText('Athlete roster').count() === 1, 'Coach-only onboarding reaches the coach roster')
    check(!await page.getByText('Athlete basics').count(), 'Coach-only onboarding has no athlete basics step')
  })

  const athlete = scenario('athlete-onboarding')
  await openScenario(athlete, '/onboarding', async page => {
    await page.getByRole('combobox', { name: 'Weight units' }).click()
    await page.getByRole('option', { name: 'Pounds' }).click()
    check(await page.getByText('Best-known current 1RMs (lb)').count() === 1, 'Athlete basics switches max display to pounds')
    await page.getByLabel('Female').check()
    await page.getByLabel('Country (ISO-2)').fill('CA')
    await page.getByLabel('Bodyweight (lb)').fill('165')
    await page.getByRole('textbox', { name: 'Squat' }).fill('300')
    await page.getByRole('textbox', { name: 'Bench' }).fill('200')
    await page.getByRole('textbox', { name: 'Deadlift' }).fill('400')
    await page.getByLabel('1RM reference date').fill('2026-09-10')
    await page.getByRole('checkbox', { name: 'Bench' }).check()
    await page.getByRole('button', { name: 'Finish onboarding' }).click()
    await page.waitForURL(/127\.0\.0\.1:\d+\/$/)
    const basics = athlete.requests.find(item => item.path === '/onboarding/athlete-basics')
    check(Boolean(basics), 'Athlete basics submits through the onboarding API')
    check(Math.abs(basics.body.bodyweight_kg - 74.843) < 0.02 && Math.abs(basics.body.training_maxes.bench_kg - 90.718) < 0.02, 'Athlete basics converts pounds to kilograms')
    check(basics.body.maxes_date === '2026-09-10' && basics.body.training_maxes_estimated.bench === true, 'Athlete basics preserves reference date and estimated lift flag')
  })

  const multi = scenario('multi-role')
  await openScenario(multi, '/sessions', async page => {
    await page.getByLabel('Active role').waitFor()
    check(await page.getByLabel('Active role').count() === 1 && await page.getByLabel('Selected Athlete').count() === 1, 'Multi-role context renders separate role and Athlete selectors')
    await page.getByLabel('Selected Athlete').click()
    await page.getByRole('option', { name: 'Coach Client' }).click()
    await page.getByText('athlete · Coach Client').waitFor()
    await page.reload()
    await page.getByText('athlete · Coach Client').waitFor()
    const selectedHeaders = multi.requests.filter(item => item.path === '/auth/me').map(item => item.selected).filter(Boolean)
    check(selectedHeaders.includes(otherAthlete), 'Selected Athlete is restored with a distinct request header')
    const selectedProgramHeaders = multi.requests.filter(item => item.path === '/programs/current').map(item => item.selected).filter(Boolean)
    check(selectedProgramHeaders.includes(otherAthlete), 'Selected Athlete header reaches a non-auth request')
    await page.getByRole('combobox', { name: 'Active role' }).click()
    await page.getByRole('option', { name: 'Coach' }).click()
    check(await page.getByText('Athlete roster').count() === 1, 'Multi-role active role switches independently of selected Athlete')
  })

  const handler = scenario('handler')
  await openScenario(handler, '/sessions?view=Compact', async page => {
    await page.getByText('Read-only mode.').waitFor()
    check(await page.getByText('Read-only mode.').count() === 1, 'Handler view announces read-only mode')
    check(await page.getByTestId('desktop-nav-designer').count() === 0, 'Handler navigation hides program designer')
    check(await page.getByTestId('session-list-add-session').isDisabled(), 'Handler cannot add a session')
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/session/2026-09-14?session=session-squat`)
    await page.getByTestId('session-detail').waitFor()
    check(await page.getByTestId('session-body-weight').isDisabled() && await page.getByText('lb', { exact: true }).count() > 0, 'Handler session editor is read-only and uses pounds')
  })

  for (const viewport of [{ width: 320, height: 568 }, { width: 375, height: 667 }]) {
    const mobileHandler = scenario('handler')
    await openScenario(mobileHandler, '/sessions?view=Compact', async page => {
      await page.getByText('Read-only mode.').waitFor()
      const change = page.getByRole('button', { name: 'Change', exact: true })
      await change.waitFor()
      check((await change.boundingBox())?.height >= 44, `Mobile ${viewport.width}px context Change control has a 44px target`)
      check(await page.locator('#athlete-context-controls').evaluate(element => getComputedStyle(element).display === 'none'), `Mobile ${viewport.width}px context controls start closed`)
      const heading = page.locator('main h1, main h2').first()
      check(await heading.isVisible(), `Mobile ${viewport.width}px Sessions heading is visible`)
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: `/tmp/nolift-mobile-final/context-${viewport.width}-closed.png` })
      await change.click()
      check(await page.locator('#athlete-context-controls').isVisible(), `Mobile ${viewport.width}px context controls expand`)
      check(await page.getByRole('button', { name: 'Close', exact: true }).isVisible(), `Mobile ${viewport.width}px context can close`)
      await page.screenshot({ path: `/tmp/nolift-mobile-final/context-${viewport.width}-expanded.png` })
    }, viewport)
  }

  const blocks = scenario('blocks')
  await openScenario(blocks, '/designer', async page => {
    await page.getByRole('button', { name: 'Complete and start next Block' }).click()
    await page.getByText('2 unfinished Sessions will stay in the archived Block with their current statuses.').waitFor()
    check(await page.getByText('2 unfinished Sessions will stay in the archived Block with their current statuses.').count() === 1, 'Block transition warns about unfinished Sessions')
    await page.getByLabel('Next Block name').fill('Peak')
    const transitionResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/programs/current/blocks/transition')
    await page.getByRole('button', { name: 'Start Block' }).click()
    await transitionResponse
    const transition = blocks.requests.find(item => item.path === '/programs/current/blocks/transition')
    check(Boolean(transition), 'Block transition uses the shared transition endpoint')
    check(transition.body.action === 'complete_and_start' && transition.body.block_id === 'block-current' && transition.body.name === 'Peak', 'Block transition sends the exact action, source Block id, and next Block name')
    check(transition.body.expected_revision === 7 && typeof transition.body.idempotency_key === 'string' && transition.body.idempotency_key.length > 10, 'Block transition sends CAS revision and idempotency key')
  })

  const sessionsState = scenario('sessions')
  await openScenario(sessionsState, '/session/2026-09-14', async page => {
    await page.getByText('Session not found').waitFor()
    check(await page.getByText('Session not found').count() === 1, 'Same-day route detects an ambiguous Session date')
    const choices = page.getByRole('button', { name: /Strength · [12]/ })
    await choices.nth(1).waitFor()
    check(await choices.count() === 2, 'Same-day route offers both Sessions')
    await choices.nth(1).click()
    await page.getByTestId('session-detail').waitFor()
    check(await page.getByTestId('session-detail').getByText('Bench Press').count() > 0, 'Same-day navigation opens the selected Session')
  })

  console.log(JSON.stringify({ verification: 'local browser with simulated API interception; no deployment or Authentik evidence', passed, uncovered: ['offline conflict dialog'] }, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
