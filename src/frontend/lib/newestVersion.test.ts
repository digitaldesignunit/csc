/**
 * The version a form or the page starts from when the element has no current one (8.193).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { newestVersionRow } from './newestVersion'

const ROWS = [
  { _id: 'a', version: 0, status: 'withdrawn' },
  { _id: 'c', version: 2, status: 'withdrawn' },
  { _id: 'b', version: 1, status: 'withdrawn' },
]

test('the newest version by number, whatever the order of the rows', () => {
  assert.equal(newestVersionRow(ROWS)?._id, 'c')
})

test('no rows: nothing', () => {
  assert.equal(newestVersionRow([]), undefined)
})

test('with publishedOnly a draft or pending version is not the one', () => {
  const rows = [...ROWS, { _id: 'd', version: 3, status: 'draft' }, { _id: 'e', version: 4, status: 'pending' }]
  assert.equal(newestVersionRow(rows)?._id, 'e')
  assert.equal(newestVersionRow(rows, { publishedOnly: true })?._id, 'c')
})

test('a never published element has no version to start evidence from', () => {
  const rows = [{ _id: 'd', version: 0, status: 'draft' }, { _id: 'r', version: 1, status: 'rejected' }]
  assert.equal(newestVersionRow(rows, { publishedOnly: true }), undefined)
})
