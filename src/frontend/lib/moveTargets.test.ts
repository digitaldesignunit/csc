/**
 * The destinations of a move (8.191): the datasets the caller moderates, an
 * admin all, never the dataset the element is in.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { moveTargets, unreviewedRefuses, unreviewedWarning } from './moveTargets'

const DATASETS = [
  { _id: 'b_set', name: 'Beta' },
  { _id: 'a_set', name: 'Alpha' },
  { _id: 'c_set', name: 'Gamma', reviewed: false },
]

test('a moderator is offered the other datasets they moderate, by name', () => {
  const got = moveTargets({ datasets: DATASETS, moderated: ['a_set', 'b_set'], isAdmin: false, current: 'b_set' })
  assert.deepEqual(got.map((t) => t.id), ['a_set'])
})

test('an admin is offered every other dataset', () => {
  const got = moveTargets({ datasets: DATASETS, moderated: [], isAdmin: true, current: 'a_set' })
  assert.deepEqual(got.map((t) => t.name), ['Beta', 'Gamma'])
})

test('a dataset the caller does not moderate, or the current one, is not offered', () => {
  assert.deepEqual(moveTargets({ datasets: DATASETS, moderated: ['a_set'], isAdmin: false, current: 'a_set' }), [])
  assert.deepEqual(moveTargets({ datasets: DATASETS, moderated: [], isAdmin: false, current: 'a_set' }), [])
})

test('a dataset without the flag counts as reviewed', () => {
  const got = moveTargets({ datasets: DATASETS, moderated: ['a_set', 'c_set'], isAdmin: false, current: null })
  assert.deepEqual(got.map((t) => [t.id, t.reviewed]), [['a_set', true], ['c_set', false]])
})

test('only a public element is warned about an unreviewed destination', () => {
  const unreviewed = { id: 'c_set', name: 'Gamma', reviewed: false }
  assert.equal(unreviewedWarning(unreviewed, false, false), null)
  assert.equal(unreviewedWarning({ ...unreviewed, reviewed: true }, true, false), null)
  assert.equal(unreviewedWarning(undefined, true, false), null)
  assert.match(unreviewedWarning(unreviewed, true, false) ?? '', /cannot move there/)
  assert.match(unreviewedWarning(unreviewed, true, true) ?? '', /as an administrator/)
})

test('Move is off where the route refuses for sure: a public element, an unreviewed destination, no admin', () => {
  const unreviewed = { id: 'c_set', name: 'Gamma', reviewed: false }
  assert.equal(unreviewedRefuses(unreviewed, true, false), true)
  assert.equal(unreviewedRefuses(unreviewed, true, true), false)
  assert.equal(unreviewedRefuses(unreviewed, false, false), false)
  assert.equal(unreviewedRefuses({ ...unreviewed, reviewed: true }, true, false), false)
  assert.equal(unreviewedRefuses(undefined, true, false), false)
})
