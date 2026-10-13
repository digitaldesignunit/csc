/**
 * The security headers of the web app (8.144 g): the list is asserted here
 * and reaches the server through `headers()` of next.config.ts.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import nextConfig from '../next.config'
import { CANONICAL_HOST, headerRules } from './securityHeaders'

const flat = (rule: { headers: Array<{ key: string; value: string }> }) =>
  Object.fromEntries(rule.headers.map((h) => [h.key, h.value]))

test('every path gets the framing, referrer and sniffing headers', () => {
  const [all] = headerRules()
  assert.equal(all.source, '/:path*')
  assert.equal(all.has, undefined)
  assert.deepEqual(flat(all), {
    'Content-Security-Policy': "frame-ancestors 'none'",
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Content-Type-Options': 'nosniff',
  })
})

test('HSTS is sent on the canonical host only, without includeSubDomains', () => {
  const rules = headerRules()
  const hsts = rules.filter((r) => 'Strict-Transport-Security' in flat(r))
  assert.equal(hsts.length, 1)
  assert.deepEqual(hsts[0].has, [{ type: 'host', value: CANONICAL_HOST }])
  const value = flat(hsts[0])['Strict-Transport-Security']
  assert.match(value, /^max-age=\d{7,}$/)
  assert.ok(!/includeSubDomains|preload/i.test(value))
  // and not in the rule for every path
  assert.ok(!('Strict-Transport-Security' in flat(rules[0])))
})

test('next.config.ts serves that list', async () => {
  assert.equal(typeof nextConfig.headers, 'function')
  assert.deepEqual(await nextConfig.headers!(), headerRules())
})
