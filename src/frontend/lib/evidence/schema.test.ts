/**
 * The labels the evidence form takes from the registry's schema titles.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { labelOf, type Resolved } from '@/lib/evidence/schema'

const resolved = (title: string): Resolved => ({ schema: {}, nullable: false, title, description: '' })

test('a class name used as a title reads as words', () => {
  assert.equal(labelOf('instrument', resolved('ReboundInstrument')), 'Rebound instrument')
  assert.equal(labelOf('test_area', resolved('ReboundTestArea')), 'Rebound test area')
  assert.equal(labelOf('x', resolved('Anvilcheck')), 'Anvilcheck')
})

test('a title with spaces keeps its words, units as written', () => {
  assert.equal(labelOf('min_spacing_mm', resolved('Min Spacing Mm')), 'Min spacing mm')
  assert.equal(labelOf('impact_energy_nm', resolved('Impact Energy Nm')), 'Impact energy Nm')
})

test('without a title the key is the label', () => {
  assert.equal(labelOf('surface_preparation', resolved('')), 'Surface preparation')
})
