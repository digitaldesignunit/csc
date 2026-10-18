import assert from 'node:assert/strict'
import { test } from 'node:test'

import { uploadErrorText } from './uploadError'

test('a 413 from the proxy or the backend reads as a plain sentence', () => {
  assert.match(uploadErrorText(413, '{"error":"Request too large"}'), /too large/)
  assert.match(uploadErrorText(413, '{"detail":"The request is too large; the limit here is 11 MB."}'), /too large/)
})

test('other answers show their text, not the JSON', () => {
  assert.equal(uploadErrorText(415, '{"detail":"Use JPEG, PNG, or WebP."}'), 'Use JPEG, PNG, or WebP.')
  assert.equal(uploadErrorText(500, 'plain text'), 'plain text')
  assert.equal(uploadErrorText(502, ''), 'Upload failed (502)')
})
