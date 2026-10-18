import assert from 'node:assert/strict'
import { test } from 'node:test'

import { READ_ONLY_BANNER, READ_ONLY_POLL_MS, READ_ONLY_TITLE, parseReadOnly } from './readOnly'

test('only read_only: true switches the read-only state on', () => {
  assert.equal(parseReadOnly({ version: '0.6.2.0', read_only: true }), true)
  for (const off of [{ read_only: false }, { version: '0.6.1.1' }, { read_only: 'true' }, { read_only: 1 }, null, undefined, 'x', []]) {
    assert.equal(parseReadOnly(off), false, JSON.stringify(off))
  }
})

test('the texts are ASCII and the poll is not faster than once a few seconds', () => {
  for (const text of [READ_ONLY_BANNER, READ_ONLY_TITLE]) {
    assert.ok(/^[\x20-\x7e]+$/.test(text), text)
  }
  assert.ok(READ_ONLY_POLL_MS >= 30_000)
})
