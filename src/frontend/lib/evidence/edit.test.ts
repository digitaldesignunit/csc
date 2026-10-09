import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { EvidenceBulkItem } from '@/generated'
import type { MethodInfo } from './api'
import { canEditEvidence, editBody } from './edit'

const METHOD = (summary_from_client: boolean) => ({ name: 'rebound_hammer', summary_from_client }) as MethodInfo

const ITEM = {
  identity_id: 'i1',
  method: 'rebound_hammer',
  payload: { test_area: { label: 'A' } },
  performed_by: [],
  self_attested: true,
  observed_at_precision: 'day',
} as unknown as EvidenceBulkItem

test('a draft is edited by its author or a moderator, a pending record by a moderator only', () => {
  assert.equal(canEditEvidence('draft', true, false), true)
  assert.equal(canEditEvidence('draft', false, true), true)
  assert.equal(canEditEvidence('draft', false, false), false)
  assert.equal(canEditEvidence('pending', true, false), false)
  assert.equal(canEditEvidence('pending', false, true), true)
  for (const status of ['rejected', 'published', 'withdrawn']) {
    assert.equal(canEditEvidence(status, true, true), false, status)
  }
})

test('the edit body drops the component and self_attested and keeps the rest', () => {
  const body = editBody(ITEM, METHOD(false))
  assert.equal('identity_id' in body, false)
  assert.equal('self_attested' in body, false)
  assert.equal(body.method, 'rebound_hammer')
  assert.deepEqual(body.payload, { test_area: { label: 'A' } })
  assert.equal(body.observed_at_precision, 'day')
  // the item itself is not changed
  assert.equal((ITEM as unknown as { identity_id: string }).identity_id, 'i1')
})

test('an emptied note is sent as null so that the edit clears it', () => {
  assert.equal(editBody(ITEM, METHOD(false)).notes, null)
  assert.equal(editBody({ ...ITEM, notes: 'kept' } as EvidenceBulkItem, METHOD(false)).notes, 'kept')
})

test('an emptied summary is cleared only for a method whose client sends it', () => {
  assert.equal(editBody(ITEM, METHOD(true)).summary, null)
  assert.equal('summary' in editBody(ITEM, METHOD(false)), false)
})
