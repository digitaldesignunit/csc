/**
 * Server-side backend calls (8.144, review F3): the target is FASTAPI_URL, never
 * a base built from the request's Host header; the token, the client header and
 * the visitor's address are added.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { backendRequest } from './serverBackend'

test('the target is the configured backend, whatever the request headers say', () => {
  const evil = new Headers({ host: 'evil.example', 'x-forwarded-proto': 'https', 'x-forwarded-host': 'evil.example' })
  const call = backendRequest('http://127.0.0.1:8000/', '/identities/count?circulation=in', undefined, evil)
  assert.equal(call.url, 'http://127.0.0.1:8000/identities/count?circulation=in')
})

test('the token, the client header and the visitor address go along', () => {
  const call = backendRequest('http://b.test', '/datasets', 'tok', new Headers({ 'x-forwarded-for': '6.6.6.6, 203.0.113.9' }))
  assert.equal(call.headers.Authorization, 'Bearer tok')
  assert.match(call.headers['X-CSC-Client'], /^web\//)
  assert.equal(call.headers['X-Forwarded-For'], '203.0.113.9')
})

test('an anonymous visitor sends no Authorization header and no cookie', () => {
  const call = backendRequest('http://b.test', '/datasets', undefined, new Headers({ cookie: 'next-auth.session-token=abc' }))
  assert.ok(!('Authorization' in call.headers))
  assert.ok(!Object.keys(call.headers).some((k) => k.toLowerCase() === 'cookie'))
})

test('a path that could change the host is refused', () => {
  for (const path of ['//evil.example/x', 'evil.example/x', 'http://evil.example/', '@evil.example']) {
    assert.throws(() => backendRequest('http://b.test', path, undefined, new Headers()), /one slash/)
  }
})
