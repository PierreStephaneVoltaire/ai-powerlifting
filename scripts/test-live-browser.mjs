import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

const { chromium } = createRequire(new URL('../src/package.json', import.meta.url))('@playwright/test')
const browser = await chromium.launch({ headless: true })
try {
  const context = await browser.newContext({ storageState: process.env.PL_STORAGE_STATE || '/tmp/nolift-test-session.json' })
  const response = await context.request.get('https://dev.nolift.training/api/auth/me')
  const me = await response.json()
  assert.equal(me.person_pk, 'person_be8959131fea4ca395a38e8f')
  assert.equal(me.readOnly, false)
  const page = await context.newPage()
  await page.goto('https://dev.nolift.training/sessions')
  await page.getByText('Squat', { exact: true }).first().waitFor()
  assert.equal(await page.getByText('Squat', { exact: true }).count(), 3)
  assert.ok(await page.getByText('Nov 2', { exact: true }).isVisible())
  assert.ok(await page.getByText('Nov 16', { exact: true }).isVisible())
  console.log('Live browser checks passed')
} finally {
  await browser.close()
}
