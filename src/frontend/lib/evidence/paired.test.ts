/**
 * The paired rebound record of a core record: the link on the core's card
 * (0.6.3.1).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  PAIRED_OFF_PAGE_TITLE,
  isOnPage,
  pairedReboundId,
  pairedReboundLink,
  recordAnchor,
} from '@/lib/evidence/paired'

test('a core record names its paired rebound record', () => {
  const payload = { sampling: { paired_rebound_id: 'abc-123' } }
  assert.equal(pairedReboundId('core_compression', payload), 'abc-123')
})

test('only a core record has one', () => {
  const payload = { sampling: { paired_rebound_id: 'abc-123' } }
  assert.equal(pairedReboundId('rebound_hammer', payload), null)
  assert.equal(pairedReboundId('reinforcement_layout', payload), null)
})

test('a core without a pairing, or a value that is no id, has none', () => {
  assert.equal(pairedReboundId('core_compression', { sampling: {} }), null)
  assert.equal(pairedReboundId('core_compression', { sampling: { paired_rebound_id: null } }), null)
  assert.equal(pairedReboundId('core_compression', { sampling: { paired_rebound_id: 5 } }), null)
  assert.equal(pairedReboundId('core_compression', { sampling: { paired_rebound_id: '  ' } }), null)
  assert.equal(pairedReboundId('core_compression', {}), null)
  assert.equal(pairedReboundId('core_compression', null), null)
  assert.equal(pairedReboundId('core_compression', undefined), null)
})

test('the link points at the card of the record', () => {
  assert.equal(recordAnchor('abc-123'), '#record-abc-123')
})

test('the link is shown for a record on the page', () => {
  assert.equal(isOnPage('a', ['a', 'b']), true)
  assert.equal(isOnPage('c', ['a', 'b']), false)
})

test('the core links to its rebound record when that record is on the page', () => {
  const payload = { sampling: { paired_rebound_id: 'reb-1' } }
  assert.deepEqual(pairedReboundLink('core_compression', payload, ['core-1', 'reb-1']), {
    id: 'reb-1', onPage: true, href: '#record-reb-1',
  })
})

test('the id is plain text with a title when the record is not on the page', () => {
  const payload = { sampling: { paired_rebound_id: 'reb-1' } }
  const off = { id: 'reb-1', onPage: false, title: PAIRED_OFF_PAGE_TITLE }
  assert.deepEqual(pairedReboundLink('core_compression', payload, ['core-1']), off)
  assert.deepEqual(pairedReboundLink('core_compression', payload, []), off)
  // no list at all (a queue, the review step of the form): nothing is on the page
  assert.deepEqual(pairedReboundLink('core_compression', payload), off)
  assert.match(PAIRED_OFF_PAGE_TITLE, /another version|filtered out/)
})

test('a record without a pairing has no link and no text', () => {
  assert.equal(pairedReboundLink('core_compression', { sampling: {} }, ['a']), null)
  assert.equal(pairedReboundLink('rebound_hammer', { sampling: { paired_rebound_id: 'x' } }, ['x']), null)
})
