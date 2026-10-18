import assert from 'node:assert/strict'
import { test } from 'node:test'

import { usernameProblem } from './username'

test('a username is 3 to 32 of a-z 0-9 . _ - and starts with a letter or digit', () => {
  for (const ok of ['abc', 'a.b', 'sample-user', 'user_01', '9lives', 'x'.repeat(32), 'Sample.User']) {
    assert.equal(usernameProblem(ok), null, ok)
  }
  for (const bad of ['ab', 'x'.repeat(33), '.abc', '-abc', '_abc', 'a b c', 'ab\u00e4', 'a@b.c', 'a/b/c', '']) {
    assert.notEqual(usernameProblem(bad), null, bad)
  }
})
