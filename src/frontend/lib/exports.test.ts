/**
 * The pure parts of the passport exports (spec 7.8, decision 8.116 d): the
 * paths, the file name, and no CERO link for a piece CERO does not cover.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { downloadFailureMessage, isCeroMaterial, passportExports } from './exports'

const ID = '1cdca4a5-9713-5e17-8aea-1f4a964142f7'

test('CERO covers concrete and aerated concrete only', () => {
  assert.equal(isCeroMaterial('concrete'), true)
  assert.equal(isCeroMaterial('autoclaved_aerated_concrete'), true)
  assert.equal(isCeroMaterial('steel'), false)
  assert.equal(isCeroMaterial('timber'), false)
  assert.equal(isCeroMaterial(undefined), false)
  assert.equal(isCeroMaterial(null), false)
})

test('the export paths go through the backend proxy', () => {
  const out = passportExports(ID, 5, 'concrete')
  assert.equal(out.pdf, `/api/backend/identities/${ID}/export/pdf`)
  assert.equal(out.pdfFilename, 'csc-passport-5.pdf')
  assert.equal(out.jsonld, `/api/backend/identities/${ID}/compose?format=jsonld`)
  assert.equal(out.cero, `/api/backend/identities/${ID}/export/cero`)
})

test('a steel piece has a PDF and JSON-LD but no CERO link', () => {
  const out = passportExports(ID, 9, 'steel')
  assert.equal(out.cero, null)
  assert.ok(out.pdf.endsWith('/export/pdf'))
})

test('a rate-limited download says so in plain words', () => {
  assert.equal(
    downloadFailureMessage(429, '{"error":"Rate limit exceeded: 20 per 1 minute"}'),
    'Too many downloads, try again in a minute',
  )
  assert.equal(downloadFailureMessage(409, 'CERO covers concrete elements only'), 'CERO covers concrete elements only')
  assert.equal(downloadFailureMessage(500, ''), 'Download failed (500)')
})

test('the CERO file is named after the piece', () => {
  assert.equal(passportExports(ID, 5, 'concrete').ceroFilename, 'csc-cero-5.ttl')
})
