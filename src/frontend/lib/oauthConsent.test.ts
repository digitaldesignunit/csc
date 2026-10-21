/**
 * The consent page of a connector (decision 8.168 b): the request id, where
 * the browser may be sent, and what the card shows.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import ConsentCard from '../components/oauth/ConsentCard'
import { ReadOnlyContext } from '../components/common/ReadOnlyProvider'
import {
  ACCESS_LINE,
  GH_LOOPBACK_WARNING,
  GONE_TEXT,
  LOOPBACK_WARNING,
  allowText,
  consentTitle,
  isGrasshopper,
  requestId,
  safeReturnUrl,
  type ConsentView,
} from './oauthConsent'

const VIEW: ConsentView = {
  redirect_host: 'claude.ai',
  redirect_is_loopback: false,
  client_name: 'Claude',
  access: ACCESS_LINE,
  can_allow: true,
  refusal: null,
}

const card = (view: ConsentView | null, extra: Record<string, unknown> = {}, readOnly = false) =>
  renderToStaticMarkup(
    createElement(ReadOnlyContext.Provider, { value: readOnly },
      createElement(ConsentCard, {
        view, problem: null, busy: false, leaving: null, onAllow: () => {}, onDeny: () => {}, ...extra,
      })),
  )

test('a request id is the url-safe text /authorize made; anything else is none', () => {
  assert.equal(requestId('ImmZIk0E0DqQnPckhinFh4wp_i3r2yeI8YQjLHssjv0'), 'ImmZIk0E0DqQnPckhinFh4wp_i3r2yeI8YQjLHssjv0')
  for (const bad of [null, undefined, '', 'short', 'has space in it which is long enough', '../../etc/passwd'.repeat(2), 'a'.repeat(200)]) {
    assert.equal(requestId(bad as string | null | undefined), null, String(bad))
  }
})

test('the browser goes only to the callback of Claude or a loopback callback', () => {
  const claude = 'https://claude.ai/api/mcp/auth_callback?code=abc&state=xyz'
  assert.equal(safeReturnUrl(claude), claude)
  assert.equal(safeReturnUrl('http://localhost:3118/callback?code=a&state=b'), 'http://localhost:3118/callback?code=a&state=b')
  assert.equal(safeReturnUrl('http://127.0.0.1/callback?error=access_denied'), 'http://127.0.0.1/callback?error=access_denied')
})

test('nothing else is ever opened from the page', () => {
  for (const bad of [
    'https://evil.example/api/mcp/auth_callback?code=a',
    'https://claude.ai.evil.example/api/mcp/auth_callback',
    'https://claude.ai/other',
    'http://claude.ai/api/mcp/auth_callback',
    'https://user:pw@claude.ai/api/mcp/auth_callback',
    'https://claude.ai/api/mcp/auth_callback#frag',
    'http://localhost/other',
    'http://localhost.evil.example/callback',
    'http://example.org:3000/callback',
    'javascript:alert(1)',
    '//claude.ai/api/mcp/auth_callback',
    '/api/mcp/auth_callback',
    '',
    'not a url',
  ]) {
    assert.equal(safeReturnUrl(bad), null, bad)
  }
})

test('the card shows the host first and large, the tool name small and the access', () => {
  const html = card(VIEW)
  assert.match(html, /data-testid="redirect-host">claude\.ai</)
  assert.ok(html.includes('text-2xl font-bold'))
  assert.ok(html.includes('The tool calls itself') && html.includes('Claude'))
  assert.ok(html.includes('it is not checked'))
  assert.ok(html.includes('Read access to the catalog, as you see it'))
  assert.match(html, />Allow</)
  assert.match(html, />Deny</)
  assert.ok(html.indexOf('claude.ai') < html.indexOf('The tool calls itself'))
})

test('a loopback address gets its warning, a tool without a name is just the host', () => {
  const html = card({ ...VIEW, redirect_host: 'localhost', redirect_is_loopback: true, client_name: null })
  assert.ok(html.includes(LOOPBACK_WARNING))
  assert.ok(!html.includes('The tool calls itself'))
  assert.ok(!card(VIEW).includes(LOOPBACK_WARNING))
})

const GH_VIEW: ConsentView = {
  redirect_host: '127.0.0.1',
  redirect_is_loopback: true,
  client_name: null,
  scope: 'gh:client',
  computer: 'WORKSTATION-7',
  access: 'Grasshopper on this computer: act as you in the Grasshopper interface',
  can_allow: true,
  refusal: null,
}

test('the Grasshopper variant says what it is: this computer, acting as you, the host large', () => {
  const html = card(GH_VIEW)
  assert.ok(isGrasshopper(GH_VIEW) && !isGrasshopper(VIEW))
  assert.ok(html.includes(consentTitle(GH_VIEW)) && html.includes('Sign in Grasshopper on this computer'))
  assert.match(html, /data-testid="redirect-host">127\.0\.0\.1</)
  assert.ok(html.includes('text-2xl font-bold'))
  assert.ok(html.includes('Grasshopper on this computer: act as you in the Grasshopper interface'))
  assert.ok(html.includes(GH_LOOPBACK_WARNING) && !html.includes(LOOPBACK_WARNING))
  assert.ok(html.includes('The computer calls itself') && html.includes('WORKSTATION-7') && html.includes('it is not checked'))
  assert.ok(!html.includes('The tool calls itself'))
  assert.match(html, />Allow</)
  assert.match(html, />Deny</)
  assert.ok(allowText('127.0.0.1', GH_VIEW).includes('Grasshopper here can act as you'))
  assert.ok(allowText('claude.ai').includes('that tool can read the catalog as you'))
})

test('the computer name is text, never markup', () => {
  const html = card({ ...GH_VIEW, computer: '<b>x</b> & "y"' })
  assert.ok(!html.includes('<b>x</b>'))
  assert.ok(html.includes('&lt;b&gt;x&lt;/b&gt;'))
})

test('the title of a tool that reads the catalog stays', () => {
  assert.equal(consentTitle(VIEW), 'Connect a tool to the catalog')
  assert.ok(card(VIEW).includes('Connect a tool to the catalog'))
})

test('a role that may not allow sees a refusal and no Allow', () => {
  const html = card({ ...VIEW, can_allow: false, refusal: 'Your account may not connect tools to the catalog.' })
  assert.ok(html.includes('may not connect tools'))
  assert.ok(!html.includes('>Allow<'))
  assert.match(html, />Deny</)
})

test('a request that is gone says so and shows no buttons', () => {
  const html = card(null, { problem: GONE_TEXT })
  assert.ok(html.includes(GONE_TEXT))
  assert.ok(!html.includes('>Allow<') && !html.includes('>Deny<'))
})

test('Allow and Deny stop while the backend is read-only', () => {
  const on = card(VIEW, {}, true)
  assert.equal((on.match(/disabled=""/g) ?? []).length, 2)
  assert.ok(!/disabled=""/.test(card(VIEW)))
})
