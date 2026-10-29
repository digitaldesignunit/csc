/**
 * The session monitor on a component page (issue 35): a public piece stays
 * readable after the session ended, a private piece or a non-public view of
 * a public one does not, and the sign-in callback keeps the whole address.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { componentViewIsPublic, expiredSignInUrl, expiryOutcome } from './sessionExpiry'

const PAGE = `/components/${'a'.repeat(8)}-${'b'.repeat(4)}-${'c'.repeat(4)}-${'d'.repeat(4)}-${'e'.repeat(12)}`

test('a public piece, a published version, no layout: the view is public', () => {
  assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus: 'published' }), true)
  assert.equal(componentViewIsPublic({
    isPublic: true, snapshotStatus: 'published', recordStatuses: ['published', 'published'],
  }), true)
  // the records may still load: the view is public until one says otherwise
  assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus: 'published', recordStatuses: null }), true)
})

test('a private piece is not public', () => {
  assert.equal(componentViewIsPublic({ isPublic: false, snapshotStatus: 'published' }), false)
  assert.equal(componentViewIsPublic({ isPublic: undefined, snapshotStatus: 'published' }), false)
})

test('a draft or pending version on a public piece is not public', () => {
  for (const snapshotStatus of ['draft', 'pending', 'rejected', 'withdrawn', undefined, null]) {
    assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus }), false, String(snapshotStatus))
  }
})

test('a layout opened by ?layout= on a public piece is not public', () => {
  assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus: 'published', layoutId: 'abc' }), false)
  assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus: 'published', layoutId: '' }), true)
})

test('a record only the signed-in user sees makes the view not public', () => {
  assert.equal(componentViewIsPublic({
    isPublic: true, snapshotStatus: 'published', recordStatuses: ['published', 'draft'],
  }), false)
  assert.equal(componentViewIsPublic({
    isPublic: true, snapshotStatus: 'published', recordStatuses: ['pending'],
  }), false)
})

test('your own draft, pending or rejected version on a public piece is not public', () => {
  const live = { status: 'published', name: 'Beam' }
  assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus: 'published', snapshots: [live] }), true)
  for (const status of ['draft', 'pending', 'rejected']) {
    assert.equal(componentViewIsPublic({
      isPublic: true, snapshotStatus: 'published', snapshots: [live, { status, name: 'Beam' }],
    }), false, status)
  }
})

test('a withdrawn row with an author is a full row, with a name or without', () => {
  const full = (extra: Record<string, string | null>) => componentViewIsPublic({
    isPublic: true, snapshotStatus: 'published', snapshots: [{ status: 'withdrawn', name: null, ...extra }],
  })
  assert.equal(full({ added_by_user_id: 'u1' }), false)
  assert.equal(full({ added_by_username: 'someone' }), false)
  assert.equal(full({ name: 'Beam' }), false)
  assert.equal(full({ added_by_user_id: null, added_by_username: null }), true)
})

test('a withdrawn version in full is not public, the public tombstone is', () => {
  const tombstone = { status: 'withdrawn', name: null }
  const full = { status: 'withdrawn', name: 'Beam' }
  assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus: 'published', snapshots: [tombstone] }), true)
  assert.equal(componentViewIsPublic({
    isPublic: true, snapshotStatus: 'published', snapshots: [{ status: 'withdrawn' }],
  }), true)
  assert.equal(componentViewIsPublic({ isPublic: true, snapshotStatus: 'published', snapshots: [full] }), false)
})

test('a public view of a component page goes on as an anonymous visitor, any other view goes to sign-in', () => {
  assert.equal(expiryOutcome(PAGE, { publicToAnonymous: true }), 'anonymous')
  assert.equal(expiryOutcome(PAGE, { publicToAnonymous: false }), 'sign-in')
  // nothing reported: an access notice, a piece without a published version
  assert.equal(expiryOutcome(PAGE, null), 'sign-in')
})

test('a page that is no component page always goes to sign-in', () => {
  for (const path of ['/components', '/my-work', `${PAGE}/edit`, '/components/location-map', '/']) {
    assert.equal(expiryOutcome(path, { publicToAnonymous: true }), 'sign-in', path)
  }
})

test('the view of a draft, a layout or a private piece goes to sign-in, a plain public one does not', () => {
  const outcome = (input: Parameters<typeof componentViewIsPublic>[0]) =>
    expiryOutcome(PAGE, { publicToAnonymous: componentViewIsPublic(input) })
  assert.equal(outcome({ isPublic: true, snapshotStatus: 'published' }), 'anonymous')
  assert.equal(outcome({ isPublic: false, snapshotStatus: 'published' }), 'sign-in')
  assert.equal(outcome({ isPublic: true, snapshotStatus: 'draft' }), 'sign-in')
  assert.equal(outcome({ isPublic: true, snapshotStatus: 'published', layoutId: 'l1' }), 'sign-in')
  assert.equal(outcome({ isPublic: true, snapshotStatus: 'published', snapshots: [{ status: 'pending', name: 'x' }] }), 'sign-in')
})

test('the sign-in address keeps the query and the hash of a component page', () => {
  const url = expiredSignInUrl(PAGE, '?snapshot=s1&layout=l1', '#component-viewer')
  const parsed = new URL(url, 'http://x')
  assert.equal(parsed.pathname, '/auth/signin')
  assert.equal(parsed.searchParams.get('error'), 'SessionExpired')
  assert.equal(parsed.searchParams.get('callbackUrl'), `${PAGE}?snapshot=s1&layout=l1#component-viewer`)
})

test('the sign-in address of other pages has no callback', () => {
  assert.equal(expiredSignInUrl('/my-work', '?a=1', '#x'), '/auth/signin?error=SessionExpired')
})
