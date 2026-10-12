/**
 * The date text of the shared `DateField` (decision 8.143).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  FIRST_YEAR,
  canonical,
  daysInMonth,
  finalMessage,
  firstDay,
  formatHint,
  lastYear,
  parseDate,
  precisionOf,
  todayText,
  truncateTo,
  yearPage,
  type DatePrecision,
} from '@/lib/dateField'

const NOW = new Date(2026, 9, 12, 15, 0, 0)
const ALL: DatePrecision[] = ['year', 'month', 'day']

test('a day, a month and a year are read as typed, with their precision', () => {
  assert.deepEqual(parseDate('2024-05-03', ALL, NOW), {
    kind: 'ok', text: '2024-05-03', precision: 'day', year: 2024, month: 5, day: 3,
  })
  assert.deepEqual(parseDate('2024-05', ALL, NOW), {
    kind: 'ok', text: '2024-05', precision: 'month', year: 2024, month: 5, day: 1,
  })
  assert.deepEqual(parseDate('1968', ALL, NOW), {
    kind: 'ok', text: '1968', precision: 'year', year: 1968, month: 1, day: 1,
  })
})

test('a short month or day is padded, other separators and the German order are read', () => {
  const day = parseDate('2024-5-3', ALL, NOW)
  assert.ok(day.kind === 'ok' && day.text === '2024-05-03')
  const slash = parseDate('2024/05/03', ALL, NOW)
  assert.ok(slash.kind === 'ok' && slash.text === '2024-05-03')
  const german = parseDate('03.05.2024', ALL, NOW)
  assert.ok(german.kind === 'ok' && german.text === '2024-05-03')
  const germanMonth = parseDate('5.2024', ALL, NOW)
  assert.ok(germanMonth.kind === 'ok' && germanMonth.text === '2024-05' && germanMonth.precision === 'month')
  const spaced = parseDate('  2024-05-03 ', ALL, NOW)
  assert.ok(spaced.kind === 'ok' && spaced.text === '2024-05-03')
})

test('an empty text is empty', () => {
  assert.deepEqual(parseDate('', ALL, NOW), { kind: 'empty' })
  assert.deepEqual(parseDate('   ', ['day'], NOW), { kind: 'empty' })
})

test('the default field takes a full day only', () => {
  assert.equal(parseDate('2024-05-03', undefined, NOW).kind, 'ok')
  // a year or a month is a start of a day, not yet an error
  assert.equal(parseDate('2024', undefined, NOW).kind, 'partial')
  assert.equal(parseDate('2024-05', undefined, NOW).kind, 'partial')
  // ... which the field reports when it is left
  assert.equal(finalMessage('2024', undefined, NOW), 'Finish the date: YYYY-MM-DD.')
  assert.equal(finalMessage('2024-05-03', undefined, NOW), null)
  assert.equal(finalMessage('', undefined, NOW), null)
})

test('a field that takes year and month only refuses a day', () => {
  const allowed: DatePrecision[] = ['year', 'month']
  assert.equal(parseDate('2024', allowed, NOW).kind, 'ok')
  assert.equal(parseDate('2024-05', allowed, NOW).kind, 'ok')
  const refused = parseDate('2024-05-03', allowed, NOW)
  assert.equal(refused.kind, 'error')
  assert.ok(refused.kind === 'error' && refused.message.includes('YYYY or YYYY-MM'))
})

test('a year-only field takes a year and refuses more', () => {
  assert.equal(parseDate('1974', ['year'], NOW).kind, 'ok')
  assert.equal(parseDate('1974-05', ['year'], NOW).kind, 'error')
  assert.equal(finalMessage('1974-05', ['year'], NOW), 'This field takes YYYY.')
})

test('the years run from 1900 to next year', () => {
  assert.equal(lastYear(NOW), 2027)
  assert.equal(parseDate('1900', ALL, NOW).kind, 'ok')
  assert.equal(parseDate('2027-12-31', ALL, NOW).kind, 'ok')
  const early = parseDate('1899-12-31', ALL, NOW)
  assert.ok(early.kind === 'error' && early.message === `The year is between ${FIRST_YEAR} and 2027.`)
  assert.equal(parseDate('2028', ALL, NOW).kind, 'error')
  assert.equal(parseDate('0001', ALL, NOW).kind, 'error')
})

test('a month and a day must exist', () => {
  const month = parseDate('2024-13', ALL, NOW)
  assert.ok(month.kind === 'error' && month.message === '13 is not a month (1 to 12).')
  assert.equal(parseDate('2024-00', ALL, NOW).kind, 'error')
  const feb = parseDate('2023-02-29', ALL, NOW)
  assert.ok(feb.kind === 'error' && feb.message === '2023-02 has 28 days.')
  assert.equal(parseDate('2024-02-29', ALL, NOW).kind, 'ok')          // a leap year
  assert.equal(parseDate('1900-02-29', ALL, NOW).kind, 'error')       // not a leap year
  assert.equal(parseDate('2000-02-29', ALL, NOW).kind, 'ok')
  assert.equal(parseDate('2024-04-31', ALL, NOW).kind, 'error')
  assert.equal(parseDate('2024-05-00', ALL, NOW).kind, 'error')
})

test('what is not a date is an error that names the form', () => {
  for (const text of ['abc', '2024-05-03T10:00', '24', 'yesterday', '2024-05-03-1', '12345', '2024--05']) {
    const result = parseDate(text, ALL, NOW)
    assert.ok(result.kind === 'error' || result.kind === 'partial', text)
  }
  const junk = parseDate('abc', ALL, NOW)
  assert.ok(junk.kind === 'error' && junk.message === 'Write the date as YYYY, YYYY-MM or YYYY-MM-DD.')
  const only = parseDate('abc', ['day'], NOW)
  assert.ok(only.kind === 'error' && only.message === 'Write the date as YYYY-MM-DD.')
})

test('the start of a date is partial while typing', () => {
  for (const text of ['2', '20', '202', '2024-', '2024-0', '2024-05-', '2024-05-0']) {
    assert.equal(parseDate(text, ['day'], NOW).kind, 'partial', text)
  }
  // a full year is a year as soon as the field takes years
  assert.equal(parseDate('2024', ALL, NOW).kind, 'ok')
})

test('the hint names the forms a field takes', () => {
  assert.equal(formatHint(['day']), 'YYYY-MM-DD')
  assert.equal(formatHint(['year', 'month']), 'YYYY or YYYY-MM')
  assert.equal(formatHint(ALL), 'YYYY, YYYY-MM or YYYY-MM-DD')
  assert.equal(formatHint([]), 'YYYY-MM-DD')
})

test('canonical text, precision, truncation and the first day', () => {
  assert.equal(canonical(987, 5, 3, 'year'), '0987')
  assert.equal(canonical(2024, 5, 3, 'month'), '2024-05')
  assert.equal(canonical(2024, 5, 3, 'day'), '2024-05-03')
  assert.equal(precisionOf('2024'), 'year')
  assert.equal(precisionOf('2024-05'), 'month')
  assert.equal(precisionOf('2024-05-03'), 'day')
  assert.equal(precisionOf('2024-5'), null)
  assert.equal(precisionOf(''), null)
  assert.equal(truncateTo('2024-05-03', 'month'), '2024-05')
  assert.equal(truncateTo('2024-05-03', 'year'), '2024')
  assert.equal(truncateTo('2024-05', 'day'), '2024-05')      // a coarser text stays
  assert.equal(truncateTo('junk', 'year'), 'junk')
  assert.equal(firstDay('2024'), '2024-01-01')
  assert.equal(firstDay('2024-05'), '2024-05-01')
  assert.equal(firstDay('2024-05-03'), '2024-05-03')
})

test('the days of a month', () => {
  assert.equal(daysInMonth(2024, 2), 29)
  assert.equal(daysInMonth(2023, 2), 28)
  assert.equal(daysInMonth(2024, 12), 31)
  assert.equal(daysInMonth(2024, 4), 30)
})

test('today at a precision is in the local time zone', () => {
  assert.equal(todayText('day', NOW), '2026-10-12')
  assert.equal(todayText('month', NOW), '2026-10')
  assert.equal(todayText('year', NOW), '2026')
})

test('a page of the year grid has up to twelve years inside the bounds', () => {
  const page = yearPage(1974, NOW)
  assert.equal(page.years.length, 12)
  assert.ok(page.years.includes(1974))
  assert.deepEqual(yearPage(1900, NOW).years[0], 1900)
  const last = yearPage(2027, NOW)
  assert.equal(last.years[last.years.length - 1], 2027)
  assert.ok(last.years.includes(2027))
  // the page never leaves the bounds
  for (const year of [1900, 1905, 1950, 2020, 2027]) {
    const { years } = yearPage(year, NOW)
    assert.ok(years.every((y) => y >= 1900 && y <= 2027), String(year))
  }
})
