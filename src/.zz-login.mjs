import { chromium } from '@playwright/test'
const pw = process.argv[2], S = process.argv[3]
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1400, height: 900 } })
const bad = []
p.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) bad.push(`${r.status()} ${r.request().method()} ${r.url()}`) })
await p.goto('https://dev.nolift.training/', { waitUntil: 'networkidle' })
const login = p.getByRole('link', { name: /log ?in|sign ?in/i }).or(p.getByRole('button', { name: /log ?in|sign ?in/i }))
if (await login.count()) await login.first().click()
await p.waitForSelector('input[name="uidField"]', { timeout: 20000 })
await p.fill('input[name="uidField"]', 'test'); await p.keyboard.press('Enter')
await p.waitForSelector('input[name="password"]', { timeout: 20000 })
await p.fill('input[name="password"]', pw); await p.keyboard.press('Enter')
await p.waitForURL(u => u.hostname === 'dev.nolift.training' && !u.pathname.startsWith('/oauth2'), { timeout: 30000 })
await p.waitForLoadState('networkidle')
console.log('after login', p.url())
await p.screenshot({ path: `${S}/dashboard.png` })
const me = await p.evaluate(() => fetch('/api/auth/me').then(r => r.status))
console.log('/api/auth/me', me)
for (const path of ['/sessions', '/session']) {
  await p.goto('https://dev.nolift.training' + path, { waitUntil: 'networkidle' }).catch(e => console.log(e.message))
  console.log('visited', p.url())
}
await p.screenshot({ path: `${S}/sessions.png` })
await p.context().storageState({ path: `${S}/state.json` })
console.log('API errors:\n' + bad.join('\n'))
await b.close()
