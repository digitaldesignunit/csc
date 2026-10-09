import assert from 'node:assert/strict'
import { test } from 'node:test'

import { METHOD_ORDER, orderMethods } from './order'

test('the cards go by use on site', () => {
  const given = ['core_compression', 'archival_document', 'rebound_hammer', 'visual_inspection',
    'era_heuristic', 'reinforcement_layout', 'manufacturer_datasheet'].map((name) => ({ name }))
  assert.deepEqual(orderMethods(given).map((m) => m.name), METHOD_ORDER)
})

test('a method the list does not know goes last, in the order given', () => {
  const given = [{ name: 'new_b' }, { name: 'rebound_hammer' }, { name: 'new_a' }, { name: 'visual_inspection' }]
  assert.deepEqual(orderMethods(given).map((m) => m.name), ['visual_inspection', 'rebound_hammer', 'new_b', 'new_a'])
})

test('the input is not changed', () => {
  const given = [{ name: 'core_compression' }, { name: 'visual_inspection' }]
  orderMethods(given)
  assert.deepEqual(given.map((m) => m.name), ['core_compression', 'visual_inspection'])
})

test('the tier chip is short and never the method name', async () => {
  const { tierChip } = await import('./order')
  assert.equal(tierChip('visual'), 'Visual')
  assert.equal(tierChip('ndt'), 'Non-destructive')
  assert.equal(tierChip('heuristic'), 'Estimate')
  assert.equal(tierChip('archival', true), 'Source varies')
  assert.equal(tierChip('unknown-tier'), '')
  assert.equal(tierChip(null), '')
})
