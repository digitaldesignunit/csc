import assert from 'node:assert/strict'
import { test } from 'node:test'

import { BackendError } from './backend'
import {
  SIMILAR_CARD_COUNT,
  SIMILAR_MORE_COUNT,
  canShowMore,
  cardOfAnswer,
  cardOfError,
  distanceText,
  needsScrollBack,
  shownPieces,
  toggleLabel,
  neighbourLine,
  neighbourTitle,
  similarPath,
} from './similarPieces'
import type { SimilarPiece, SimilarPieces } from '@/generated/CatalogModels'

const ID = '2e6f6e3c-165f-4ca2-9be9-884e6e8e84f5'

function piece(number: number, shape: string | null, name: string | null, distance = 1.234): SimilarPiece {
  return {
    distance,
    piece: { _id: `id-${number}`, catalog_number: number, name, shape_class: shape } as unknown as SimilarPiece['piece'],
  }
}

function answer(results: SimilarPiece[]): SimilarPieces {
  return { query_id: ID, basis: 'radial_signature', basis_label: 'Radial signature', considered: 9, results }
}

test('the request asks for the radial signature and the six nearest', () => {
  assert.equal(SIMILAR_CARD_COUNT, 6)
  assert.equal(similarPath(ID), `/identities/${ID}/similar?basis=radial_signature&count=6`)
  assert.equal(similarPath(ID, SIMILAR_MORE_COUNT), `/identities/${ID}/similar?basis=radial_signature&count=24`)
  assert.match(similarPath('a b'), /^\/identities\/a%20b\/similar/)
})

test('the card lists the neighbours and is hidden when there are none', () => {
  const found = cardOfAnswer(answer([piece(5, 'planar', 'Panel')]))
  assert.equal(found.kind, 'list')
  assert.equal(found.kind === 'list' && found.pieces.length, 1)
  assert.deepEqual(cardOfAnswer(answer([])), { kind: 'hidden', reason: 'none' })
  assert.deepEqual(cardOfAnswer(null), { kind: 'hidden', reason: 'none' })
  assert.deepEqual(cardOfAnswer(undefined), { kind: 'hidden', reason: 'none' })
})

test('a refusal or a failure hides the card and says why', () => {
  assert.deepEqual(cardOfError(new BackendError(422, 'no descriptor')), { kind: 'hidden', reason: 'no_descriptor' })
  assert.deepEqual(cardOfError(new BackendError(409, 'not computed')), { kind: 'hidden', reason: 'no_matrix' })
  assert.deepEqual(cardOfError(new BackendError(404, 'Component not found')), { kind: 'hidden', reason: 'not_found' })
  assert.deepEqual(cardOfError(new BackendError(500, 'x')), { kind: 'hidden', reason: 'error' })
  assert.deepEqual(cardOfError(new TypeError('network')), { kind: 'hidden', reason: 'error' })
})

test('"Show more" is offered only after a full first answer', () => {
  assert.equal(canShowMore(6), true)
  assert.equal(canShowMore(5), false)
  assert.equal(canShowMore(0), false)
  assert.equal(canShowMore(24, 24), true)
})

test('a neighbour is named by number and shape, and its distance is rounded', () => {
  assert.equal(neighbourLine(piece(584, 'irregular', 'Scanned Rubble 54').piece), '#584 / irregular')
  assert.equal(neighbourLine(piece(7, null, null).piece), '#7')
  assert.equal(distanceText(1.2349), '1.23')
  assert.equal(distanceText(0), '0.00')
  assert.equal(distanceText(Number.NaN), '')
  assert.equal(neighbourTitle(piece(7, 'planar', 'Panel 7', 0.5)), 'Panel 7, distance 0.50 (smaller is more similar)')
  assert.equal(neighbourTitle(piece(8, 'planar', null, 2)), 'Component #8, distance 2.00 (smaller is more similar)')
})

test('the toggle shows six, all loaded when expanded, and the right word', () => {
  const loaded = Array.from({ length: 24 }, (_, i) => i)
  assert.deepEqual(shownPieces(loaded, false), [0, 1, 2, 3, 4, 5])
  assert.equal(shownPieces(loaded, true).length, 24)
  assert.deepEqual(shownPieces([1, 2], false), [1, 2])
  assert.equal(toggleLabel(6, false), 'Show more')
  assert.equal(toggleLabel(24, true), 'Show fewer')
  assert.equal(toggleLabel(3, false), null)            // fewer than six found: nothing more to show
  assert.equal(toggleLabel(7, true), 'Show fewer')
})

test('after "Show fewer" the card scrolls back only when its top left the viewport', () => {
  assert.equal(needsScrollBack(-1), true)
  assert.equal(needsScrollBack(-400), true)
  assert.equal(needsScrollBack(0), false)
  assert.equal(needsScrollBack(120), false)
})
