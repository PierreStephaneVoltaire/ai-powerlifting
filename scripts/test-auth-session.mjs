import { spawnSync } from 'node:child_process'
import { chmodSync, closeSync, openSync } from 'node:fs'
import { createRequire } from 'node:module'
import { randomUUID } from 'node:crypto'

const { chromium } = createRequire(new URL('../src/package.json', import.meta.url))('@playwright/test')
const username = 'acceptance-luna-20260915'
const person = 'person_be8959131fea4ca395a38e8f'
const origin = process.env.PL_APP_ORIGIN || 'https://dev.nolift.training'
const state = process.env.PL_STORAGE_STATE || '/tmp/nolift-test-session.json'
const id = `codex-test-${randomUUID()}`
const shell = code => {
  const result = spawnSync('kubectl', ['exec', '-n', 'powerlifting', 'deploy/authentik-worker', '--', 'ak', 'shell', '-c', code], { encoding: 'utf8' })
  if (result.status !== 0) throw new Error(`Authentik command failed: ${result.stderr.trim()}`)
  return result.stdout.trim()
}
let browser
try {
  const output = shell(`from authentik.core.models import User, Token, TokenIntents; from django.utils import timezone; from datetime import timedelta; print('CREDENTIAL_RESULT='+Token.objects.create(identifier='${id}', user=User.objects.get(username='${username}'), intent=TokenIntents.INTENT_APP_PASSWORD, expiring=True, expires=timezone.now()+timedelta(minutes=10)).key)`)
  const password = output.match(/CREDENTIAL_RESULT=([^\s]+)/)?.[1]
  if (!password) throw new Error('Could not create test credential')
  browser = await chromium.launch({ headless: true })
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(`${origin}/oauth2/start`)
  const login = page.locator('input[name="uidField"]')
  await login.fill(username)
  await login.press('Enter')
  await login.waitFor({ state: 'hidden' })
  const passwordInput = page.locator('input[type="password"]:visible').first()
  await passwordInput.fill(password)
  await passwordInput.press('Enter')
  await page.waitForURL(`${origin}/**`, { timeout: 30000 })
  const response = await context.request.get(`${origin}/api/auth/me`)
  const me = await response.json()
  if (!response.ok() || me.readOnly !== false || me.person_pk !== person) throw new Error('Login did not resolve the expected test Person')
  closeSync(openSync(state, 'w', 0o600))
  chmodSync(state, 0o600)
  await context.storageState({ path: state })
  console.log(`Authenticated test session saved to ${state}`)
} finally {
  await browser?.close()
  shell(`from authentik.core.models import Token; Token.objects.filter(identifier='${id}').delete()`)
}
