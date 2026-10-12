import assert from 'node:assert/strict'
import test from 'node:test'

import { stepIndex } from '@/lib/previewStep'

test('stepping moves one place and stops at both ends', () => {
  assert.equal(stepIndex(1, 3, 1), 2)
  assert.equal(stepIndex(1, 3, -1), 0)
  assert.equal(stepIndex(2, 3, 1), null)
  assert.equal(stepIndex(0, 3, -1), null)
})

test('an item that is not in the list does not step', () => {
  assert.equal(stepIndex(-1, 3, 1), null)
  assert.equal(stepIndex(5, 3, -1), null)
})
