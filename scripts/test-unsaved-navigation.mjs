import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

const { chromium } = createRequire(new URL('../src/package.json', import.meta.url))('@playwright/test')
const baseUrl = process.env.PL_BASE_URL || 'https://dev.nolift.training'
const liveUrl = process.env.PL_LIVE_URL || 'https://dev.nolift.training'
const browser = await chromium.launch({ headless: false, executablePath: '/usr/bin/brave-browser', args: ['--no-sandbox'] })

try {
  const context = await browser.newContext({ storageState: process.env.PL_STORAGE_STATE || '/tmp/nolift-test-session.json' })
  await context.route(`${baseUrl}/api/**`, async (route) => {
    const request = route.request()
    if (request.method() !== 'GET' || /assistant|coach|analytics-ai|correlation|evaluation/i.test(request.url())) return route.abort()
    try {
      const response = await context.request.get(request.url().replace(baseUrl, liveUrl))
      return route.fulfill({ response })
    } catch {
      return route.abort()
    }
  })
  const response = await context.request.get(`${liveUrl}/api/auth/me`)
  const me = await response.json()
  assert.equal(response.ok(), true)
  assert.equal(me.person_pk, 'person_be8959131fea4ca395a38e8f')
  assert.equal(me.readOnly, false)

  const cases = [
    { path: '/designer/goals', add: 'Add Goal' },
    { path: '/supplements', add: 'New phase' },
    { path: '/biometrics', add: 'Add Entry' },
  ]
  const page = await context.newPage()
  for (const item of cases) {
    await page.goto(`${baseUrl}${item.path}`)
    await page.getByRole('button', { name: item.add, exact: true }).first().click()
    const draft = page.getByRole('button', { name: 'Save', exact: true })
    await draft.waitFor()
    const cancelled = page.waitForEvent('dialog').then(async (dialog) => {
      assert.match(dialog.message(), /unsaved changes/i)
      await dialog.dismiss()
    })
    await page.getByRole('link', { name: 'Dashboard', exact: true }).first().click()
    await cancelled
    assert.ok(page.url().endsWith(item.path))
    await draft.waitFor()
    const accepted = page.waitForEvent('dialog').then((dialog) => dialog.accept())
    await page.getByRole('link', { name: 'Dashboard', exact: true }).first().click()
    await accepted
    await page.waitForURL(`${baseUrl}/`)
  }

  await page.goto(`${baseUrl}/notes`)
  const note = page.locator('textarea').first()
  await note.fill('Unsaved browser test note')
  await page.getByRole('button', { name: 'Save Entry' }).click()
  await page.getByText('Failed to save notes').waitFor()
  assert.equal(await note.inputValue(), 'Unsaved browser test note')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('link', { name: 'Designer', exact: true }).first().click()
  await page.getByRole('link', { name: /goals/i }).first().click()
  await page.getByRole('button', { name: 'Add Goal', exact: true }).click()
  const backCancelled = page.waitForEvent('dialog').then((dialog) => {
    assert.match(dialog.message(), /unsaved changes/i)
    return dialog.dismiss()
  })
  await page.evaluate(() => history.back())
  await backCancelled
  await page.waitForURL(`${baseUrl}/designer/goals`)
  await page.getByRole('button', { name: 'Save', exact: true }).waitFor()
  console.log('Unsaved navigation browser checks passed')
} finally {
  await browser.close()
}
