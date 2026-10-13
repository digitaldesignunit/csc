/**
 * The member editor copes with a member row without an address (8.144 d) and
 * does not promise a direct add where the dataset invites only.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { addMemberHint, memberLabel, memberLine } from './members'

test('a member row with and without an address', () => {
  assert.equal(memberLine({ user_id: 'u1', username: 'sample', email: 'sample@example.org' }), 'sample \u00b7 sample@example.org')
  assert.equal(memberLine({ user_id: 'u1', username: 'sample' }), 'sample')
  assert.equal(memberLine({ user_id: 'u1', username: 'sample', email: null }), 'sample')
  assert.equal(memberLine({ user_id: 'u1' }), 'u1')
})

test('a member is named by user name, else address, else a word', () => {
  assert.equal(memberLabel({ user_id: 'u1', username: 'sample', email: 'a@x.org' }), 'sample')
  assert.equal(memberLabel({ user_id: 'u1', email: 'a@x.org' }), 'a@x.org')
  assert.equal(memberLabel({ user_id: 'u1' }), 'this person')
})

test('the hint says invitation only for a moderator of an unreviewed dataset', () => {
  assert.match(addMemberHint(true, false), /added right away/)
  assert.match(addMemberHint(undefined, false), /added right away/)
  assert.match(addMemberHint(false, true), /added right away/)
  const invite = addMemberHint(false, false)
  assert.match(invite, /invitation/)
  assert.ok(!/added right away/.test(invite))
})
