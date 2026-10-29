/**
 * The grouped method choice (decision 8.134 b).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { groupMethods, searchMethods } from '@/lib/evidence/methodGroups'

const METHODS = [
  { name: 'core_compression', label: 'Core in compression', description: 'A core drilled from the element, crushed.' },
  { name: 'archival_document', label: 'Archival document', description: 'A claim from a drawing or report.' },
  { name: 'rebound_hammer', label: 'Rebound hammer', description: 'A test location with a rebound hammer.' },
  { name: 'visual_inspection', label: 'Visual inspection', description: 'Spalling, cracking, corrosion.' },
  { name: 'era_heuristic', label: 'Rule of thumb', description: 'An estimate from the construction year.' },
  { name: 'reinforcement_layout', label: 'Reinforcement layout', description: 'The bars of the element.' },
  { name: 'manufacturer_datasheet', label: 'Manufacturer datasheet', description: 'A figure from the datasheet.' },
]

test('the methods are grouped by the kind of evidence, in the order of the groups', () => {
  const groups = groupMethods(METHODS)
  assert.deepEqual(groups.map((g) => g.id), ['strength', 'ndt', 'inspection', 'reinforcement', 'documents'])
  assert.deepEqual(groups[4].methods.map((m) => m.name), ['archival_document', 'manufacturer_datasheet', 'era_heuristic'])
})

test('a group without a method is left out and a method of no group goes to Other', () => {
  const groups = groupMethods([METHODS[2], { name: 'new_method', label: 'New' }])
  assert.deepEqual(groups.map((g) => g.id), ['ndt', 'other'])
  assert.deepEqual(groups[1].methods.map((m) => m.name), ['new_method'])
  assert.deepEqual(groupMethods([]), [])
})

test('every method is in exactly one group', () => {
  const names = groupMethods(METHODS).flatMap((g) => g.methods.map((m) => m.name)).sort()
  assert.deepEqual(names, METHODS.map((m) => m.name).sort())
})

test('the search takes words of the name, label, description and group', () => {
  assert.deepEqual(searchMethods(METHODS, 'rebound').map((m) => m.name), ['rebound_hammer'])
  assert.deepEqual(searchMethods(METHODS, 'drawing').map((m) => m.name), ['archival_document'])
  assert.deepEqual(searchMethods(METHODS, 'non-destructive').map((m) => m.name), ['rebound_hammer'])
  assert.deepEqual(searchMethods(METHODS, 'rule of thumb').map((m) => m.name), ['era_heuristic'])
  assert.deepEqual(searchMethods(METHODS, 'core crushed').map((m) => m.name), ['core_compression'])
})

test('an empty search keeps every method and a search that fits none finds none', () => {
  assert.equal(searchMethods(METHODS, '').length, METHODS.length)
  assert.equal(searchMethods(METHODS, '   ').length, METHODS.length)
  assert.deepEqual(searchMethods(METHODS, 'zzz'), [])
})
