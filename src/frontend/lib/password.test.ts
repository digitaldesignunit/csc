import assert from 'node:assert/strict'
import { test } from 'node:test'

import { passwordProblem } from './password'

test('a password needs 8 characters and at most 72 bytes', () => {
  assert.match(passwordProblem('short') ?? '', /at least 8/)
  assert.equal(passwordProblem('long enough'), null)
  assert.equal(passwordProblem('x'.repeat(72)), null)
  assert.match(passwordProblem('x'.repeat(73)) ?? '', /at most 72 bytes/)
  // umlauts take two bytes: 37 of them are 74 bytes
  assert.match(passwordProblem('\u00e4'.repeat(37)) ?? '', /at most 72 bytes/)
  assert.equal(passwordProblem('\u00e4'.repeat(36)), null)
})
