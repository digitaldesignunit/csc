/**
 * Filling the empty document fields of a published layout once (RL5).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  documentValues,
  emptyDocumentFields,
  fillBody,
  fillProblems,
  needsTitle,
} from '@/lib/evidence/layoutDocument'

test('a layout without a document has every field empty and needs a title', () => {
  for (const payload of [undefined, null, {}, { document: null }, { document: {} }]) {
    assert.deepEqual(emptyDocumentFields(payload), ['title', 'date', 'reference', 'url', 'retrieved_at'])
    assert.equal(needsTitle(payload), true)
  }
})

test('only the empty fields of a document are open', () => {
  const payload = { document: { title: 'Bewehrungsplan', date: '1968-03', reference: '  ', url: null } }
  assert.deepEqual(emptyDocumentFields(payload), ['reference', 'url', 'retrieved_at'])
  assert.equal(needsTitle(payload), false)
  assert.equal(documentValues(payload).date, '1968-03')
})

test('the body holds only the typed values of the empty fields', () => {
  const payload = { document: { title: 'Plan', date: '1968' } }
  const body = fillBody(payload, {
    title: 'Other', date: '1999', reference: ' Plan 12 ', url: 'https://archive.example.org/12', retrieved_at: '',
  })
  assert.deepEqual(body, { payload: { document: { reference: 'Plan 12', url: 'https://archive.example.org/12' } } })
  // nothing typed, nothing sent
  assert.deepEqual(fillBody(payload, {}), { payload: { document: {} } })
})

test('a document may be started with a title', () => {
  assert.deepEqual(fillBody({}, { title: 'Drawing found later' }), { payload: { document: { title: 'Drawing found later' } } })
})

test('a title is needed when anything else is set on a layout without a document', () => {
  assert.deepEqual(fillProblems({}, { reference: 'R' }), { title: 'A title is needed for the document.' })
  assert.deepEqual(fillProblems({}, { title: 'T', reference: 'R' }), {})
  assert.deepEqual(fillProblems({}, {}), {})
  assert.deepEqual(fillProblems({ document: { title: 'T' } }, { reference: 'R' }), {})
})

test('a link must be http or https with a host; a date must be a date', () => {
  const payload = { document: { title: 'T' } }
  for (const url of ['javascript:alert(1)', 'ftp://host/x', 'example.org', 'https://a b.org', 'https://']) {
    assert.ok(fillProblems(payload, { url }).url, url)
  }
  assert.deepEqual(fillProblems(payload, { url: 'https://example.org/plan' }), {})
  assert.ok(fillProblems(payload, { date: '1968-13' }).date)
  assert.deepEqual(fillProblems(payload, { date: '1968' }), {})
  assert.ok(fillProblems(payload, { retrieved_at: '2026' }).retrieved_at)         // a day is needed
  assert.deepEqual(fillProblems(payload, { retrieved_at: '2026-10-05' }), {})
  // a set field is not checked: it is not sent
  assert.deepEqual(fillProblems({ document: { title: 'T', url: 'https://a.org' } }, { url: 'nonsense' }), {})
})
