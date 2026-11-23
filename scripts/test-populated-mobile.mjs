import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

const { chromium } = createRequire(new URL('../src/package.json', import.meta.url))('@playwright/test')
const baseUrl = process.env.PL_BASE_URL || 'http://127.0.0.1:5173'
const liveUrl = 'https://dev.nolift.training'
const browser = await chromium.launch({ headless: false, executablePath: '/usr/bin/brave-browser', args: ['--no-sandbox'] })

try {
  const context = await browser.newContext({ storageState: process.env.PL_STORAGE_STATE || '/tmp/nolift-test-session.json', viewport: { width: 375, height: 667 } })
  const identity = await context.request.get(`${liveUrl}/api/auth/me`)
  const me = await identity.json()
  assert.equal(identity.ok(), true)
  assert.equal(me.person_pk, 'person_be8959131fea4ca395a38e8f')
  assert.equal(me.readOnly, false)

  await context.route(`${baseUrl}/api/**`, async (route) => {
    const request = route.request()
    const url = request.url()
    if (request.method() !== 'GET' || /assistant|coach|analytics-ai|correlation|evaluation/i.test(url)) return route.abort()
    try {
      const response = await context.request.get(url.replace(baseUrl, liveUrl))
      if (/\/api\/goals(?:\?|$)/.test(url)) {
        const payload = await response.json()
        payload.data = Array.from({ length: 20 }, (_, i) => ({ id: `synthetic-goal-${i + 1}`, title: `Goal ${i + 1}: Improve competition performance with a descriptive title`, goal_type: 'custom', priority: 'secondary', notes: '' }))
        return route.fulfill({ response, json: payload })
      }
      if (!/\/api\/programs\/current(?:\?|$)/.test(url)) return route.fulfill({ response })
      const payload = await response.json()
      const program = payload.data
      const block = program.meta.current_block_id || 'current'
      const date = (i) => new Date(Date.UTC(2026, 10, 1 + i)).toISOString().slice(0, 10)
      program.meta.block_notes = Array.from({ length: 30 }, (_, i) => ({ date: date(i), block_id: block, notes: `Note ${i + 1}: ${'Long training context, recovery, exercise technique and adjustments. '.repeat(4)}`, updated_at: `${date(i)}T12:00:00Z` }))
      program.diet_notes = Array.from({ length: 12 }, (_, i) => ({ date: date(i), block_id: block, notes: `Biometrics ${i + 1}`, avg_daily_calories: 3000 + i, avg_protein_g: 180 + i, consistent: true }))
      program.supplement_phases = Array.from({ length: 2 }, (_, i) => ({ phase: i + 1, phase_name: `Synthetic phase ${i + 1}`, block_id: block, notes: '', start_week: 1, end_week: 4, items: Array.from({ length: 8 }, (_, k) => ({ name: `Compound ${i + 1}-${k + 1}`, dose: '5 g/day', notes: '', dose_assessment: 'within_range' })) }))
      return route.fulfill({ response, json: payload })
    } catch {
      return route.abort()
    }
  })

  const page = await context.newPage()
  for (const viewport of [{ width: 375, height: 667 }, { width: 320, height: 568 }]) {
    await page.setViewportSize(viewport)
    await page.goto(`${baseUrl}/notes`)
    await page.getByTestId('program-note-card').first().waitFor()
    assert.equal(await page.getByTestId('program-note-card').count(), 5)
    const firstNote = await page.getByTestId('program-note-card').first().innerText()
    await page.getByRole('button', { name: 'Next' }).first().click()
    assert.ok(await page.evaluate(() => document.querySelector('[data-testid="program-note-card"]')?.getBoundingClientRect().top < innerHeight))
    for (let index = 2; index < 6; index += 1) await page.getByRole('button', { name: 'Next' }).first().click()
    assert.equal(await page.getByTestId('program-note-card').count(), 5)
    assert.notEqual(await page.getByTestId('program-note-card').first().innerText(), firstNote)
    assert.match(await page.getByTestId('program-note-card').first().innerText(), /Note 5:/)
    await page.getByRole('button', { name: 'Previous' }).first().click()
    for (let index = 2; index < 5; index += 1) await page.getByRole('button', { name: 'Previous' }).first().click()
    await page.getByRole('button', { name: 'Previous' }).last().click()
    assert.ok(await page.evaluate(() => document.querySelector('[data-testid="program-note-card"]')?.getBoundingClientRect().top < innerHeight))
    await page.getByTestId('program-note-card').first().click()
    await page.getByTestId('program-note-text').fill('Unsaved note switch draft')
    const editPrompt = page.waitForEvent('dialog').then(async (dialog) => {
      assert.match(dialog.message(), /unsaved|discard|leave/i)
      await dialog.dismiss()
    })
    await page.getByTestId('program-note-card').nth(1).click()
    await editPrompt
    assert.equal(await page.getByTestId('program-note-text').inputValue(), 'Unsaved note switch draft')

    page.once('dialog', (dialog) => dialog.accept())
    await page.goto(`${baseUrl}/designer/goals`)
    await page.getByRole('button', { name: /Goal 1:/ }).waitFor()
    assert.equal(await page.locator('[data-accordion-control]').count(), 5)
    assert.equal(await page.getByText('secondary', { exact: true }).count(), 5)
    for (let index = 1; index < 4; index += 1) await page.getByRole('button', { name: 'Next' }).first().click()
    assert.equal(await page.getByRole('button', { name: /Goal 20:/ }).count(), 1)
    await page.getByRole('button', { name: 'Previous' }).first().click()
    const goalDraft = page.getByRole('button', { name: /Goal 11:/ })
    await goalDraft.click()
    await page.locator('textarea:visible').last().fill('Unsaved goal paging draft')
    await page.getByRole('button', { name: 'Next' }).first().click()
    await page.getByRole('button', { name: 'Previous' }).first().click()
    const goalOnReturn = page.getByRole('button', { name: /Goal 11:/ })
    if (await goalOnReturn.getAttribute('aria-expanded') !== 'true') await goalOnReturn.click()
    assert.equal(await page.locator('textarea:visible').last().inputValue(), 'Unsaved goal paging draft')

    page.once('dialog', (dialog) => dialog.accept())
    await page.goto(`${baseUrl}/biometrics`)
    await page.getByRole('button', { name: 'Next' }).first().waitFor()
    assert.equal(await page.locator('.if-card').count(), 2)
    const draft = page.locator('.if-card input[type=number]').first()
    await draft.fill('7777')
    await page.getByRole('button', { name: 'Next' }).last().click()
    await page.getByRole('button', { name: 'Previous' }).last().click()
    assert.equal(await draft.inputValue(), '7777')

    page.once('dialog', (dialog) => dialog.accept())
    await page.goto(`${baseUrl}/supplements`)
    assert.equal(await page.locator('.if-supp-phase-inner').count(), 0)
    await page.getByRole('button', { name: /Phase 1/ }).click()
    assert.equal(await page.locator('.if-supp-table-row').count(), 3)
    const compound = page.locator('.if-supp-table-row input').first()
    await compound.fill('Edited compound')
    await page.getByRole('button', { name: 'Next' }).last().click()
    assert.ok(await page.evaluate(() => document.querySelector('.if-supp-table-row')?.getBoundingClientRect().top < innerHeight))
    const secondItem = await page.locator('.if-supp-table-row input').first().inputValue()
    assert.notEqual(secondItem, 'Edited compound')
    await page.getByRole('button', { name: 'Previous' }).last().click()
    assert.ok(await page.evaluate(() => document.querySelector('.if-supp-table-row')?.getBoundingClientRect().top < innerHeight))
    assert.equal(await page.locator('.if-supp-table-row input').first().inputValue(), 'Edited compound')
    page.once('dialog', (dialog) => dialog.accept())

    const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth }))
    assert.ok(dimensions.width <= dimensions.viewport + 2, JSON.stringify(dimensions))
  }
  console.log('Populated mobile Brave checks passed')
} finally {
  await browser.close()
}
