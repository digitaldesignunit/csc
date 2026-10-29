/**
 * The return address after sign-in only accepts addresses on this site (8.182 b).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { safeCallbackPath } from './safeCallback'

const FALLBACK = '/my-work'

test('a path of this site is kept with its query and hash', () => {
  assert.equal(safeCallbackPath('/components/x?snapshot=a#h', FALLBACK), '/components/x?snapshot=a#h')
  assert.equal(safeCallbackPath('/components', FALLBACK), '/components')
  assert.equal(safeCallbackPath('/', FALLBACK), '/')
  assert.equal(
    safeCallbackPath('/components/abc?snapshot=1&layout=2#component-viewer', FALLBACK),
    '/components/abc?snapshot=1&layout=2#component-viewer',
  )
  // a path that only looks odd stays on this site
  assert.equal(safeCallbackPath('/a//b', FALLBACK), '/a//b')
  assert.equal(safeCallbackPath('/x?next=//evil.com', FALLBACK), '/x?next=//evil.com')
})

test('an address on another site is the fallback', () => {
  for (const bad of [
    '//evil.com', '//evil.com/path', '///evil.com', '/\\evil.com', '/\\/evil.com', '\\\\evil.com',
    'https://evil.com', 'http://evil.com/x', 'HTTPS://EVIL.COM', 'javascript:alert(1)', 'data:text/html,x',
    'evil.com', 'components', ' /components', '/\t/evil.com', '/\n/evil.com', '/\r/evil.com',
  ]) {
    assert.equal(safeCallbackPath(bad, FALLBACK), FALLBACK, JSON.stringify(bad))
  }
})

test('nothing, an empty text or a list is read like the first value', () => {
  assert.equal(safeCallbackPath(undefined, FALLBACK), FALLBACK)
  assert.equal(safeCallbackPath(null, FALLBACK), FALLBACK)
  assert.equal(safeCallbackPath('', FALLBACK), FALLBACK)
  assert.equal(safeCallbackPath([], FALLBACK), FALLBACK)
  assert.equal(safeCallbackPath(['/components', '//evil.com'], FALLBACK), '/components')
  assert.equal(safeCallbackPath(['//evil.com', '/components'], FALLBACK), FALLBACK)
})

test('the origin of the browser is the one checked against', () => {
  assert.equal(safeCallbackPath('/components?x=1', FALLBACK, 'https://csc.example.org'), '/components?x=1')
  assert.equal(safeCallbackPath('//csc.example.org/x', FALLBACK, 'https://csc.example.org'), FALLBACK)
  assert.equal(safeCallbackPath('https://csc.example.org/x', FALLBACK, 'https://csc.example.org'), FALLBACK)
})
