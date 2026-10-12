import assert from 'node:assert/strict'
import test from 'node:test'

import { HKS_VISIBLE } from '@/lib/hks'
import { mapBasisOptions } from '@/lib/mapBases'

test('the map offers the radial signature and the scalars', () => {
  assert.deepEqual(mapBasisOptions(false).map((o) => o.value), ['radial_signature', 'scalars'])
})

test('the heat kernel signature is offered only with the flag on', () => {
  assert.deepEqual(mapBasisOptions(true).map((o) => o.value), ['radial_signature', 'scalars', 'hks'])
})

test('the flag is off: the page offers no HKS and shows no HKS curve', () => {
  assert.equal(HKS_VISIBLE, false)
  assert.equal(mapBasisOptions().some((o) => o.value === 'hks'), false)
})
