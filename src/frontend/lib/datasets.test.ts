import assert from 'node:assert/strict'
import { test } from 'node:test'

import { datasetCounts } from './datasets'

test('the counts line names members and components', () => {
  assert.equal(datasetCounts({ member_count: 3, component_count: 120 }), '3 members, 120 components')
  assert.equal(datasetCounts({ member_count: 1, component_count: 1 }), '1 member, 1 component')
  assert.equal(datasetCounts({ member_count: 0, component_count: 0 }), '0 members, 0 components')
})

test('a count that is not there is left out', () => {
  assert.equal(datasetCounts({ component_count: 2 }), '2 components')
  assert.equal(datasetCounts({ member_count: null, component_count: 1500 }), '1,500 components')
  assert.equal(datasetCounts({}), '')
})

import { awaitsReview, newDatasetHint, slugFromName } from '@/lib/datasets'

test('the id of a dataset is made from its name like the API makes it', () => {
  assert.equal(slugFromName('Lichtwiese Survey'), 'lichtwiese_survey')
  assert.equal(slugFromName('  Zur\u00fcck zum B\u00e4ren!  '), 'zuruck_zum_baren')
  assert.equal(slugFromName('Beyond Debris 2026'), 'beyond_debris_2026')
  assert.equal(slugFromName('a--b__c'), 'a_b_c')
  assert.equal(slugFromName('---'), 'dataset')
  assert.equal(slugFromName(''), 'dataset')
  assert.equal(slugFromName('X'), 'x_x')
  assert.equal(slugFromName('\u30c7\u30fc\u30bf'), 'dataset')           // nothing ASCII is left
})

test('a long name is cut to 55 characters without a trailing underscore', () => {
  const slug = slugFromName(`${'a'.repeat(54)} b c d`)
  assert.ok(slug.length <= 55 && !slug.endsWith('_'), slug)
  assert.equal(slugFromName('b'.repeat(80)).length, 55)
})

test('only a dataset marked not reviewed awaits review', () => {
  assert.equal(awaitsReview({ reviewed: false }), true)
  assert.equal(awaitsReview({ reviewed: true }), false)
  assert.equal(awaitsReview({}), false)
  assert.equal(awaitsReview({ reviewed: null }), false)
})

test('the hint shows the id the name makes', () => {
  assert.match(newDatasetHint('Lichtwiese Survey'), /^Id: lichtwiese_survey /)
  assert.match(newDatasetHint(' '), /^The id is made from the name/)
})
