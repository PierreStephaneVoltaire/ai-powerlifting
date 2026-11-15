import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium } from '@playwright/test'
import react from '@vitejs/plugin-react'
import {
  authData,
  analysisManifest,
  analysisSection,
  competition,
  coachAthlete,
  coachPerson,
  dashboardProgram,
  handlerAthlete,
  handlerPerson,
  profiles,
  relationship,
  rankingPercentile,
  settings,
} from './fixtures/social-ui.mjs'
import { ownAthlete } from './fixtures/backlog-ui.mjs'

const root = resolve(fileURLToPath(new URL('.', import.meta.url)), '..', 'frontend')
const server = await createServer({ root, appType: 'spa', configFile: false, logLevel: 'error', server: { host: '127.0.0.1', port: 0 }, plugins: [react({ fastRefresh: false })], resolve: { alias: { '@': resolve(root, 'src') } }, css: { postcss: { plugins: [] } } })
const passed = []
const check = (condition, name) => { assert.ok(condition, name); passed.push(name) }
const response = (data, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(data) })
const bodyOf = request => { try { return request.postDataJSON() } catch { return undefined } }

function state(overrides = {}) {
  return {
    actor: 'owner', selected: ownAthlete, requests: [], unhandled: [], browserErrors: [], expected: [], expectedConsoleResponses: 0,
    relationships: { sent: [], received: [], history: [] }, notifications: [], tags: [{ tag: 'powerlifting', status: 'approved', revision: 1 }], settings: settings(), publication: { domains: [], revision: 1 },
    fail: {}, delay: () => 0, ...overrides,
  }
}

function expectResponse(current, method, path, status, body) { current.expected.push({ method, path, status, body }) }
function consumeExpected(current, method, path, status) {
  const index = current.expected.findIndex(item => item.method === method && item.path === path && item.status === status)
  if (index < 0) return false
  current.expected.splice(index, 1)
  return true
}

function currentAuth(current, selected) {
  if (current.actor === 'multi') return authData('owner', selected || current.selected)
  return authData(current.actor, selected || current.selected)
}

function relationshipsFor(current) {
  return current.relationships
}

