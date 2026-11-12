import assert from 'node:assert/strict'
import test from 'node:test'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

test('request logging removes identity credentials and session cookies', () => {
  const script = `const { logger } = require(${JSON.stringify(resolve(__dirname, 'logger.ts'))}); logger.info({ req: { method: 'GET', headers: { authorization: 'test-id-token', cookie: 'test-session', 'x-pl-principal': 'test-principal', 'x-pl-access-context': 'test-context' } }, res: { headers: { 'set-cookie': 'test-cookie' } } });`
  const result = spawnSync(process.execPath, ['--import', 'tsx', '-e', script], { cwd: resolve(__dirname, '../../..'), encoding: 'utf8', env: { ...process.env, LOG_LEVEL: 'info' } })
  assert.equal(result.status, 0, result.stderr)
  assert.equal(JSON.parse(result.stdout).req.method, 'GET')
  for (const value of ['test-id-token', 'test-session', 'test-principal', 'test-context', 'test-cookie']) assert.equal(result.stdout.includes(value), false)
})
