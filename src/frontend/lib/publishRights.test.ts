/**
 * Publishing the first version of a child (8.8, #46): the parents decide.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  IDENTITY_WITHDRAWN_PUBLISH,
  isFirstPublish,
  parentsRefusePublish,
  publishBlockOf,
  type ParentLookup,
} from './publishRights'

const moderatesOnly = (...datasets: string[]) => (dataset: string) => datasets.includes(dataset)
const own = (dataset: string): ParentLookup => ({ kind: 'dataset', dataset })

test('a first version is one with no published or withdrawn version before it', () => {
  assert.equal(isFirstPublish([]), true)
  assert.equal(isFirstPublish([{ status: 'pending' }, { status: 'rejected' }, { status: 'draft' }]), true)
  assert.equal(isFirstPublish([{ status: 'published' }]), false)
  assert.equal(isFirstPublish([{ status: 'withdrawn' }, { status: 'pending' }]), false)
})

test('a later version, or a root element, is not stopped by parents', () => {
  assert.equal(parentsRefusePublish({ first: false, moderates: moderatesOnly(), parents: [own('b')] }), null)
  assert.equal(parentsRefusePublish({ first: true, moderates: moderatesOnly(), parents: [] }), null)
})

test('the first version of a child needs a moderator of every parent dataset', () => {
  const ok = parentsRefusePublish({ first: true, moderates: moderatesOnly('a', 'b'), parents: [own('a'), own('b')] })
  assert.equal(ok, null)
  const one = parentsRefusePublish({ first: true, moderates: moderatesOnly('a'), parents: [own('a'), own('b')] })
  assert.match(one ?? '', /\(b\)/)
})

test('a parent the caller cannot read is a dataset they do not moderate', () => {
  const refused = parentsRefusePublish({ first: true, moderates: moderatesOnly('a'), parents: [own('a'), { kind: 'refused' }] })
  assert.ok(refused)
  assert.doesNotMatch(refused ?? '', /\(/)
})

test('a parent that is gone is skipped, as the backend does', () => {
  assert.equal(parentsRefusePublish({ first: true, moderates: moderatesOnly(), parents: [{ kind: 'gone' }] }), null)
})

test('a site admin moderates every dataset', () => {
  assert.equal(parentsRefusePublish({ first: true, moderates: () => true, parents: [own('a'), own('z')] }), null)
})

test('the queue offers no Publish on a version of a withdrawn element, whatever the parents say (8.190)', () => {
  assert.equal(publishBlockOf({ identityWithdrawn: true, parentBlock: null }), IDENTITY_WITHDRAWN_PUBLISH)
  assert.equal(publishBlockOf({ identityWithdrawn: true, parentBlock: 'loading' }), IDENTITY_WITHDRAWN_PUBLISH)
  assert.equal(publishBlockOf({ identityWithdrawn: true, parentBlock: 'a parent refuses' }), IDENTITY_WITHDRAWN_PUBLISH)
  // otherwise the parents decide, as before
  assert.equal(publishBlockOf({ identityWithdrawn: false, parentBlock: null }), null)
  assert.equal(publishBlockOf({ identityWithdrawn: undefined, parentBlock: 'loading' }), 'loading')
  assert.equal(publishBlockOf({ parentBlock: 'a parent refuses' }), 'a parent refuses')
  assert.match(IDENTITY_WITHDRAWN_PUBLISH, /reinstate it before publishing/)
})
