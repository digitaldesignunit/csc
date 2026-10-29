/**
 * Who may add and remove the photos of an existing version (8.184): the whole
 * table, each value read off `_add_photo` / `_remove_photo` in
 * `apps/catalog/permissions.py`.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { photoRights, type PhotoRightsInput } from './photoRights'

const AUTHOR = 'u-author'
const OTHER = 'u-other'

type Caller = Pick<PhotoRightsInput, 'signedIn' | 'userId' | 'isAdmin' | 'roles'>

const CALLERS: Record<string, Caller> = {
  anonymous: { signedIn: false, userId: null, isAdmin: false, roles: [] },
  'signed-in non-member': { signedIn: true, userId: OTHER, isAdmin: false, roles: [] },
  'viewer-only member': { signedIn: true, userId: OTHER, isAdmin: false, roles: ['reviewer'] },
  'contributor, author': { signedIn: true, userId: AUTHOR, isAdmin: false, roles: ['contributor'] },
  'contributor, not author': { signedIn: true, userId: OTHER, isAdmin: false, roles: ['contributor'] },
  moderator: { signedIn: true, userId: OTHER, isAdmin: false, roles: ['contributor', 'moderator'] },
  'site admin': { signedIn: true, userId: OTHER, isAdmin: true, roles: ['contributor', 'reviewer', 'moderator'] },
}

// [add, remove] per caller, in the order of CALLERS
const TABLE: Record<string, Array<[boolean, boolean]>> = {
  // `_file_editor` = `_unpublished_editor`: a draft --- author or moderator
  draft: [[false, false], [false, false], [false, false], [true, true], [false, false], [true, true], [true, true]],
  // a pending version --- a moderator only (not its author)
  pending: [[false, false], [false, false], [false, false], [false, false], [false, false], [true, true], [true, true]],
  // a rejected version --- nobody but the site admin
  rejected: [[false, false], [false, false], [false, false], [false, false], [false, false], [false, false], [true, true]],
  // after publish: add --- contributor or moderator; remove --- moderator
  published: [[false, false], [false, false], [false, false], [true, false], [true, false], [true, true], [true, true]],
  // `_unpublished` is false for a withdrawn version, so it follows the after-publish branch
  withdrawn: [[false, false], [false, false], [false, false], [true, false], [true, false], [true, true], [true, true]],
}

for (const [status, rows] of Object.entries(TABLE)) {
  Object.entries(CALLERS).forEach(([name, caller], i) => {
    test(`photos of a ${status} version: ${name}`, () => {
      const [add, remove] = rows[i]
      assert.deepEqual(
        photoRights({ ...caller, status, addedByUserId: AUTHOR }),
        { add, remove },
      )
    })
  })
}

test('the author of a draft edits its files whatever the dataset role (`_author`)', () => {
  const base = { signedIn: true, userId: AUTHOR, isAdmin: false, status: 'draft', addedByUserId: AUTHOR }
  assert.deepEqual(photoRights({ ...base, roles: [] }), { add: true, remove: true })
  assert.deepEqual(photoRights({ ...base, roles: ['reviewer'] }), { add: true, remove: true })
})

test('a moderator without the contributor role may add and remove after publish (`_add_photo` takes either role)', () => {
  const moderator = { signedIn: true, userId: OTHER, isAdmin: false, roles: ['moderator'], status: 'published', addedByUserId: AUTHOR }
  assert.deepEqual(photoRights(moderator), { add: true, remove: true })
})

test('a version without an author or without a viewer id matches nobody as author', () => {
  const base = { signedIn: true, isAdmin: false, roles: ['contributor'], status: 'draft' }
  assert.deepEqual(photoRights({ ...base, userId: null, addedByUserId: null }), { add: false, remove: false })
  assert.deepEqual(photoRights({ ...base, userId: undefined, addedByUserId: undefined }), { add: false, remove: false })
  assert.deepEqual(photoRights({ ...base, userId: AUTHOR, addedByUserId: null }), { add: false, remove: false })
})

test('an unknown or missing status is unpublished and has no editor (`_unpublished_editor`)', () => {
  const caller = { signedIn: true, userId: AUTHOR, isAdmin: false, roles: ['moderator'], addedByUserId: AUTHOR }
  assert.deepEqual(photoRights({ ...caller, status: null }), { add: false, remove: false })
  assert.deepEqual(photoRights({ ...caller, status: undefined }), { add: false, remove: false })
})

test('a site admin passes every check, a signed-out caller none', () => {
  for (const status of [...Object.keys(TABLE), null]) {
    assert.deepEqual(
      photoRights({ signedIn: true, isAdmin: true, roles: [], status }),
      { add: true, remove: true },
    )
    assert.deepEqual(
      photoRights({ signedIn: false, isAdmin: true, roles: ['moderator'], status, userId: AUTHOR, addedByUserId: AUTHOR }),
      { add: false, remove: false },
    )
  }
})
