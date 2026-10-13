/**
 * The page /invite: the code of the link, the ways to sign in or register and
 * come back, and the words for what the invitation offers (8.144 b).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { inviteCode, invitePath, offerText, registerHref, rolesText, signInHref } from './invite'

test('a code is 16 base32 characters in any case; anything else is not a code', () => {
  assert.equal(inviteCode('abcdefgh23456723'), 'ABCDEFGH23456723')
  assert.equal(inviteCode('  ABCDEFGH23456723 '), 'ABCDEFGH23456723')
  for (const bad of [null, undefined, '', 'short', 'ABCDEFG1ABCDEFGH', '<script>', 'AB CD EF GH']) {
    assert.equal(inviteCode(bad), null, String(bad))
  }
})

test('signing in comes back to the invitation, registering carries the code', () => {
  const code = 'ABCDEFGH23456723'
  assert.equal(invitePath(code), '/invite?code=ABCDEFGH23456723')
  const href = signInHref(code)
  assert.ok(href.startsWith('/auth/signin?callbackUrl='))
  assert.equal(decodeURIComponent(href.split('callbackUrl=')[1]), '/invite?code=ABCDEFGH23456723')
  assert.equal(registerHref(code), '/auth/register?code=ABCDEFGH23456723')
})

test('the roles read as a sentence', () => {
  assert.equal(rolesText([]), 'member')
  assert.equal(rolesText(['reviewer']), 'reviewer')
  assert.equal(rolesText(['contributor', 'reviewer']), 'contributor and reviewer')
  assert.equal(rolesText(['contributor', 'reviewer', 'moderator']), 'contributor, reviewer and moderator')
})

test('the offer names the dataset and the roles, or only the catalogue', () => {
  assert.equal(
    offerText({ dataset_name: 'Sample set', roles: ['contributor'] }),
    'You are invited to the dataset "Sample set" as contributor.')
  assert.equal(offerText({ dataset_name: null, roles: [] }), 'You are invited to the Catalog of Second Chances.')
})
