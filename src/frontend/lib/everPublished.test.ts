/**
 * "Ever published" (decision 8.193): the same answer as `identity_ever_published`
 * in `apps/catalog/api/access.py`.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { everPublished } from './everPublished'

test('a current version means published once', () => {
  assert.equal(everPublished({ currentSnapshotId: 'v1' }), true)
  assert.equal(everPublished({ currentSnapshotId: 'v1', versions: [] }), true)
})

test('every version withdrawn: published once, with no current version', () => {
  assert.equal(everPublished({ currentSnapshotId: null, versions: [{ status: 'withdrawn' }] }), true)
  assert.equal(
    everPublished({ currentSnapshotId: '', versions: [{ status: 'withdrawn' }, { status: 'withdrawn' }] }),
    true,
  )
})

test('a published row counts even when the element names no current version', () => {
  assert.equal(everPublished({ versions: [{ status: 'published' }] }), true)
})

test('draft, pending and rejected versions do not make an element published', () => {
  for (const status of ['draft', 'pending', 'rejected']) {
    assert.equal(everPublished({ currentSnapshotId: null, versions: [{ status }] }), false, status)
  }
  assert.equal(
    everPublished({ versions: [{ status: 'draft' }, { status: 'rejected' }, { status: null }, {}] }),
    false,
  )
})

test('no rows and no current version: not published', () => {
  assert.equal(everPublished({}), false)
  assert.equal(everPublished({ currentSnapshotId: null, versions: [] }), false)
  assert.equal(everPublished({ currentSnapshotId: undefined, versions: null }), false)
})
