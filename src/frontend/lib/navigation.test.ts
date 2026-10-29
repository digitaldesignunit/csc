import assert from 'node:assert/strict'
import { test } from 'node:test'

import { pageTitle, visibleNav } from './navigation'

const ids = (viewer: Parameters<typeof visibleNav>[0]) =>
  visibleNav(viewer).flatMap((group) => group.entries.map((e) => e.id))

const NOBODY = { signedIn: false, isAdmin: false, isModerator: false, isReviewer: false }
const USER = { ...NOBODY, signedIn: true }

test('an anonymous visitor sees the public tier and the way in (8.118 Q8)', () => {
  assert.deepEqual(ids(NOBODY), ['browse', 'similarity-map', 'location-map', 'analytics', 'gh', 'reference', 'api-docs', 'signin'])
})

test('a signed-in user has no Sign in and gets Capture and My work', () => {
  assert.deepEqual(ids(USER), ['browse', 'similarity-map', 'location-map', 'analytics', 'scan', 'add', 'mywork', 'gh', 'reference', 'api-docs'])
})

test('moderation entries follow the roles', () => {
  assert.ok(ids({ ...USER, isModerator: true }).includes('queue'))
  assert.ok(ids({ ...USER, isModerator: true }).includes('datasets'))
  const reviewer = ids({ ...USER, isReviewer: true })
  assert.ok(reviewer.includes('queue'))
  assert.ok(!reviewer.includes('datasets'))
})

test('an admin has eighteen entries, the access tokens among them', () => {
  assert.equal(ids({ ...USER, isAdmin: true }).length, 18)
  assert.ok(ids({ ...USER, isAdmin: true }).includes('access-tokens'))
  assert.ok(!ids({ ...USER, isModerator: true }).includes('access-tokens'))
})

test('the Data Model page is in Tools next to Grasshopper, for anyone, and has its title (8.181 c)', () => {
  for (const viewer of [NOBODY, USER, { ...USER, isAdmin: true }]) {
    const tools = visibleNav(viewer).find((group) => group.id === 'tools')
    assert.deepEqual(tools?.entries.map((e) => e.id).slice(0, 2), ['gh', 'reference'])
    const entry = tools?.entries.find((e) => e.id === 'reference')
    assert.equal(entry?.href, '/reference')
    assert.equal(entry?.label, 'Data Model')
  }
  assert.equal(pageTitle('/reference', new URLSearchParams()), 'Data Model')
})

test('the forms of a component are titled Component, not Browse', () => {
  const none = new URLSearchParams()
  assert.equal(pageTitle('/components/abc/snapshot/new', none), 'Component')
  assert.equal(pageTitle('/components/abc/evidence/new', none), 'Add evidence')
  assert.equal(pageTitle('/components', none), 'Browse')
  // the two maps are pages of their own, not a component
  assert.equal(pageTitle('/components/similarity-map', none), 'Similarity Map')
  assert.equal(pageTitle('/components/location-map', none), 'Location Map')
  assert.equal(pageTitle('/components/location-map', new URLSearchParams('layer=origin')), 'Location Map')
})
