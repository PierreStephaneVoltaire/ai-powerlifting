import assert from 'node:assert/strict'
import { test } from 'node:test'
import { operationScope } from '../utils/operationScope'

test('exercise field updates read and patch the stable Session after same-day reorder', async () => {
  process.env.INTERNAL_API_TOKEN = 'session-controller-test-token'
  process.env.PL_PRINCIPAL_SECRET = 'session-controller-test-principal-secret'
  process.env.POWERLIFTING_SERVICE_BASE_URL = 'http://session-controller-test'
  const sessions = [
    { id: 'session-sibling', date: '2026-09-14', exercises: [{ name: 'sibling squat', sets: 3 }] },
    { id: 'session-intended', date: '2026-09-14', exercises: [{ name: 'intended squat', sets: 5 }, { name: 'intended bench', sets: 4 }] },
  ]
  const calls: Array<{ url: string; body: any }> = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    const request = new Request(input, init)
    const body = await request.json()
    calls.push({ url: request.url, body })
    if (request.url.endsWith('/profile/internal/access')) return new Response(JSON.stringify({ settings_pk: 'person-1' }), { status: 200 })
    if (request.url.endsWith('/operations/session_get')) {
      assert.equal(body.session_id, 'session-intended')
      return new Response(JSON.stringify(sessions.find(session => session.id === body.session_id)), { status: 200 })
    }
    if (request.url.endsWith('/operations/session_patch')) {
      assert.equal(body.session_id, 'session-intended')
      const target = sessions.find(session => session.id === body.session_id)
      assert.ok(target)
      target!.exercises = body.patch.exercises
      return new Response(JSON.stringify(target), { status: 200 })
    }
    throw new Error(`Unexpected request ${request.url}`)
  }) as typeof fetch

  try {
    const { updateExerciseField } = await import('./sessionController')
    const updated = await operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => updateExerciseField(
      'athlete-1', 'current', '2026-09-14', 0, 0, 'name', 'intended squat updated',
      { expected_revision: 7, idempotency_key: 'session-controller-reorder', session_id: 'session-intended' },
    ))
    assert.equal(calls.filter(call => call.url.endsWith('/operations/session_get')).length, 1)
    assert.equal(calls.filter(call => call.url.endsWith('/operations/session_patch')).length, 1)
    assert.equal(updated.id, 'session-intended')
    assert.deepEqual(updated.exercises, [
      { name: 'intended squat updated', sets: 5 },
      { name: 'intended bench', sets: 4 },
    ])
    assert.deepEqual(sessions[0].exercises, [{ name: 'sibling squat', sets: 3 }])
  } finally {
    globalThis.fetch = originalFetch
  }
})
