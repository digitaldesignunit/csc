/**
 * The empty state of the Properties card: a link to add evidence only for
 * someone who may, and only when there is no property to show (T11b).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { canAddEvidence } from './componentDetail'
import { addEvidenceHref, propertiesEmptyState } from './propertiesEmpty'

const CONTRIBUTOR = { signedIn: true, isAdmin: false, roles: ['contributor'], withdrawn: null, currentSnapshotId: 'v1' }

test('with properties there is no empty state, whoever looks', () => {
  assert.deepEqual(propertiesEmptyState(true, '/components/e/evidence/new'), { kind: 'none' })
  assert.deepEqual(propertiesEmptyState(true, null), { kind: 'none' })
})

test('without properties a user who may add evidence gets the link, everyone else the plain sentence', () => {
  const href = addEvidenceHref('e1', canAddEvidence(CONTRIBUTOR))
  assert.equal(href, '/components/e1/evidence/new')
  assert.deepEqual(propertiesEmptyState(false, href), { kind: 'link', href: '/components/e1/evidence/new' })
  for (const viewer of [
    { ...CONTRIBUTOR, signedIn: false },
    { ...CONTRIBUTOR, roles: ['reviewer'] },
    { ...CONTRIBUTOR, withdrawn: { at: '2026-01-01T00:00:00Z' } },
    { ...CONTRIBUTOR, currentSnapshotId: null },
  ]) {
    assert.deepEqual(propertiesEmptyState(false, addEvidenceHref('e1', canAddEvidence(viewer))), { kind: 'plain' })
  }
})

test('the address names the element and is escaped', () => {
  assert.equal(addEvidenceHref('a b/c', true), '/components/a%20b%2Fc/evidence/new')
  assert.equal(addEvidenceHref('e1', false), null)
})
