/**
 * The date of an observation as the form sends it (decision 8.91 b).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { localDay, observationInstant } from '@/lib/evidence/dates'

// a fixed moment in the middle of a day, whatever the machine's time zone
const NOW = new Date(2026, 9, 3, 15, 47, 31, 456)

test('a date that is today is now, to the minute, with exact precision', () => {
  const sent = observationInstant(localDay(NOW), NOW)
  assert.ok(sent)
  assert.equal(sent.observed_at_precision, 'exact')
  assert.match(sent.observed_at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$/)
  const sentMs = Date.parse(sent.observed_at)
  assert.ok(sentMs <= NOW.getTime() && NOW.getTime() - sentMs < 60_000, 'within the minute before now')
})

test('a past date stays the day-precise UTC midnight', () => {
  assert.deepEqual(observationInstant('2026-10-02', NOW), {
    observed_at: '2026-10-02T00:00:00Z', observed_at_precision: 'day',
  })
  assert.deepEqual(observationInstant('1968-03-01', NOW), {
    observed_at: '1968-03-01T00:00:00Z', observed_at_precision: 'day',
  })
})

test('an empty or malformed date sends nothing', () => {
  assert.equal(observationInstant('', NOW), null)
  assert.equal(observationInstant('03.10.2026', NOW), null)
})

test('a same-day observation is not before a state recorded earlier that day', () => {
  const stateStart = new Date(2026, 9, 3, 15, 45, 32).getTime()
  const sent = observationInstant(localDay(NOW), NOW)
  assert.ok(sent && Date.parse(sent.observed_at) >= stateStart)
})
