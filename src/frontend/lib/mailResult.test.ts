import assert from 'node:assert/strict'
import { test } from 'node:test'

import { memberNotice, resendNotice, summariseInvitations } from './mailResult'

test('a failed mail is told apart from a sent one and from an existing account', () => {
  const summary = summariseInvitations([
    { email: 'a@x.org', result: 'invited' },
    { email: 'b@x.org', result: 'mail_failed' },
    { email: 'c@x.org', result: 'exists' },
  ])
  assert.deepEqual(summary.sent, ['a@x.org'])
  assert.deepEqual(summary.failed, ['b@x.org'])
  assert.deepEqual(summary.existing, ['c@x.org'])
  assert.equal(summary.warning, true)
  assert.match(summary.toast, /1 invitation sent; 1 mail could not be sent: use Resend/)
  const clean = summariseInvitations([{ email: 'a@x.org', result: 'invited' }])
  assert.equal(clean.warning, false)
  assert.equal(clean.toast, '1 invitation sent')
})

test('the member editor says when the notice did not go out and that the membership stands', () => {
  const added = memberNotice({ email: 'a@x.org', result: 'added', mail_failed: true })
  assert.equal(added.warning, true)
  assert.match(added.text, /membership stands/)
  assert.equal(memberNotice({ email: 'a@x.org', result: 'added', mail_failed: false }).text, 'a@x.org added and notified')
  const invited = memberNotice({ email: 'n@x.org', result: 'invited', mail_failed: true })
  assert.equal(invited.warning, true)
  assert.match(invited.text, /Use Resend/)
  assert.equal(memberNotice({ email: 'n@x.org', result: 'invited' }).warning, false)
})

test('Resend says that the old link no longer works', () => {
  assert.match(resendNotice({ email: 'a@x.org', result: 'invited' }).text, /old link no longer works/)
  const failed = resendNotice({ email: 'a@x.org', result: 'mail_failed' })
  assert.equal(failed.warning, true)
  assert.match(failed.text, /previous link no longer works/)
})
