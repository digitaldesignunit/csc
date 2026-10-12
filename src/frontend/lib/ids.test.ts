import assert from 'node:assert/strict'
import test from 'node:test'

import { shortId } from '@/lib/ids'

test('a long id is cut to its first eight characters', () => {
  assert.equal(shortId('0b6f1d2e-aaaa-bbbb-cccc-1234567890ab'), '0b6f1d2e')
})

test('a short or empty id is kept', () => {
  assert.equal(shortId('abc'), 'abc')
  assert.equal(shortId(''), '')
  assert.equal(shortId('  abc '), 'abc')
})
