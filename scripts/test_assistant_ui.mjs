import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../src/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const { createServer } = await import(new URL('../src/node_modules/vite/dist/node/index.js', import.meta.url))
const program = {
  meta: { current_block_id: 'active', blocks: [{ id: 'past', name: 'Past block', status: 'completed' }, { id: 'active', status: 'active' }] },
  sessions: [], phases: [],
  supplement_phases: [{ phase: 1, phase_name: 'Past protocol', block_id: 'past', items: [] }],
}
const phase = { phase: 5, phase_name: 'Off season', block_id: 'active', start_week: 1, end_week: 5, items: [{ name: 'Recorded item', dose: 'Recorded dose' }] }
const proposal = { id: 'proposal', operation: 'supplement_phases_update', summary: 'Create current phase', target_id: 'active', state: 'pending', destructive: false, diff: { phases: [phase] } }
const progress = { stage: 'Checking', text: 'First reasoning.\n' + 'Readable reasoning line.\n'.repeat(80), updated_at: new Date().toISOString() }
const turns = []
let job
const jobs = new Map()
let submitted = 0
let programReads = 0
const browserErrors = []
const source = `
import React from 'react'
import { createRoot } from 'react-dom/client'
import { MantineProvider } from '@mantine/core'
import { MemoryRouter } from 'react-router-dom'
import '@mantine/core/styles.css'
import { AuthProvider } from '/src/auth/AuthProvider'
import { useProgramStore } from '/src/store/programStore'
import SupplementsPage from '/src/pages/SupplementsPage'
useProgramStore.setState({ program: ${JSON.stringify(program)} })
createRoot(document.getElementById('root')).render(<MantineProvider><MemoryRouter initialEntries={['/supplements']}><AuthProvider><SupplementsPage /></AuthProvider></MemoryRouter></MantineProvider>)
`
const server = await createServer({
  root: fileURLToPath(new URL('../src/frontend', import.meta.url)),
  server: { host: '127.0.0.1', port: 5184, strictPort: true },
  plugins: [{ name: 'assistant-test', resolveId: (id) => id === '/__assistant_test__.tsx' ? id : null, load: (id) => id === '/__assistant_test__.tsx' ? source : null }],
})
await server.listen()
let browser
let page
try {
  browser = await chromium.launch({ headless: true })
  page = await browser.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', (error) => browserErrors.push(error.message))
  await page.route('**/__assistant_test__', async (route) => route.fulfill({
    contentType: 'text/html',
    body: await server.transformIndexHtml('/__assistant_test__', '<html><body><div id="root"></div><script type="module" src="/__assistant_test__.tsx"></script></body></html>'),
  }))
  await page.route('http://127.0.0.1:5184/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let result
    if (path === '/api/auth/me') result = { person_pk: 'p', mapped_pk: 'a', own_athlete_pk: 'a', user: { roles: ['athlete'], active_role: 'athlete', display_name: 'Test' }, access: { permissions: ['program:read', 'program:write'] }, onboarding: { is_onboarded: true } }
    else if (path.endsWith('/history')) {
      const expand = new URL(route.request().url()).searchParams.get('expand')
      result = { turns: turns.map((turn) => ({ ...turn, content: expand === turn.id ? turn.content : undefined })), conversation_id: 'conversation' }
    }
    else if (path.endsWith('/turns')) {
      submitted += 1
      job = { id: `turn-${submitted}`, job_id: `turn-${submitted}`, status: 'running', proposals: submitted === 1 ? [proposal] : [], progress: submitted === 1 ? progress : { ...progress, text: 'New request thinking.' } }
      jobs.set(job.id, job)
      turns.unshift({ id: job.id, status: 'running', created_at: new Date().toISOString(), summary: 'Request', content: { request: 'Create current phase', reply: '', progress: job.progress, proposals: job.proposals } })
      result = job
    } else if (path.endsWith('/approve')) {
      proposal.state = 'committed'
      program.supplement_phases.push(phase)
      job = { ...job, status: 'succeeded', result: { content: 'Phase created.' } }
      jobs.set(job.id, job)
      Object.assign(turns.find((turn) => turn.id === job.id), { status: 'succeeded', summary: 'Created phase', content: { request: 'Create current phase', reply: 'Phase created.', progress, proposals: [proposal] } })
      result = proposal
    } else if (path.endsWith('/cancel')) {
      job = { ...job, status: 'cancelled' }
      jobs.set(job.id, job)
      turns.find((turn) => turn.id === job.id).status = 'cancelled'
      result = job
    } else if (path.includes('/assistant/jobs/')) result = jobs.get(path.split('/').at(-1))
    else if (path === '/api/programs/current') {
      programReads += 1
      result = { data: program }
    } else throw new Error(`Unexpected API request: ${path}`)
    await route.fulfill({ json: result })
  })
  await page.goto('http://127.0.0.1:5184/__assistant_test__')
  await page.getByRole('button', { name: 'Assistant', exact: true }).click()
  await page.getByPlaceholder('Write your request.').fill('Create current phase')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await page.getByText('First reasoning.', { exact: false }).waitFor()
  const reasoning = page.getByText('First reasoning.', { exact: false })
  await reasoning.evaluate((node) => { node.parentElement.scrollTop = 0 })
  progress.text += '\nSecond model call.'
  await page.getByText('Second model call.', { exact: false }).waitFor()
  assert.equal(await reasoning.evaluate((node) => node.parentElement.scrollTop), 0, 'stream must not scroll away while reading')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Assistant', exact: true }).click()
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  await page.getByText('Thinking', { exact: true }).waitFor()
  assert.ok(programReads > 0, 'committed change must reload the program')
  await page.getByPlaceholder('Write your request.').fill('Next message')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  assert.ok(await page.getByText('First reasoning.', { exact: false }).count() >= 1, 'previous thinking must survive a new message')
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await page.keyboard.press('Escape')
  await page.getByText('Off season', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Assistant', exact: true }).click()
  await page.getByText('Thinking', { exact: true }).first().waitFor()
  await page.getByRole('button', { name: /Created phase/ }).click()
  await page.getByText('Applied', { exact: true }).waitFor()
  await page.keyboard.press('Escape')
  await page.getByRole('combobox', { name: 'Training block' }).click()
  await page.getByRole('option', { name: 'Past block', exact: true }).click()
  assert.equal(await page.getByRole('button', { name: 'New phase', exact: true }).isDisabled(), true, 'past block must be read-only')
  assert.deepEqual(browserErrors, [])
  console.log('PASS: approval refresh, retained thinking, scroll position, reopened history, and past-block write protection')
} catch (error) {
  console.error({ browserErrors, text: (await page?.locator('body').innerText().catch(() => '')).slice(-2500) })
  throw error
} finally {
  await browser?.close()
  await server.close()
}
