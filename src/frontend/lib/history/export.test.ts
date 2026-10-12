import assert from 'node:assert/strict'
import test from 'node:test'

import { MAX_CANVAS_SIDE, exportFileName, pngScale } from '@/lib/history/export'

test('the file name carries the piece number and the day', () => {
  const now = new Date('2026-10-12T08:00:00Z')
  assert.equal(exportFileName(709, 'abcdef01-2345', 'svg', now), 'csc-history-709-20261012.svg')
  assert.equal(exportFileName(null, 'abcdef01-2345', 'json', now), 'csc-history-abcdef01-20261012.json')
})

test('a very wide image gets a smaller PNG scale', () => {
  assert.equal(pngScale(1000, 400), 2)
  assert.ok(pngScale(20000, 400) * 20000 <= MAX_CANVAS_SIDE + 1e-6)
  assert.ok(pngScale(0, 0) > 0)
})
