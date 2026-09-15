import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sessionIndexForRoute, sessionRoute } from './sessionRoute'

test('same-day Session links survive reordering and reject ambiguous legacy selectors', () => {
  const first = { id: 'first', date: '2026-09-14' }
  const second = { id: 'second', date: '2026-09-14' }
  assert.equal(sessionRoute(second, 1), '/session/2026-09-14?session=second')
  assert.equal(sessionIndexForRoute([second, first], first.date, undefined, second.id), 0)
  assert.equal(sessionIndexForRoute([second, first], first.date), -1)
  assert.equal(sessionIndexForRoute([first], first.date), 0)
  assert.equal(sessionIndexForRoute([first], first.date, '0oops'), -1)
  assert.equal(sessionIndexForRoute([first], first.date, '0', 'deleted'), -1)
  assert.equal(sessionIndexForRoute([first], '2026-09-15', '0'), -1)
})
