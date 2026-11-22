import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRequire } from 'node:module'
import type * as Units from './units'

const { fromDisplayUnit, toDisplayUnit, displayWeight } = createRequire(import.meta.url)('./units.ts') as typeof Units

test('pound weights retain up to two decimals without rounding stored kilograms', () => {
  for (const lb of [170, 170.4, 170.42]) {
    const kg = fromDisplayUnit(lb, 'lb')
    assert.equal(toDisplayUnit(kg, 'lb'), lb)
    assert.equal(displayWeight(kg, 'lb'), `${lb} lb`)
  }
  assert.equal(fromDisplayUnit(170.42, 'lb'), 170.42 / 2.20462)
})
