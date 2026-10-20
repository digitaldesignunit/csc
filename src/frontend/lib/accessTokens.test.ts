/**
 * Access tokens in the interface (decision 8.167): the texts and rules, the
 * once-only display of a new token, the list that never holds a token, and the
 * write buttons that stop while the backend is read-only.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import AccessTokenTable from '../components/settings/AccessTokenTable'
import NewTokenNotice from '../components/settings/NewTokenNotice'
import { ReadOnlyContext } from '../components/common/ReadOnlyProvider'
import {
  ONCE_NOTE,
  canRenew,
  canRevoke,
  createFailure,
  lifetimeLabel,
  scopeText,
  tokenPreview,
  type AccessTokenRow,
} from './accessTokens'

const TOKEN = 'csc_pat_AbCdEfGh0123456789abcdefghijklmnopqrstuv'

const row = (over: Partial<AccessTokenRow> = {}): AccessTokenRow => ({
  id: 'r1',
  kind: 'pat',
  name: 'my assistant',
  scopes: ['read:catalog'],
  short_id: 'AbCdEfGh',
  created: '2026-10-20T10:00:00.000000Z',
  expires: '2027-01-18T10:00:00.000000Z',
  last_used: null,
  revoked: null,
  status: 'active',
  renew_due: false,
  ...over,
})

const table = (rows: AccessTokenRow[], extra: Record<string, unknown> = {}, readOnly = false) =>
  renderToStaticMarkup(
    createElement(ReadOnlyContext.Provider, { value: readOnly },
      createElement(AccessTokenTable, {
        rows: rows.map((r) => ({ ...r, ...extra })),
        showOwner: true,
        onRevoke: () => {},
        onRenew: () => {},
      })),
  )

test('the choices of the lifetime read as days and a year', () => {
  assert.deepEqual([30, 90, 365].map(lifetimeLabel), ['30 days', '90 days', '1 year'])
})

test('a list shows the prefix and the first 8 characters, then dots', () => {
  assert.equal(tokenPreview(row()), 'csc_pat_AbCdEfGh...')
  assert.equal(tokenPreview(row({ kind: 'device', short_id: 'ZZZZ1111' })), 'csc_dev_ZZZZ1111...')
})

test('a connection of a tool through OAuth shows a steady label, never a token prefix', () => {
  assert.equal(tokenPreview(row({ kind: 'oauth', short_id: '0a1b2c3d' })), 'Connection 0a1b2c3d')
  const html = table([row({ kind: 'oauth', short_id: '0a1b2c3d', name: 'Claude (claude.ai)' })])
  assert.ok(html.includes('Connection 0a1b2c3d') && html.includes('Claude (claude.ai)'))
  assert.ok(!html.includes('csc_oat_') && !html.includes('csc_ort_'))
  // no Renew for a connection, even near its end: a new consent makes a new one
  assert.ok(!table([row({ kind: 'oauth', renew_due: true })]).includes('Renew'))
})

test('the scope is named in words', () => {
  assert.equal(scopeText(['read:catalog']), 'Read the catalog (MCP)')
  assert.equal(scopeText(['gh:client']), 'Grasshopper client')
  assert.equal(scopeText(['other']), 'other')
})

test('renew is offered within 14 days of the expiry and after it, never for a revoked token', () => {
  assert.equal(canRenew(row()), false)
  assert.equal(canRenew(row({ renew_due: true })), true)
  assert.equal(canRenew(row({ status: 'expired' })), true)
  assert.equal(canRenew(row({ status: 'revoked', renew_due: true })), false)
  assert.equal(canRenew(row({ kind: 'device', renew_due: true })), false)
  assert.equal(canRevoke(row({ status: 'expired' })), true)
  assert.equal(canRevoke(row({ status: 'revoked' })), false)
})

test('a refused create shows the backend text, else a general one', () => {
  assert.equal(createFailure(new Error('You already have 10 active access tokens: revoke one first.')),
    'You already have 10 active access tokens: revoke one first.')
  assert.equal(createFailure(new Error('Request failed (500)')), 'The token could not be created.')
  assert.equal(createFailure('x'), 'The token could not be created.')
})

test('a new token is shown once, in full, with the copy button and the note', () => {
  const html = renderToStaticMarkup(createElement(NewTokenNotice, { name: 'cursor', token: TOKEN, onDone: () => {} }))
  assert.ok(html.includes(TOKEN))
  assert.ok(html.includes(ONCE_NOTE) && /will not see it again/.test(ONCE_NOTE))
  assert.match(html, /aria-label="Copy the token"/)
  assert.match(html, />Done</)
})

test('the list never holds a token: only the first 8 characters, even if a row carried one', () => {
  const html = table([row()], { token: TOKEN, token_sha256: 'deadbeef'.repeat(8) })
  assert.ok(html.includes('csc_pat_AbCdEfGh...'))
  assert.ok(!html.includes(TOKEN) && !html.includes('AbCdEfGh0123'))
  assert.ok(!html.includes('deadbeef'))
})

test('the list shows the owner name and last used, never an e-mail address', () => {
  const html = table([row({ last_used: '2026-10-21T08:00:00.000000Z' })], { owner_username: 'adminuser', owner_id: 'u1' })
  assert.ok(html.includes('adminuser'))
  assert.ok(!html.includes('never'))
  assert.ok(!html.includes('@'))
  assert.ok(table([row()]).includes('never'))
})

test('a row offers Revoke, and Renew only when due; a revoked row neither', () => {
  const plain = table([row()])
  assert.ok(plain.includes('Revoke') && !plain.includes('Renew'))
  const due = table([row({ renew_due: true })])
  assert.ok(due.includes('Renew') && due.includes('Revoke') && due.includes('expires soon'))
  const revoked = table([row({ status: 'revoked', revoked: '2026-10-22T00:00:00.000000Z' })])
  assert.ok(!revoked.includes('>Revoke<') && !revoked.includes('Renew') && revoked.includes('revoked'))
  assert.ok(table([row({ status: 'expired' })]).includes('expired'))
})

test('the buttons are disabled with their reason while the backend is read-only', () => {
  const on = table([row({ renew_due: true })], {}, true)
  assert.equal((on.match(/disabled=""/g) ?? []).length, 2)
  const off = table([row({ renew_due: true })], {}, false)
  assert.ok(!/disabled=""/.test(off))
})