async function routeApi(route, current) {
  const request = route.request()
  const url = new URL(request.url())
  const path = url.pathname.replace(/^\/api/, '')
  const method = request.method()
  const body = bodyOf(request)
  const selected = request.headers()['x-selected-athlete-pk']
  const actorAtRequest = current.actor
  const selectedAtRequest = selected || current.selected
  current.requests.push({ method, path, body, selected })
  const delay = current.delay?.({ method, path, actor: actorAtRequest, selected: selectedAtRequest }) || 0
  if (delay) await new Promise(resolve => setTimeout(resolve, delay))
  const expected = current.expected.find(item => item.method === method && item.path === path && item.status >= 400)
  if (expected) return route.fulfill(response({ error: 'expected failure' }, expected.status))

  if (path === '/auth/me' && method === 'GET') {
    if (selected) current.selected = selected
    return route.fulfill(response(authData(actorAtRequest, selectedAtRequest)))
  }
  if (path === '/programs/current' && method === 'GET') return route.fulfill(response({ data: dashboardProgram(selected || ownAthlete) }))
  if (path === '/analytics/analysis/manifest' && method === 'GET') return route.fulfill(response({ data: analysisManifest(url.searchParams.get('asOfDate')) }))
  if (path === '/analytics/analysis/sections/queue' && method === 'POST') return route.fulfill(response({ data: { accepted: true, queued: [], sourceFingerprint: 'social-ui' } }, 202))
  if (path.startsWith('/analytics/analysis/sections/') && method === 'GET') return route.fulfill(response({ data: analysisSection(path.split('/').at(-1), url.searchParams.get('asOfDate')) }))
  if (path === '/stats/ranking_percentile' && method === 'GET') return route.fulfill(response(rankingPercentile))
  if (path === '/profiles/current' && method === 'GET') return route.fulfill(response({ data: { athlete_pk: ownAthlete, nickname: 'luna', display_name: 'Luna', profile_visibility: 'private', public_training_summary_enabled: false, is_self: true, tags: [], bio: '' } }))
  if (path === '/weight/current' && method === 'GET') return route.fulfill(response({ data: { entries: [] } }))
  if (path === '/exercises' && method === 'GET') return route.fulfill(response({ data: [] }))
  if (path === '/videos' && method === 'GET') return route.fulfill(response({ data: { videos: [], exercises: [] } }))
  if (path === '/stats/categories' && method === 'GET') return route.fulfill(response({ countries: ['CA'], country_regions: { CA: ['ON'] } }))
  if (path === '/federations' && method === 'GET') return route.fulfill(response({ data: [] }))
  if (path === '/competitions' && method === 'GET') return route.fulfill(response({ data: [competition] }))
  if (path === '/settings' && method === 'GET') return route.fulfill(response({ data: current.settings }))
  if (path === '/settings/publication' && method === 'GET') return route.fulfill(response({ data: current.publication }))
  if (path === '/settings/publication' && method === 'PUT') { current.publication = { domains: body.domains, revision: current.publication.revision + 1 }; return route.fulfill(response({ data: current.publication })) }
  if (path === '/settings/profile' && method === 'PUT') { current.settings = { ...current.settings, ...body }; return route.fulfill(response({ data: current.settings })) }
  if (path === '/settings/nickname' && method === 'PUT') return route.fulfill(response({ data: current.settings }))

  if (path === '/grants/requests' && method === 'GET') return route.fulfill(response({ data: relationshipsFor(current) }))
  if (path === '/grants/' && method === 'GET') return route.fulfill(response({ data: { active: [], inactive: [] } }))
  if (path === '/grants/notifications' && method === 'GET') return route.fulfill(response({ data: { notifications: current.notifications, total: current.notifications.length } }))
  if (path === '/grants/notifications/read' && method === 'POST') { current.notifications = current.notifications.map(item => body.notification_ids.includes(item.notification_id) ? { ...item, read_at: new Date().toISOString() } : item); return route.fulfill(response({ data: { marked: body.notification_ids.length } })) }
  if (path === '/grants/requests' && method === 'POST') {
    const id = `relationship-${current.requests.filter(item => item.path === '/grants/requests' && item.method === 'POST').length}`
    const created = relationship({ id, direction: current.actor === 'owner' ? 'athlete_to_delegate' : 'coach_to_athlete', type: body.relationship_type, recipient: body.recipient_person_pk, requester: current.actor === 'owner' ? 'person-luna' : current.actor === 'coach' ? coachPerson : handlerPerson, tied: body.tied_competition_ids || [] })
    current.relationships.sent = [...current.relationships.sent, created]
    return route.fulfill(response({ data: created }))
  }
  if (path === '/grants/requests/respond' && method === 'POST') {
    if (current.fail.respond409) return route.fulfill(response({ error: { code: 'relationship_changed', message: 'This request was already resolved; reload relationship history.' } }, 409))
    const item = [...current.relationships.received, ...current.relationships.sent, ...current.relationships.history].find(value => value.relationship_id === body.relationship_id)
    if (!item) return route.fulfill(response({ error: 'Relationship not found' }, 404))
    current.lastResponse = body
    const next = { ...item, state: body.action === 'approve' ? 'approved' : body.action === 'reject' ? 'rejected' : 'cancelled', active: body.action === 'approve' }
    if (body.action === 'approve') {
      next.permissions = body.permissions || item.permissions
      next.tied_competition_ids = body.tied_competition_ids || item.tied_competition_ids
      if (body.replace_current_relationship_id) {
        current.relationships.history = current.relationships.history.map(value => value.relationship_id === body.replace_current_relationship_id ? { ...value, active: false, state: 'replaced', replaced_by_relationship_id: item.relationship_id } : value)
      }
    }
    current.relationships.received = current.relationships.received.filter(value => value.relationship_id !== item.relationship_id)
    current.relationships.sent = current.relationships.sent.filter(value => value.relationship_id !== item.relationship_id)
    current.relationships.history = [...current.relationships.history.filter(value => value.relationship_id !== item.relationship_id), next]
    return route.fulfill(response({ data: next }))
  }
  if (path === '/grants/requests/revoke' && method === 'POST') return route.fulfill(response({ data: {} }))
  if (path === '/profiles/search' && method === 'GET') return route.fulfill(response({ data: { profiles: profiles.filter(item => `${item.display_name} ${item.nickname}`.toLowerCase().includes((url.searchParams.get('q') || '').toLowerCase())), next_cursor: null } }))
  if (path === '/profiles/tags' && method === 'GET') return route.fulfill(response({ data: current.tags.filter(item => url.searchParams.get('review') === 'true' || item.status === 'approved') }))
  if (path.startsWith('/settings/tags/') && method === 'POST') { const tag = decodeURIComponent(path.split('/')[3]); current.tags = current.tags.map(item => item.tag === tag ? { ...item, status: body.decision, revision: item.revision + 1 } : item); return route.fulfill(response({ data: current.tags })) }
  if (path === '/settings/tags' && method === 'POST') { current.tags = [...current.tags, { tag: body.tag, status: 'pending', revision: 1 }]; current.settings = { ...current.settings, tags: [...current.settings.tags, { tag: body.tag, approved: false, proposed_by: 'person-luna' }] }; return route.fulfill(response({ data: current.settings })) }

  current.unhandled.push({ method, path, query: url.search })
  return route.fulfill(response({ error: `Unhandled mock request: ${method} ${path}${url.search}` }, 500))
}

