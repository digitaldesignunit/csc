/**
 * The Content-Security-Policy (decision 8.164): the directives, a fresh nonce
 * per request, one CSP header, no unsafe script sources in production, and the
 * paths the proxy covers and gates.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { config } from '../proxy'
import { MAP_TILE_ORIGIN, buildCsp, cspHeaderName, isReportOnly, newNonce, staticOrigin } from './csp'
import { PROTECTED_PREFIXES, isApiPath, isProtectedPath } from './proxyAuth'

const directives = (policy: string) =>
  Object.fromEntries(policy.split('; ').map((part) => {
    const [name, ...sources] = part.split(' ')
    return [name, sources]
  }))

test('every directive of 8.164 is present, with its sources', () => {
  const d = directives(buildCsp({ nonce: 'abc' }))
  assert.deepEqual(d['default-src'], ["'self'"])
  assert.deepEqual(d['script-src'], ["'self'", "'nonce-abc'", "'strict-dynamic'", "'wasm-unsafe-eval'"])
  assert.deepEqual(d['style-src'], ["'self'", "'unsafe-inline'"])
  // the Location Map's tiles (8.171) are the one addition
  assert.deepEqual(d['img-src'], ["'self'", 'blob:', 'data:', 'https://tile.openstreetmap.de'])
  assert.deepEqual(d['connect-src'], ["'self'"])
  assert.deepEqual(d['font-src'], ["'self'"])
  assert.deepEqual(d['worker-src'], ["'self'", 'blob:'])
  assert.deepEqual(d['media-src'], ["'self'", 'blob:'])
  assert.deepEqual(d['frame-src'], ['https://maps.google.com', 'https://www.google.com'])
  assert.deepEqual(d['object-src'], ["'none'"])
  assert.deepEqual(d['base-uri'], ["'none'"])
  assert.deepEqual(d['form-action'], ["'self'"])
  assert.deepEqual(d['frame-ancestors'], ["'none'"])
  assert.equal(Object.keys(d).length, 13)
})

test('scripts: the nonce, never unsafe-inline; no unsafe-eval or ws: in production', () => {
  const production = buildCsp({ nonce: 'abc' })
  const scripts = directives(production)['script-src']
  assert.ok(!scripts.includes("'unsafe-inline'"))
  assert.ok(!/(?<!wasm-)unsafe-eval/.test(production))   // wasm-unsafe-eval is allowed
  assert.ok(!/\bws:/.test(production))
  // no nonce in style-src: it would switch unsafe-inline off
  assert.ok(!directives(production)['style-src'].some((s) => s.startsWith("'nonce-")))
  // nothing from gstatic
  assert.ok(!production.includes('gstatic'))
})

test('development adds unsafe-eval and ws: for hot reload, and nothing else', () => {
  const dev = directives(buildCsp({ nonce: 'abc', dev: true }))
  const prod = directives(buildCsp({ nonce: 'abc' }))
  assert.deepEqual(dev['script-src'], [...prod['script-src'], "'unsafe-eval'"])
  assert.deepEqual(dev['connect-src'], ["'self'", 'ws:'])
  assert.deepEqual({ ...dev, 'script-src': 0, 'connect-src': 0 }, { ...prod, 'script-src': 0, 'connect-src': 0 })
})

test('the tile host is allowed for images only, and for nothing else', () => {
  assert.equal(MAP_TILE_ORIGIN, 'https://tile.openstreetmap.de')
  const policy = buildCsp({ nonce: 'abc' })
  const d = directives(policy)
  for (const [name, sources] of Object.entries(d)) {
    assert.equal(sources.includes(MAP_TILE_ORIGIN), name === 'img-src', name)
  }
  // no other host appears than the map tiles and the Google embed of 8.164
  const hosts = new Set(policy.match(/https?:\/\/[^\s;]+/g))
  assert.deepEqual([...hosts].sort(), ['https://maps.google.com', 'https://tile.openstreetmap.de', 'https://www.google.com'])
  // a tile server is not a script, connect or frame source
  assert.ok(!d['script-src'].some((s) => s.includes('openstreetmap')))
  assert.ok(!d['connect-src'].some((s) => s.includes('openstreetmap')))
  assert.ok(!d['frame-src'].some((s) => s.includes('openstreetmap')))
})

test('the static host is allowed for images only', () => {
  const d = directives(buildCsp({ nonce: 'abc', staticBaseUrl: 'https://static.example.org/assets/' }))
  assert.deepEqual(d['img-src'], ["'self'", 'blob:', 'data:', 'https://tile.openstreetmap.de', 'https://static.example.org'])
  assert.deepEqual(d['connect-src'], ["'self'"])
  assert.equal(staticOrigin('  '), null)
  assert.equal(staticOrigin('javascript:alert(1)'), null)
  assert.equal(staticOrigin('not a url'), null)
})

test('the nonce is 128 bits of base64 and differs per request', () => {
  const nonces = new Set(Array.from({ length: 200 }, () => newNonce()))
  assert.equal(nonces.size, 200)
  for (const nonce of nonces) {
    assert.match(nonce, /^[A-Za-z0-9+/]{22}==$/)
    assert.equal(Buffer.from(nonce, 'base64').length, 16)
  }
  assert.notEqual(buildCsp({ nonce: newNonce() }), buildCsp({ nonce: newNonce() }))
})

test('only the text 1 switches report-only on, and it renames the header', () => {
  assert.equal(isReportOnly('1'), true)
  for (const off of [undefined, '', '0', 'true', 'yes']) assert.equal(isReportOnly(off), false)
  assert.equal(cspHeaderName(false), 'Content-Security-Policy')
  assert.equal(cspHeaderName(true), 'Content-Security-Policy-Report-Only')
})

// THE PROXY -------------------------------------------------------------------
const matcher = new RegExp(`^${config.matcher[0]}$`)

test('the proxy runs for every page path and skips build output and public files', () => {
  for (const page of ['/', '/auth/signin', '/auth/register', '/components', '/components/similarity-map',
    '/components/3f2c0c86-6b5b-4a6a-8b7e-0d9d3a2d6e11', '/admin/users', '/privacy', '/invite',
    '/api/backend/identities', '/api/auth/session', '/gh-interface', '/gh-interface/',
    '/gh-interface/csc_addcomponent.jpg', '/gh-interface/csc_fetchallsnapshots.png']) {
    assert.ok(matcher.test(page), page)
  }
  for (const file of ['/_next/static/chunks/app.js', '/_next/image', '/favicon.ico',
    '/backgroundmeshes/a_reduced.glb', '/logo/csc.svg', '/logo/funding/x.png']) {
    assert.ok(!matcher.test(file), file)
  }
})

test('the matcher runs for every path under a protected prefix, whatever it ends in', () => {
  // an exclusion here would let the path past the sign-in gate (the gh-interface
  // screenshots were once excluded by their extension)
  for (const prefix of PROTECTED_PREFIXES) {
    for (const tail of ['', '/', '/x', '/x/y', '/x.jpg', '/x.jpeg', '/x.png', '/x.webp', '/x.svg',
      '/x.gif', '/x.glb', '/x.json', '/x.js', '/x.css', '/x.ico', '/x.pdf']) {
      assert.ok(matcher.test(`${prefix}${tail}`), `${prefix}${tail}`)
    }
  }
})

test('the sign-in gate covers the prefixes it always did, and public pages stay public', () => {
  for (const protectedPath of ['/components', '/components/similarity-map', '/components/location-map', '/dashboard', '/dashboard/x',
    '/admin', '/admin/users', '/api/backend/identities', '/gh-interface', '/locate-by-id',
    '/locate-by-id/x', '/scan', '/my-work', '/identify', '/analytics', '/transmit-id',
    '/add-component', '/add-component/x', '/oauth/consent']) {
    assert.ok(isProtectedPath(protectedPath), protectedPath)
  }
  for (const open of ['/', '/auth/signin', '/auth/register', '/auth/forgot-password', '/invite',
    '/privacy', '/imprint', '/credits', '/id/abc', '/settings', '/api/auth/session',
    '/componentsx', '/scanner']) {
    assert.ok(!isProtectedPath(open), open)
  }
  assert.ok(isApiPath('/api/backend/x') && isApiPath('/api/auth/session'))
  assert.ok(!isApiPath('/apiary'))
})
