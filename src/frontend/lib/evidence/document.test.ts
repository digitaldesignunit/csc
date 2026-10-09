/**
 * The document a record cites: the link is shown as its host and only
 * http(s) links are links (decision 8.106).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { documentOf, safeHref } from '@/lib/evidence/document'

test('only http and https links are links, shown by their host', () => {
  assert.deepEqual(safeHref('https://www.example.org/a/b.pdf?x=1'), {
    href: 'https://www.example.org/a/b.pdf?x=1', host: 'example.org' })
  assert.equal(safeHref('http://example.org/')?.host, 'example.org')
  for (const bad of ['javascript:alert(1)', 'ftp://example.org/a', 'data:text/html,x', '/relative', 'not a url', '', null, 5]) {
    assert.equal(safeHref(bad), null, String(bad))
  }
})

test('the document of a payload carries title, link and the day it was read', () => {
  const ref = documentOf({ document: { title: ' Profile drawing ', url: 'https://example.org/p.pdf', retrieved_at: '2026-10-05' } })
  assert.equal(ref?.title, 'Profile drawing')
  assert.equal(ref?.host, 'example.org')
  assert.equal(ref?.retrievedAt, '2026-10-05')
  // a stored link that is not http(s) is no link
  assert.equal(documentOf({ document: { title: 'x', url: 'javascript:alert(1)' } })?.href, null)
  assert.equal(documentOf({ observations: [] }), null)
  assert.equal(documentOf(null), null)
})