async function openScenario(current, path) {
  const context = await browser.newContext()
  const page = await context.newPage()
  page.on('pageerror', error => current.browserErrors.push(`pageerror: ${error.stack || error.message}`))
  page.on('console', message => { if (message.type() !== 'error') return; if (message.text().includes('Failed to load resource') && current.expectedConsoleResponses > 0) { current.expectedConsoleResponses -= 1; return }; current.browserErrors.push(`console: ${message.text()}`) })
  page.on('response', response => {
    if (response.status() < 400) return
    const request = response.request()
    const requestUrl = new URL(request.url())
    const requestPath = requestUrl.pathname.replace(/^\/api/, '')
    if (consumeExpected(current, request.method(), requestPath, response.status())) { current.expectedConsoleResponses += 1; return }
    current.browserErrors.push(`response: ${response.status()} ${request.url()}`)
  })
  await page.route('**/api/**', route => new URL(route.request().url()).pathname.startsWith('/api/') ? routeApi(route, current) : route.continue())
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}${path}`)
  return { context, page }
}

let browser
try {
  await server.listen()
  browser = await chromium.launch({ headless: true })
  const relationshipsState = state({ relationships: { sent: [], received: [relationship({ id: 'incoming-coach', direction: 'coach_to_athlete', recipient: 'person-luna', requester: coachPerson, tied: ['meet-1'] })], history: [relationship({ id: 'current-coach', state: 'approved', active: true, recipient: coachPerson, permissions: ['program:read'], tied: ['meet-1'] })] }, notifications: [{ notification_id: 'notification-1', kind: 'relationship_approved', payload: { message: 'A relationship changed.' }, read_at: null, created_at: '2026-09-02T00:00:00Z' }] })
  const inbox = await openScenario(relationshipsState, '/inbox')
  await inbox.page.getByText(coachPerson, { exact: true }).waitFor()
  await inbox.page.getByRole('combobox', { name: 'Authorized permissions' }).click()
  await inbox.page.getByRole('option', { name: 'program:read' }).click()
  await inbox.page.getByRole('combobox', { name: 'Tied competition entries' }).click()
  await inbox.page.getByRole('option', { name: /Toronto Open/ }).click()
  await inbox.page.getByRole('combobox', { name: 'Replace current relationship (Athlete confirmation)' }).click()
  await inbox.page.getByRole('option', { name: /person-coach/ }).click()
  await inbox.page.getByRole('button', { name: 'Approve' }).click()
  check(relationshipsState.lastResponse.permissions.includes('program:read') && relationshipsState.lastResponse.tied_competition_ids.includes('meet-1') && relationshipsState.lastResponse.replace_current_relationship_id === 'current-coach', 'Athlete approval sends selected permissions, tied entry, and replacement')
  await inbox.page.getByText('Notifications').waitFor()
  await inbox.page.getByRole('button', { name: 'Mark all read' }).click()
  await inbox.page.getByRole('tab', { name: 'History' }).click().catch(async () => inbox.page.getByText('History', { exact: true }).click())
  check(relationshipsState.relationships.history.some(item => item.relationship_id === 'current-coach' && !item.active && item.state === 'replaced') && relationshipsState.relationships.history.some(item => item.relationship_id === 'incoming-coach' && item.active), 'Replacement leaves one active relationship and historical replaced record')
  await inbox.context.close()

  const ownerGrant = state({ actor: 'owner' })
  const grant = await openScenario(ownerGrant, '/settings')
  await grant.page.getByText('Roster', { exact: true }).click()
  await grant.page.getByTestId('open-grant-modal').click()
  await grant.page.getByTestId('grant-grantee-input').fill('Coach')
  await grant.page.getByRole('combobox', { name: 'Verified profile' }).click()
  await grant.page.getByRole('option', { name: /Coach Casey/ }).click()
  await grant.page.getByRole('combobox', { name: 'Tied competition entries' }).click()
  await grant.page.getByRole('option', { name: /Toronto Open/ }).click()
  await grant.page.getByRole('button', { name: 'Send request' }).click()
  const created = ownerGrant.requests.find(item => item.path === '/grants/requests' && item.method === 'POST')
  check(created?.body.relationship_type === 'coach' && created.body.tied_competition_ids.includes('meet-1'), 'Athlete Coach request sends tied competition entry')
  await grant.page.getByTestId('open-grant-modal').click()
  await grant.page.getByTestId('grant-grantee-input').fill('Handler')
  await grant.page.getByRole('combobox', { name: 'Verified profile' }).click()
  await grant.page.getByRole('option', { name: /Handler Harper/ }).click()
  await grant.page.getByRole('combobox', { name: 'Grant type' }).click()
  await grant.page.getByRole('option', { name: /Handler/ }).click()
  await grant.page.getByRole('combobox', { name: 'Tied competition entries' }).click()
  await grant.page.getByRole('option', { name: /Toronto Open/ }).click()
  await grant.page.getByRole('button', { name: 'Send request' }).click()
  check(ownerGrant.requests.filter(item => item.path === '/grants/requests' && item.method === 'POST').length === 2, 'Athlete Handler request is sent through the same grants contract')
  await grant.context.close()

  const tags = state({ tags: [{ tag: 'powerlifting', status: 'approved', revision: 1 }, { tag: 'old-school', status: 'pending', revision: 1 }, { tag: 'unsafe', status: 'pending', revision: 1 }] })
  const profile = await openScenario(tags, '/settings')
  await profile.page.getByText('Profile tags').waitFor()
  await profile.page.getByRole('button', { name: 'Add profile tag' }).click()
  await profile.page.getByRole('combobox', { name: 'Choose or request a tag' }).fill('new-wave')
  await profile.page.getByRole('button', { name: 'Submit for approval' }).click()
  await profile.page.getByText('Submitted and pending approval: new-wave').waitFor()
  check(tags.tags.some(item => item.tag === 'new-wave' && item.status === 'pending'), 'Ordinary Athlete can request a normalized pending tag')
  await profile.page.getByRole('combobox', { name: 'Choose or request a tag' }).fill('')
  await profile.page.getByRole('combobox', { name: 'Choose or request a tag' }).click()
  await profile.page.getByRole('option', { name: 'powerlifting' }).waitFor()
  check(await profile.page.getByRole('option', { name: 'powerlifting' }).count() === 1 && await profile.page.getByRole('option', { name: 'new-wave' }).count() === 0, 'Ordinary Athlete tag selector exposes approved catalog entries only')
  await profile.context.close()

  tags.actor = 'operator'
  const review = await openScenario(tags, '/settings')
  await review.page.getByText('Catalog review').waitFor()
  await review.page.getByText('new-wave · pending').locator('..').getByRole('button', { name: 'Approve' }).click()
  await review.page.getByText('unsafe · pending').locator('..').getByRole('button', { name: 'Reject' }).click()
  check(tags.tags.find(item => item.tag === 'new-wave')?.status === 'approved' && tags.tags.find(item => item.tag === 'unsafe')?.status === 'rejected', 'Operator approval and rejection update the tag catalog')
  await review.context.close()
  tags.actor = 'owner'
  const refreshed = await openScenario(tags, '/settings')
  await refreshed.page.getByText('Profile tags').waitFor()
  await refreshed.page.getByRole('button', { name: 'Add profile tag' }).click()
  await refreshed.page.getByRole('combobox', { name: 'Choose or request a tag' }).click()
  await refreshed.page.getByRole('option', { name: 'new-wave' }).waitFor()
  check(await refreshed.page.getByRole('option', { name: 'new-wave' }).count() === 1 && await refreshed.page.getByRole('option', { name: 'unsafe' }).count() === 0, 'Reloaded ordinary Athlete sees approved tags only')
  await refreshed.context.close()

  const socialStates = [relationshipsState, ownerGrant, tags]
  check(socialStates.every(item => item.unhandled.length === 0 && item.browserErrors.length === 0 && item.expected.length === 0 && item.expectedConsoleResponses === 0), `Social scenarios have no unhandled mocks, unexpected errors, or unaccounted failures: ${JSON.stringify(socialStates.map(item => ({ unhandled: item.unhandled, browserErrors: item.browserErrors, expected: item.expected, expectedConsoleResponses: item.expectedConsoleResponses })))}`)
  console.log(JSON.stringify({ verification: 'local Chromium DOM with simulated API interception; no live API, deployment, or Authentik evidence', passed }, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
