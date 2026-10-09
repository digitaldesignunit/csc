import assert from 'node:assert/strict'
import { test } from 'node:test'

import { pageTitle, visibleNav } from './navigation'

const ids = (viewer: Parameters<typeof visibleNav>[0]) =>
  visibleNav(viewer).flatMap((group) => group.entries.map((e) => e.id))

const NOBODY = { signedIn: false, isAdmin: false, isModerator: false, isReviewer: false }
const USER = { ...NOBODY, signedIn: true }

test('an anonymous visitor sees the public tier and the way in (8.118 Q8)', () => {
  assert.deepEqual(ids(NOBODY), ['browse', 'map', 'analytics', 'gh', 'api-docs', 'signin'])
})

test('a signed-in user has no Sign in and gets Capture and My work', () => {
  assert.deepEqual(ids(USER), ['browse', 'map', 'analytics', 'scan', 'add', 'mywork', 'gh', 'api-docs'])
})

test('moderation entries follow the roles', () => {
  assert.ok(ids({ ...USER, isModerator: true }).includes('queue'))
  assert.ok(ids({ ...USER, isModerator: true }).includes('datasets'))
  const reviewer = ids({ ...USER, isReviewer: true })
  assert.ok(reviewer.includes('queue'))
  assert.ok(!reviewer.includes('datasets'))
})

test('an admin has fourteen entries', () => {
  assert.equal(ids({ ...USER, isAdmin: true }).length, 14)
})

test('the forms of a component are titled Component, not Browse', () => {
  const none = new URLSearchParams()
  assert.equal(pageTitle('/components/abc/snapshot/new', none), 'Component')
  assert.equal(pageTitle('/components/abc/evidence/new', none), 'Add evidence')
  assert.equal(pageTitle('/components', none), 'Browse')
})
