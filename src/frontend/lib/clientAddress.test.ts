/**
 * The visitor's address passed on to the backend (plan P10 review, 8.117 e):
 * the address the proxy in front appended, never what the browser sent.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { clientAddress, forwardedFor, proxyHops } from './clientAddress'

const h = (value?: string) => new Headers(value === undefined ? {} : { 'x-forwarded-for': value })

test('the address is the one the proxy appended, the rightmost', () => {
  assert.equal(clientAddress(h('203.0.113.9'), 1), '203.0.113.9')
  // the browser put 6.6.6.6 in front; the proxy appended the real peer
  assert.equal(clientAddress(h('6.6.6.6, 203.0.113.9'), 1), '203.0.113.9')
  assert.equal(clientAddress(h('2001:db8::7'), 1), '2001:db8::7')
})

test('with two proxies in front the address is the one before the last', () => {
  assert.equal(clientAddress(h('6.6.6.6, 203.0.113.9, 10.0.0.2'), 2), '203.0.113.9')
  assert.equal(clientAddress(h('10.0.0.2'), 2), null)
})

test('no header, no proxy or junk gives no address', () => {
  assert.equal(clientAddress(h(), 1), null)
  assert.equal(clientAddress(h('203.0.113.9'), 0), null)
  assert.equal(clientAddress(h('not-an-address'), 1), null)
  assert.equal(clientAddress(h('1.2.3.4, <script>'), 1), null)
})

test('the headers for the backend are one single entry', () => {
  assert.deepEqual(forwardedFor(h('6.6.6.6, 203.0.113.9'), 1), { 'X-Forwarded-For': '203.0.113.9' })
  assert.deepEqual(forwardedFor(h(), 1), {})
})

test('a plain header object (NextAuth) works like Headers', () => {
  assert.equal(clientAddress({ 'X-Forwarded-For': '6.6.6.6, 203.0.113.9' }, 1), '203.0.113.9')
  assert.equal(clientAddress({ 'x-forwarded-for': ['6.6.6.6', '203.0.113.9'] }, 1), '203.0.113.9')
})

test('the hop count defaults to 1 and ignores nonsense', () => {
  assert.equal(proxyHops(undefined), 1)
  assert.equal(proxyHops('0'), 0)
  assert.equal(proxyHops('2'), 2)
  assert.equal(proxyHops('x'), 1)
  assert.equal(proxyHops('-3'), 1)
})
