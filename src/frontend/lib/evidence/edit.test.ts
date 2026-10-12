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

test('a self-attested record without its recorder among the performers says that it is reset', async () => {
  const { verificationNotices } = await import('./edit')
  const record = { recorded_by_user_id: 'u1', verification: { state: 'self_attested' } }
  assert.equal(verificationNotices(record, ['u1']).length, 0)
  assert.equal(verificationNotices(record, ['u1', 'u2']).length, 0)
  const reset = verificationNotices(record, ['u2'])
  assert.equal(reset.length, 1)
  assert.ok(reset[0].includes('self-attested') && reset[0].includes('unverified'))
  assert.equal(verificationNotices(record, []).length, 1)
})

test('a reviewed or accredited record says that a changed result resets it', async () => {
  const { verificationNotices } = await import('./edit')
  for (const state of ['reviewed', 'accredited']) {
    const notices = verificationNotices({ recorded_by_user_id: 'u1', verification: { state } }, ['u1'])
    assert.equal(notices.length, 1, state)
    assert.ok(notices[0].includes(state) && notices[0].includes('reviewer'))
  }
})

test('an unverified record or one with no verification says nothing', async () => {
  const { verificationNotices } = await import('./edit')
  assert.deepEqual(verificationNotices({ recorded_by_user_id: 'u1', verification: { state: 'unverified' } }, []), [])
  assert.deepEqual(verificationNotices({ recorded_by_user_id: 'u1' }, []), [])
  assert.deepEqual(verificationNotices({ verification: null }, ['u1']), [])
})
