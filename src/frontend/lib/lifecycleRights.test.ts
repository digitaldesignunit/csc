/**
 * The lifecycle buttons of a version and of an evidence record (8.18, 8.190,
 * 8.193, 8.195), each value read off `permissions.py` and the 409 of the route.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { attachmentButtons, evidenceButtons, snapshotButtons, type CallerFacts } from './lifecycleRights'

const NOBODY: CallerFacts = { isAuthor: false, isAdmin: false, isModerator: false, isContributor: false }
const AUTHOR: CallerFacts = { ...NOBODY, isAuthor: true, isContributor: true }
const CONTRIBUTOR: CallerFacts = { ...NOBODY, isContributor: true }
const MODERATOR: CallerFacts = { ...NOBODY, isModerator: true, isContributor: true }
const ADMIN: CallerFacts = { isAuthor: false, isAdmin: true, isModerator: true, isContributor: true }

const snap = (who: CallerFacts, status: string, over: Partial<Parameters<typeof snapshotButtons>[0]> = {}) =>
  snapshotButtons({ ...who, status, superseded: false, isCurrent: false, hasOpenSnapshot: false, ...over })
const evid = (who: CallerFacts, status: string, over: Partial<Parameters<typeof evidenceButtons>[0]> = {}) =>
  evidenceButtons({ ...who, status, superseded: false, hasOpenCorrection: false, identityWithdrawn: false, ...over })

// VERSIONS --------------------------------------------------------------------
test('the author submits a draft, recalls a pending version and returns a rejected one to draft', () => {
  assert.equal(snap(AUTHOR, 'draft').submit, true)
  assert.equal(snap(AUTHOR, 'pending').recall, true)
  assert.equal(snap(AUTHOR, 'rejected').resubmit, true)
  assert.equal(snap(AUTHOR, 'published').submit, false)
})

test('a moderator who is not the author does not submit, recall or return to draft (`_author`)', () => {
  assert.equal(snap(MODERATOR, 'draft').submit, false)
  assert.equal(snap(MODERATOR, 'pending').recall, false)
  assert.equal(snap(MODERATOR, 'rejected').resubmit, false)
})

test('a site admin does these for another person version (the admin shortcut, #48 case 6)', () => {
  assert.equal(snap(ADMIN, 'draft').submit, true)
  assert.equal(snap(ADMIN, 'pending').recall, true)
  assert.equal(snap(ADMIN, 'rejected').resubmit, true)
})

test('back to draft waits while another version is open (I3b, 8.195)', () => {
  assert.equal(snap(AUTHOR, 'rejected', { hasOpenSnapshot: true }).resubmit, false)
  assert.equal(snap(ADMIN, 'rejected', { hasOpenSnapshot: true }).resubmit, false)
})

test('a correction of a live version needs the contributor role and no open version', () => {
  assert.equal(snap(CONTRIBUTOR, 'published').correct, true)
  assert.equal(snap(CONTRIBUTOR, 'published', { hasOpenSnapshot: true }).correct, false)
  assert.equal(snap(CONTRIBUTOR, 'published', { superseded: true }).correct, false)
  assert.equal(snap(CONTRIBUTOR, 'withdrawn').correct, false)
  assert.equal(snap(NOBODY, 'published').correct, false)
})

test('publish and reject are the moderator rights; a first publish stops where a parent dataset is not moderated (8.8)', () => {
  assert.equal(snap(MODERATOR, 'pending').publish, true)
  assert.equal(snap(MODERATOR, 'pending').reject, true)
  assert.equal(snap(MODERATOR, 'pending', { publishBlock: 'no' }).publish, false)
  assert.equal(snap(MODERATOR, 'pending', { publishBlock: 'no' }).reject, true)
  assert.equal(snap(AUTHOR, 'pending').publish, false)
})

test('promote, withdraw, reinstate and delete', () => {
  assert.equal(snap(MODERATOR, 'published').promote, true)
  assert.equal(snap(MODERATOR, 'published', { isCurrent: true }).promote, false)
  assert.equal(snap(MODERATOR, 'published').withdraw, true)
  assert.equal(snap(MODERATOR, 'withdrawn').reinstate, true)
  assert.equal(snap(AUTHOR, 'draft').delete, true)
  assert.equal(snap(CONTRIBUTOR, 'draft').delete, false)
  assert.equal(snap(MODERATOR, 'rejected').delete, true)
  assert.equal(snap(MODERATOR, 'published').delete, false)
})

// EVIDENCE --------------------------------------------------------------------
test('a withdrawn element: no submit, publish, promote, correct or reinstate; the other steps stay (8.190)', () => {
  const w = { identityWithdrawn: true }
  assert.equal(snap(AUTHOR, 'draft', w).submit, false)
  assert.equal(snap(ADMIN, 'draft', w).submit, false)
  assert.equal(snap(MODERATOR, 'pending', w).publish, false)
  assert.equal(snap(ADMIN, 'pending', w).publish, false)
  assert.equal(snap(MODERATOR, 'published', w).promote, false)
  assert.equal(snap(MODERATOR, 'published', w).correct, false)
  // a version is reinstated after the element (the route answers 409 before)
  assert.equal(snap(MODERATOR, 'withdrawn', w).reinstate, false)
  assert.equal(snap(ADMIN, 'withdrawn', w).reinstate, false)
  // recall, reject, back to draft, delete and withdraw stay
  assert.equal(snap(AUTHOR, 'pending', w).recall, true)
  assert.equal(snap(MODERATOR, 'pending', w).reject, true)
  assert.equal(snap(AUTHOR, 'rejected', w).resubmit, true)
  assert.equal(snap(AUTHOR, 'draft', w).delete, true)
  assert.equal(snap(MODERATOR, 'published', w).withdraw, true)
  // reinstated: the same facts offer them again
  assert.equal(snap(MODERATOR, 'withdrawn', { identityWithdrawn: false }).reinstate, true)
  const back = { identityWithdrawn: false }
  assert.equal(snap(AUTHOR, 'draft', back).submit, true)
  assert.equal(snap(MODERATOR, 'pending', back).publish, true)
  assert.equal(snap(MODERATOR, 'published', back).promote, true)
})

test('only the author submits an evidence draft, not a moderator who did not write it (#46)', () => {
  assert.equal(evid(AUTHOR, 'draft').submit, true)
  assert.equal(evid({ ...MODERATOR, isAuthor: true }, 'draft').submit, true)
  assert.equal(evid(MODERATOR, 'draft').submit, false)
  assert.equal(evid(ADMIN, 'draft').submit, true)
})

test('recall and back to draft are for the author and the admin', () => {
  assert.equal(evid(AUTHOR, 'pending').recall, true)
  assert.equal(evid(MODERATOR, 'pending').recall, false)
  assert.equal(evid(ADMIN, 'pending').recall, true)
  assert.equal(evid(AUTHOR, 'rejected').resubmit, true)
  assert.equal(evid(MODERATOR, 'rejected').resubmit, false)
  assert.equal(evid(ADMIN, 'rejected').resubmit, true)
})

test('a moderator edits a draft and a pending record, the author only a draft', () => {
  assert.equal(evid(MODERATOR, 'draft').edit, true)
  assert.equal(evid(MODERATOR, 'pending').edit, true)
  assert.equal(evid(AUTHOR, 'draft').edit, true)
  assert.equal(evid(AUTHOR, 'pending').edit, false)
  assert.equal(evid(MODERATOR, 'published').edit, false)
})

test('"Correct" waits while a correction is open and is not offered on a withdrawn element (I14, I28, 8.195)', () => {
  assert.equal(evid(CONTRIBUTOR, 'published').correct, true)
  assert.equal(evid(CONTRIBUTOR, 'published', { hasOpenCorrection: true }).correct, false)
  assert.equal(evid(CONTRIBUTOR, 'published', { identityWithdrawn: true }).correct, false)
  assert.equal(evid(CONTRIBUTOR, 'published', { superseded: true }).correct, false)
  assert.equal(evid(NOBODY, 'published').correct, false)
})

test('on a withdrawn element submit, edit and publish are off, the rest stays (I28, M3)', () => {
  const gone = { identityWithdrawn: true }
  assert.equal(evid(AUTHOR, 'draft', gone).submit, false)
  assert.equal(evid(ADMIN, 'draft', gone).submit, false)
  assert.equal(evid(MODERATOR, 'draft', gone).edit, false)
  assert.equal(evid(MODERATOR, 'pending', gone).edit, false)
  assert.equal(evid(MODERATOR, 'pending', gone).publish, false)
  // a moderator still rejects, the author recalls and returns to draft, both delete
  assert.equal(evid(MODERATOR, 'pending', gone).reject, true)
  assert.equal(evid(AUTHOR, 'pending', gone).recall, true)
  assert.equal(evid(AUTHOR, 'rejected', gone).resubmit, true)
  assert.equal(evid(AUTHOR, 'draft', gone).delete, true)
  assert.equal(evid(MODERATOR, 'published', gone).withdraw, true)
  // a withdrawn record is reinstated after the element: the route answers 409 (8.190)
  assert.equal(evid(MODERATOR, 'withdrawn', gone).reinstate, false)
  assert.equal(evid(ADMIN, 'withdrawn', gone).reinstate, false)
  assert.equal(evid(MODERATOR, 'withdrawn').reinstate, true)
})

test('publish, reject, withdraw, reinstate and delete of a record', () => {
  assert.equal(evid(MODERATOR, 'pending').publish, true)
  assert.equal(evid(MODERATOR, 'pending').reject, true)
  assert.equal(evid(MODERATOR, 'published').withdraw, true)
  assert.equal(evid(MODERATOR, 'withdrawn').reinstate, true)
  assert.equal(evid(AUTHOR, 'draft').delete, true)
  assert.equal(evid(CONTRIBUTOR, 'draft').delete, false)
})

// ATTACHMENTS -----------------------------------------------------------------
const att = (who: CallerFacts, status: string, over: Partial<Parameters<typeof attachmentButtons>[0]> = {}) =>
  attachmentButtons({ ...who, status, correction: false, identityWithdrawn: false, ...over })

test('before publish the files follow the editors of the record (`_file_editor`)', () => {
  assert.deepEqual(att(AUTHOR, 'draft'), { add: true, remove: true })
  assert.deepEqual(att(CONTRIBUTOR, 'draft'), { add: false, remove: false })
  assert.deepEqual(att(MODERATOR, 'draft'), { add: true, remove: true })
  assert.deepEqual(att(MODERATOR, 'pending'), { add: true, remove: true })
  assert.deepEqual(att(AUTHOR, 'pending'), { add: false, remove: false })
})

test('the author of a pending correction adds and removes files while it waits (8.142 a)', () => {
  assert.deepEqual(att(AUTHOR, 'pending', { correction: true }), { add: true, remove: true })
})

test('a rejected record has no file editor, a site admin apart (#46)', () => {
  assert.deepEqual(att(AUTHOR, 'rejected'), { add: false, remove: false })
  assert.deepEqual(att(MODERATOR, 'rejected'), { add: false, remove: false })
  assert.deepEqual(att(ADMIN, 'rejected'), { add: true, remove: true })
})

test('after publish a contributor or a moderator adds, a moderator removes (#48 case 1)', () => {
  assert.deepEqual(att(CONTRIBUTOR, 'published'), { add: true, remove: false })
  const moderatorOnly: CallerFacts = { ...NOBODY, isModerator: true }
  assert.deepEqual(att(moderatorOnly, 'published'), { add: true, remove: true })
  assert.deepEqual(att(NOBODY, 'published'), { add: false, remove: false })
})

test('nobody adds to a withdrawn record or to a record of a withdrawn element, an admin included (8.190)', () => {
  for (const who of [CONTRIBUTOR, MODERATOR, ADMIN]) {
    assert.equal(att(who, 'withdrawn').add, false)
    assert.equal(att(who, 'published', { identityWithdrawn: true }).add, false)
    assert.equal(att(who, 'draft', { identityWithdrawn: true }).add, false)
  }
  // removing is not part of that
  assert.equal(att(MODERATOR, 'withdrawn').remove, true)
  assert.equal(att(ADMIN, 'published', { identityWithdrawn: true }).remove, true)
})
