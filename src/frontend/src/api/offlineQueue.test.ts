import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isQueueableMutation, mutationFingerprint } from './drafts'
import { requestPartition, setRequestAthlete, setRequestPerson } from './context'

test('queue eligibility excludes online-only or unversioned writes', () => {
  const body = { expected_revision: 3, idempotency_key: 'first', text: 'local' }
  assert.equal(isQueueableMutation('PUT', '/authored-notes/private', body), true)
  assert.equal(isQueueableMutation('POST', '/videos/current/upload', body), false)
  assert.equal(isQueueableMutation('PUT', '/competitions/current/unsupported', body), false)
  assert.equal(isQueueableMutation('PUT', '/sessions/current/2026-09-14/0', { text: 'missing envelope' }), false)
  assert.equal(isQueueableMutation('PUT', '/sessions/current/2026-09-14/0', { ...body, session_id: ' ' }), false)
  assert.equal(isQueueableMutation('PATCH', '/sessions/current/2026-09-14/0/exercise/0', body), false)
  assert.equal(isQueueableMutation('PATCH', '/sessions/current/2026-09-14/0/exercise/0', { ...body, session_id: 'session-1' }), true)
  assert.equal(isQueueableMutation('PUT', '/sessions/current/2026-09-14/0', { ...body, id: 'session-1' }), false)
})

test('retry fingerprint ignores a newly generated idempotency key', () => {
  assert.equal(
    mutationFingerprint('put', '/sessions/current/2026-09-14/0', { expected_revision: 4, idempotency_key: 'first', notes: 'same' }),
    mutationFingerprint('PUT', '/sessions/current/2026-09-14/0', { expected_revision: 4, idempotency_key: 'retry', notes: 'same' }),
  )
  assert.notEqual(
    mutationFingerprint('PUT', '/sessions/current/2026-09-14/0', { expected_revision: 4, idempotency_key: 'retry', notes: 'changed' }),
    mutationFingerprint('PUT', '/sessions/current/2026-09-14/0', { expected_revision: 4, idempotency_key: 'first', notes: 'same' }),
  )
})

test('context partitions include both Person and Athlete', () => {
  setRequestPerson('person-a')
  setRequestAthlete('athlete-a')
  assert.equal(requestPartition(), '["person-a","athlete-a"]')
  setRequestPerson('')
  setRequestAthlete('operator')
})
