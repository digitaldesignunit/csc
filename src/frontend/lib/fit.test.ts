/**
 * The "Fits" search of Browse (decisions 8.169, 8.173): the URL parameters
 * read and built, what is sent to the backend, the words for a row's match and
 * the sort options of the card view.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { sortOptions, withParams, withoutFilters } from './browse'
import {
  DEFAULT_TOLERANCE,
  defaultSortKey,
  deviationText,
  fitBackendParams,
  fitChanges,
  fitChipLabel,
  fitRowLines,
  fitRowText,
  fitSizeText,
  parseFit,
  parseFitSize,
  parseFitTolerance,
  rowFit,
  percentText,
  volumeText,
  wasteText,
} from './fit'

const params = (text: string) => new URLSearchParams(text)

test('the size is three numbers above 0, any order, as typed', () => {
  assert.deepEqual(parseFitSize('200,1200,600'), [200, 1200, 600])
  assert.deepEqual(parseFitSize(' 1.5 , 2 ,3 '), [1.5, 2, 3])
  for (const bad of [null, undefined, '', '1,2', '1,2,3,4', '1,2,x', '0,1,2', '-1,2,3', '1,,3', '1,2,100001', '1e3,2,3']) {
    assert.equal(parseFitSize(bad), null, String(bad))
  }
})

test('the tolerance is a number with % or mm, at most 100 % or 100 m', () => {
  assert.equal(parseFitTolerance('10%'), '10%')
  assert.equal(parseFitTolerance(' 2.5 % '), '2.5%')
  assert.equal(parseFitTolerance('50MM'), '50mm')
  assert.equal(parseFitTolerance('0mm'), '0mm')
  for (const bad of [null, '', '10', '%', '-5%', '101%', 'abc', '5cm', '100001mm']) {
    assert.equal(parseFitTolerance(bad), null, String(bad))
  }
})

test('a fit needs a mode and three sizes; about gets the default tolerance', () => {
  assert.deepEqual(parseFit(params('fit_mode=about&fit_size=1200,600,200')),
    { mode: 'about', size: [1200, 600, 200], tolerance: DEFAULT_TOLERANCE })
  assert.deepEqual(parseFit(params('fit_mode=about&fit_size=1200,600,200&fit_tol=50mm')),
    { mode: 'about', size: [1200, 600, 200], tolerance: '50mm' })
  // an unusable tolerance falls back to the default instead of dropping the search
  assert.equal(parseFit(params('fit_mode=about&fit_size=1,2,3&fit_tol=x'))?.tolerance, DEFAULT_TOLERANCE)
  // can hold takes none, whatever the link says
  assert.deepEqual(parseFit(params('fit_mode=can_hold&fit_size=1,2,3&fit_tol=5%')),
    { mode: 'can_hold', size: [1, 2, 3], tolerance: null })
  for (const bad of ['', 'fit_size=1,2,3', 'fit_mode=about', 'fit_mode=near&fit_size=1,2,3', 'fit_mode=about&fit_size=1,2']) {
    assert.equal(parseFit(params(bad)), null, bad)
  }
})

test('only a usable fit goes on to the backend', () => {
  assert.deepEqual(fitBackendParams(params('fit_mode=about&fit_size=200,1200,600')),
    { fit_mode: 'about', fit_size: '200,1200,600', fit_tol: '10%' })
  assert.deepEqual(fitBackendParams(params('fit_mode=can_hold&fit_size=1,2,3&fit_tol=5%')),
    { fit_mode: 'can_hold', fit_size: '1,2,3' })
  assert.deepEqual(fitBackendParams(params('fit_mode=about&fit_size=oops')), {})
  assert.deepEqual(fitBackendParams(params('fit_size=1,2,3')), {})
})

test('building the URL: the default tolerance is not written, a search removes cleanly', () => {
  const none = { sortkey: null, sortorder: null }
  assert.deepEqual(fitChanges({ mode: 'about', size: [1200, 600, 200], tolerance: '10%' }, true),
    { fit_mode: 'about', fit_size: '1200,600,200', fit_tol: null })
  assert.deepEqual(fitChanges({ mode: 'about', size: [1, 2, 3], tolerance: '50mm' }, true),
    { fit_mode: 'about', fit_size: '1,2,3', fit_tol: '50mm' })
  assert.deepEqual(fitChanges({ mode: 'can_hold', size: [1, 2, 3], tolerance: '50mm' }, true),
    { fit_mode: 'can_hold', fit_size: '1,2,3', fit_tol: null })
  assert.deepEqual(fitChanges(null, true), { fit_mode: null, fit_size: null, fit_tol: null, ...none })
  const next = withParams(params('page=3&dataset=d'), fitChanges({ mode: 'about', size: [1, 2, 3], tolerance: '7%' }, false))
  assert.deepEqual(parseFit(next), { mode: 'about', size: [1, 2, 3], tolerance: '7%' })
  assert.equal(next.get('page'), null)
  // "Clear all" drops the fit with the other filters
  assert.equal(withoutFilters(next).toString(), '')
})

test('a fit that starts or ends resets the sort, one that changes keeps it', () => {
  const fit = { mode: 'about' as const, size: [1, 2, 3] as [number, number, number], tolerance: '10%' }
  // an old explicit sort does not beat the match of a new fit
  const started = withParams(params('sortkey=name&sortorder=desc&dataset=d'), fitChanges(fit, false))
  assert.equal(started.get('sortkey'), null)
  assert.equal(started.get('sortorder'), null)
  assert.equal(started.get('dataset'), 'd')
  assert.equal(defaultSortKey(started), 'match')
  // changing the size of an active fit keeps the sort the user chose
  const changed = withParams(started, { sortkey: 'volume' })
  const edited = withParams(changed, fitChanges({ ...fit, size: [4, 5, 6] }, true))
  assert.equal(edited.get('sortkey'), 'volume')
  // removing the fit takes sortkey=match with it
  const sorted = withParams(started, { sortkey: 'match', sortorder: 'desc' })
  const removed = withParams(sorted, fitChanges(null, true))
  assert.equal(removed.get('sortkey'), null)
  assert.equal(removed.get('sortorder'), null)
  assert.equal(parseFit(removed), null)
})

test('the chip and the size read largest first', () => {
  assert.equal(fitSizeText([200, 1200, 600]), '1200 x 600 x 200 mm')
  assert.equal(fitChipLabel({ mode: 'about', size: [200, 1200, 600], tolerance: '10%' }),
    'About 1200 x 600 x 200 mm (10 %)')
  assert.equal(fitChipLabel({ mode: 'about', size: [1, 2, 3], tolerance: '50mm' }), 'About 3 x 2 x 1 mm (50 mm)')
  assert.equal(fitChipLabel({ mode: 'can_hold', size: [1, 2, 3], tolerance: null }), 'Can hold 3 x 2 x 1 mm')
})

test('the match of a row reads as a deviation or a waste', () => {
  assert.equal(deviationText(0), 'exact')
  assert.equal(deviationText(0.0004), 'exact')
  assert.equal(deviationText(0.083), '8.3 % off')
  assert.equal(deviationText(0.1), '10 % off')
  assert.equal(deviationText(0.256), '26 % off')
  // volumes: m3 with two significant digits, never an exponent
  assert.equal(volumeText(1_700_000), '0.0017 m3')
  assert.equal(volumeText(120_000_000), '0.12 m3')
  assert.equal(volumeText(1_500_000_000), '1.5 m3')
  assert.equal(volumeText(12_400_000_000), '12 m3')
  assert.equal(volumeText(1_000_000_000), '1 m3')
  assert.equal(volumeText(996_000_000), '1 m3')
  assert.equal(volumeText(123_000_000_000), '120 m3')
  assert.equal(volumeText(5_000), '0.000005 m3')
  assert.equal(percentText(0.4), '<1 %')
  assert.equal(percentText(1), '1 %')
  assert.equal(percentText(41.4), '41 %')
  assert.equal(percentText(99.6), '100 %')
  assert.equal(wasteText(0, 0), 'no waste')
  // tiny, small, large
  assert.equal(wasteText(1_700_000, 0.4), '<1 % waste (0.0017 m3)')
  assert.equal(wasteText(120_000_000, 41.2), '41 % waste (0.12 m3)')
  assert.equal(wasteText(1_500_000_000, 63.5), '64 % waste (1.5 m3)')
  // a batch: the size is one piece's, so is the waste
  assert.equal(wasteText(120_000_000, 41.2, 5), '41 % waste (0.12 m3) per piece')
  assert.equal(fitRowText({ mode: 'about', deviation: 0.05 }), '5.0 % off')
  assert.equal(fitRowText({ mode: 'can_hold', waste_mm3: 1e9, waste_percent: 50 }), '50 % waste (1 m3)')
  assert.equal(fitRowText(null), '')
  // a batch: the size is one piece's, so is the waste
  const held = { mode: 'can_hold' as const, waste_mm3: 12_400_000, waste_percent: 41 }
  assert.equal(fitRowText(held, 4), '41 % waste (0.012 m3) per piece')
  assert.equal(fitRowText(held, 1), '41 % waste (0.012 m3)')
  assert.equal(fitRowText({ ...held, waste_mm3: 0, waste_percent: 0 }, 4), 'no waste')
  assert.equal(fitRowText({ mode: 'about', deviation: 0.083 }, 4), '8.3 % off')
})

test('the match on two lines for a narrow cell', () => {
  const held = { mode: 'can_hold' as const, waste_mm3: 120_000_000, waste_percent: 41.2 }
  assert.deepEqual(fitRowLines(held), ['41 % waste', '0.12 m3'])
  assert.deepEqual(fitRowLines(held, 3), ['41 % waste', '0.12 m3 per piece'])
  assert.deepEqual(fitRowLines({ ...held, waste_mm3: 1_700_000, waste_percent: 0.4 }), ['<1 % waste', '0.0017 m3'])
  assert.deepEqual(fitRowLines({ ...held, waste_mm3: 0, waste_percent: 0 }, 3), ['no waste'])
  assert.deepEqual(fitRowLines({ mode: 'about', deviation: 0.083 }, 3), ['8.3 % off'])
  assert.deepEqual(fitRowLines(null), [])
  // the one-line text of a card is the same words
  assert.equal(fitRowText(held, 3), '41 % waste (0.12 m3) per piece')
})

test('a row carries a match only when the backend sent a usable one', () => {
  assert.deepEqual(rowFit({ fit: { mode: 'about', deviation: 0.1 } }), { mode: 'about', deviation: 0.1 })
  assert.deepEqual(rowFit({ fit: { mode: 'can_hold', waste_mm3: 5, waste_percent: 2 } }),
    { mode: 'can_hold', waste_mm3: 5, waste_percent: 2 })
  for (const bad of [null, undefined, {}, { fit: null }]) {
    assert.equal(rowFit(bad), null, JSON.stringify(bad))
  }
})

test('the sort: match is the default under a fit and one of the options only then', () => {
  assert.equal(defaultSortKey(params('')), '_id')
  assert.equal(defaultSortKey(params('fit_mode=about&fit_size=1,2,3')), 'match')
  assert.equal(defaultSortKey(params('fit_mode=about')), '_id')
  const plain = sortOptions(false).map((o) => o.value)
  assert.ok(!plain.includes('match'))
  assert.deepEqual(sortOptions(true).map((o) => o.value), ['match', ...plain])
  for (const key of ['catalog_number', 'name', 'effective_from', 'created', 'volume']) {
    assert.ok(plain.includes(key), key)
  }
})
