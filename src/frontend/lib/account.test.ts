import assert from 'node:assert/strict'
import { test } from 'node:test'

import { accountRows, membershipLine } from './account'

test('the account shows username, name when there is one, e-mail and an admin role', () => {
  assert.deepEqual(accountRows({ username: 'u1', full_name: ' Ada ', email: 'a@example.org', role: 'user' }), [
    { label: 'Username', value: 'u1' },
    { label: 'Name', value: 'Ada' },
    { label: 'E-mail', value: 'a@example.org' },
  ])
  assert.deepEqual(accountRows({ username: 'u2', email: null, role: 'admin' }), [
    { label: 'Username', value: 'u2' },
    { label: 'E-mail', value: 'Not stated' },
    { label: 'Role', value: 'Administrator' },
  ])
})

test('a membership line names the dataset and the roles', () => {
  assert.equal(membershipLine({ dataset: 'dbu_zirkus', name: 'ZirKuS', roles: ['contributor', 'moderator'] }), 'ZirKuS: contributor, moderator')
  assert.equal(membershipLine({ dataset: 'x', name: '', roles: [] }), 'x: no role')
})
