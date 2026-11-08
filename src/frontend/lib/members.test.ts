/**
 * The member editor copes with a member row without an address (8.144 d) and
 * does not promise a direct add where the dataset invites only.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { addMemberHint, deleteDatasetReason, lastModeratorReason, memberLabel, memberLine } from './members'

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

test('the last moderator cannot be removed or demoted by a moderator (8.139 g); an admin can', () => {
  const members = [
    { user_id: 'a', roles: ['moderator', 'contributor'] },
    { user_id: 'b', roles: ['contributor'] },
  ]
  assert.match(lastModeratorReason(members, members[0], false) ?? '', /at least one moderator/)
  assert.equal(lastModeratorReason(members, members[0], true), null)
  assert.equal(lastModeratorReason(members, members[1], false), null)
  // with a second moderator nobody is locked
  const two = [...members, { user_id: 'c', roles: ['moderator'] }]
  assert.equal(lastModeratorReason(two, two[0], false), null)
  assert.equal(lastModeratorReason(two, two[2], false), null)
})

test('deleting a dataset: a published element the caller sees is a sure refusal, a count of zero is not', () => {
  assert.equal(deleteDatasetReason(0), null)
  assert.equal(deleteDatasetReason(null), null)
  assert.equal(deleteDatasetReason(undefined), null)
  assert.match(deleteDatasetReason(1) ?? '', /1 published component:/)
  assert.match(deleteDatasetReason(3) ?? '', /3 published components:/)
})
