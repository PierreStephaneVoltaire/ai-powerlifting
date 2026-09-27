import assert from 'node:assert/strict'
import { test } from 'node:test'
import { routePermission } from './routes'

test('Settings is reachable through the settings permission', () => {
  assert.equal(routePermission('/settings'), 'settings:read')
  assert.equal(routePermission('/settings/profile'), 'settings:read')
})
