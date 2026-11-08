import assert from 'node:assert/strict'
import { test } from 'node:test'

import { emptySummary, summaryBody, type SummaryState } from '@/components/evidence/form/state'
import type { MethodInfo, QuantityInfo } from '@/lib/evidence/api'

const CLAIM = { summary_from_client: true, summary_kind: 'claimed' } as MethodInfo
const DERIVED = { summary_from_client: false, summary_kind: 'measured' } as MethodInfo
const SCALAR = { name: 'compressive_strength', kind: 'scalar' } as QuantityInfo
const summary = (extra: Partial<SummaryState>): SummaryState => ({ ...emptySummary(), ...extra })

test('a claim with a value sends the kind of the method with it (8.189)', () => {
  assert.deepEqual(
    summaryBody(summary({ quantity: 'compressive_strength', value: '25', unit: 'MPa' }), SCALAR, CLAIM),
    { quantity: 'compressive_strength', kind: 'claimed', value: 25, unit: 'MPa' })
})

test('a claim with a range or a class list carries the kind too', () => {
  assert.deepEqual(
    summaryBody(summary({ quantity: 'compressive_strength', low: '20', high: '30' }), SCALAR, CLAIM),
    { quantity: 'compressive_strength', kind: 'claimed', range: [20, 30] })
  assert.deepEqual(
    summaryBody(summary({ quantity: 'exposure_class', classes: ['XC1'] }), { name: 'exposure_class', kind: 'categorical' } as QuantityInfo, CLAIM),
    { quantity: 'exposure_class', kind: 'claimed', range: ['XC1'] })
})

test('a document without a result sends no summary at all (8.106)', () => {
  assert.equal(summaryBody(emptySummary(), undefined, CLAIM), undefined)
})

test('where the server derives the result, the web sends no kind', () => {
  assert.equal('kind' in summaryBody(summary({ quantity: 'q_value', value: '30' }), SCALAR, DERIVED)!, false)
  assert.equal('kind' in summaryBody(summary({ quantity: 'q_value', value: '30' }), SCALAR)!, false)
  // a claim method that names no kind sends none either
  assert.equal('kind' in summaryBody(summary({ quantity: 'q', value: '1' }), SCALAR,
    { summary_from_client: true, summary_kind: null } as MethodInfo)!, false)
})
