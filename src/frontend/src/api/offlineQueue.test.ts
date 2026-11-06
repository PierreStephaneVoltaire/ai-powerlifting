import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isQueueableMutation, mutationFingerprint } from './drafts'
import { requestPartition, setRequestAthlete, setRequestPerson } from './context'

test('queue eligibility follows the route and the stable session id', () => {
  const body = { text: 'local' }
  assert.equal(isQueueableMutation('PUT', '/authored-notes/private', body), true)
  assert.equal(isQueueableMutation('POST', '/videos/current/upload', body), false)
  assert.equal(isQueueableMutation('PUT', '/competitions/current/unsupported', body), false)
  assert.equal(isQueueableMutation('PUT', '/sessions/current/2026-09-14/0', { ...body, session_id: ' ' }), false)
  assert.equal(isQueueableMutation('PATCH', '/sessions/current/2026-09-14/0/exercise/0', body), false)
  assert.equal(isQueueableMutation('PATCH', '/sessions/current/2026-09-14/0/exercise/0', { ...body, session_id: 'session-1' }), true)
  assert.equal(isQueueableMutation('PUT', '/sessions/current/2026-09-14/0', { ...body, id: 'session-1' }), false)
})

test('identical writes share a fingerprint and different ones do not', () => {
  assert.equal(
    mutationFingerprint('put', '/sessions/current/2026-09-14/0', { notes: 'same', session_id: 's1' }),
    mutationFingerprint('PUT', '/sessions/current/2026-09-14/0', { session_id: 's1', notes: 'same' }),
  )
  assert.notEqual(
    mutationFingerprint('PUT', '/sessions/current/2026-09-14/0', { notes: 'changed', session_id: 's1' }),
    mutationFingerprint('PUT', '/sessions/current/2026-09-14/0', { notes: 'same', session_id: 's1' }),
  )
})

test('context partitions include both Person and Athlete', () => {
  setRequestPerson('person-a')
  setRequestAthlete('athlete-a')
  assert.equal(requestPartition(), '["person-a","athlete-a"]')
  setRequestPerson('')
  setRequestAthlete('operator')
})
