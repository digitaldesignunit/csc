/**
 * The privacy text holds what the code does (decision 8.144, S14): the
 * sign-in cookie lasts at most 24 hours, accounts are deleted on request,
 * location data is removed from photos, and the date moves with the text.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'

import { MAP_TILE_ORIGIN } from './csp'
import { LAST_UPDATED, ROWS } from './privacyText'

const text = ROWS.map((row) => `${row.what} ${row.kept}`).join('\n')

test('the sign-in cookie lasts at most 24 hours, as the session does', () => {
  assert.match(text, /sign-in cookie lasts at most 24 hours/)
  const route = readFileSync(join(__dirname, '..', 'app', 'api', 'auth', '[...nextauth]', 'route.ts'), 'utf8')
  assert.match(route, /maxAge: 24 \* 60 \* 60/)
  assert.ok(!/ends with your session/.test(text))
})

test('accounts are deleted on request', () => {
  assert.match(text, /it is deleted on request/)
})

test('location data is removed from photos', () => {
  assert.match(text, /GPS position\) in the metadata of a photo is removed when it is uploaded/)
})

test('the date is not older than this change', () => {
  const day = new Date(`${LAST_UPDATED} UTC`)
  assert.ok(day >= new Date('2026-10-23T00:00:00Z'), LAST_UPDATED)
})

test('the cookies row claims no tracking, no statistics, no advertising, and not that nothing loads from other sites', () => {
  const row = ROWS.find((r) => r.what.startsWith('Cookies'))!
  assert.ok(row)
  assert.match(row.why, /No tracking, no statistics, no advertising\./)
  assert.ok(!/other sites/.test(row.why))
})

test('the maintainer alone is the controller, and the page says TU Darmstadt is not (8.176)', () => {
  const page = readFileSync(join(__dirname, '..', 'app', 'privacy', 'page.tsx'), 'utf8').replace(/\s+/g, ' ')
  assert.match(page, /run by Max Eschenbach in person\. Max Eschenbach alone is the controller/)
  assert.match(page, /TU Darmstadt does not operate the site and is not responsible for it\./)
})

test('the imprint names the maintainer as provider and controller and cites the DDG, not the repealed TMG', () => {
  const page = readFileSync(join(__dirname, '..', 'app', 'imprint', 'page.tsx'), 'utf8').replace(/\s+/g, ' ')
  assert.match(page, /Verantwortlicher im Sinne der DSGVO ist Max Eschenbach pers&ouml;nlich/)
  assert.match(page, /betreibt den Katalog nicht und ist f&uuml;r ihn nicht verantwortlich/)
  assert.match(page, /\u00a7 7 Abs\. 1 DDG/)
  assert.match(page, /\u00a7\u00a7 8 bis 10 DDG/)
  assert.ok(!/TMG/.test(page))
})

test('the map tiles are named: the host of the policy, the receiver, and only the Location Map', () => {
  const row = ROWS.find((r) => r.what.startsWith('Map tiles'))!
  assert.ok(row)
  assert.ok(row.what.includes(new URL(MAP_TILE_ORIGIN).host))
  assert.match(row.what, /FOSSGIS e\.V\./)
  assert.match(row.what, /IP address/)
  assert.match(row.what, /Location Map page/)
  assert.match(row.what, /No other page loads them/)
})

test('the text is ASCII, as the files are', () => {
  for (const row of ROWS) {
    for (const value of Object.values(row)) assert.ok(/^[\x20-\x7e]*$/.test(value), value)
  }
})
