/**
 * The "Near" search of Browse (decisions 8.170, 8.173): the pasted "lat, lon",
 * the URL parameters read and built, what is sent to the backend, the sort
 * options and the words for a distance.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { sortOptions, withParams, withoutFilters } from './browse'
import { defaultSortKey, fitChanges } from './fit'
import {
  coordinateText,
  latLonEdit,
  pairFromText,
  type LatLonBoxes,
  boxesOfLocation,
  distanceText,
  INVALID_LOCATION,
  latLonText,
  locationFromBoxes,
  locationProblem,
  nearBackendParams,
  nearChanges,
  nearChipLabel,
  nearThisPieceLink,
  originLocationProblem,
  parseCoordinate,
  parseLatLon,
  parseNear,
  parseRadius,
  rowDistance,
} from './near'

const params = (text: string) => new URLSearchParams(text)

test('a pasted point is two numbers on the globe, however they are separated', () => {
  const expected = { lat: 49.8728, lon: 8.6512 }
  for (const text of [
    '49.8728, 8.6512',
    '49.8728,8.6512',
    '  49.8728 ,   8.6512  ',
    '49.8728 8.6512',
    '49.8728;8.6512',
    '49.8728\t8.6512',
    '(49.8728, 8.6512)',
    '[49.8728, 8.6512]',
    '49.8728\u00b0, 8.6512\u00b0',
    '+49.8728, +8.6512',
  ]) {
    assert.deepEqual(parseLatLon(text), expected, text)
  }
  assert.deepEqual(parseLatLon('-33.86, 151.21'), { lat: -33.86, lon: 151.21 })
  assert.deepEqual(parseLatLon('90, -180'), { lat: 90, lon: -180 })
  assert.deepEqual(parseLatLon('0, 0'), { lat: 0, lon: 0 })
  for (const bad of [
    null, undefined, '', ' ', '49.8728', '49.8728,', ',8.65', '1, 2, 3', 'a, b', '49.8728, x',
    '91, 8', '-90.5, 8', '49, 181', '49, -180.1', '49,87 8,65', '1e2, 3', 'NaN, 1', '49..8, 8',
  ]) {
    assert.equal(parseLatLon(bad), null, String(bad))
  }
})

test('a single coordinate is a plain number inside its range', () => {
  assert.equal(parseCoordinate(' 49.5 ', 'lat'), 49.5)
  assert.equal(parseCoordinate('-179.99', 'lon'), -179.99)
  assert.equal(parseCoordinate('90', 'lat'), 90)
  assert.equal(parseCoordinate('90.01', 'lat'), null)
  assert.equal(parseCoordinate('180', 'lon'), 180)
  assert.equal(parseCoordinate('181', 'lon'), null)
  assert.equal(parseCoordinate('', 'lat'), null)
  assert.equal(parseCoordinate(null, 'lat'), null)
  assert.equal(parseCoordinate('4e1', 'lat'), null)
})

test('coordinates are written with at most six decimals and no tail of zeros', () => {
  assert.equal(coordinateText(49.8728), '49.8728')
  assert.equal(coordinateText(49.12345678), '49.123457')
  assert.equal(coordinateText(8), '8')
  assert.equal(coordinateText(-0.5), '-0.5')
  assert.equal(latLonText(49.8728, 8.6512), '49.8728, 8.6512')
  // the written pair reads back as the same point
  assert.deepEqual(parseLatLon(latLonText(49.123457, -8.000001)), { lat: 49.123457, lon: -8.000001 })
})

test('the radius is a number above 0 km', () => {
  assert.equal(parseRadius('50'), 50)
  assert.equal(parseRadius(' 0.5 '), 0.5)
  for (const bad of [null, undefined, '', '0', '-1', 'x', '1e3', '100001']) {
    assert.equal(parseRadius(bad), null, String(bad))
  }
})

test('a near search needs a usable point; a bad radius is left out, the search stays', () => {
  assert.deepEqual(parseNear(params('near_lat=49.8728&near_lon=8.6512')),
    { lat: 49.8728, lon: 8.6512, layer: 'current', radiusKm: null })
  assert.deepEqual(parseNear(params('near_lat=49.8&near_lon=8.6&near_layer=origin&radius_km=50')),
    { lat: 49.8, lon: 8.6, layer: 'origin', radiusKm: 50 })
  // a layer that does not exist is the current one
  assert.equal(parseNear(params('near_lat=1&near_lon=2&near_layer=sky'))?.layer, 'current')
  assert.equal(parseNear(params('near_lat=1&near_lon=2&radius_km=0'))?.radiusKm, null)
  for (const bad of ['', 'near_lat=49', 'near_lon=8', 'near_lat=91&near_lon=8', 'near_lat=x&near_lon=8',
    'radius_km=5', 'near_layer=origin']) {
    assert.equal(parseNear(params(bad)), null, bad)
  }
})

test('only a usable search goes on to the backend', () => {
  assert.deepEqual(nearBackendParams(params('near_lat=49.8728&near_lon=8.6512&dataset=d')),
    { near_lat: '49.8728', near_lon: '8.6512', near_layer: 'current' })
  assert.deepEqual(nearBackendParams(params('near_lat=1&near_lon=2&near_layer=origin&radius_km=12.5')),
    { near_lat: '1', near_lon: '2', near_layer: 'origin', radius_km: '12.5' })
  assert.deepEqual(nearBackendParams(params('near_lat=49')), {})
  assert.deepEqual(nearBackendParams(params('near_lat=95&near_lon=8')), {})
  assert.deepEqual(nearBackendParams(params('radius_km=5')), {})
})

test('building the URL: the default layer is not written, a search removes cleanly', () => {
  const none = { sortkey: null, sortorder: null }
  assert.deepEqual(nearChanges({ lat: 49.8728, lon: 8.6512, layer: 'current', radiusKm: null }, true),
    { near_lat: '49.8728', near_lon: '8.6512', near_layer: null, radius_km: null })
  assert.deepEqual(nearChanges({ lat: 1, lon: 2, layer: 'origin', radiusKm: 30 }, true),
    { near_lat: '1', near_lon: '2', near_layer: 'origin', radius_km: '30' })
  assert.deepEqual(nearChanges(null, true),
    { near_lat: null, near_lon: null, near_layer: null, radius_km: null, ...none })
  // the round trip: set, read back, remove
  const set = withParams(params('page=3&dataset=d'), nearChanges({ lat: 49.8, lon: 8.6, layer: 'origin', radiusKm: 5 }))
  assert.deepEqual(parseNear(set), { lat: 49.8, lon: 8.6, layer: 'origin', radiusKm: 5 })
  assert.equal(set.get('page'), null)
  assert.equal(set.get('dataset'), 'd')
  assert.equal(withParams(set, nearChanges(null, true)).toString(), 'dataset=d')
  // "Clear all" drops the near search with the other filters
  assert.equal(withoutFilters(set).toString(), '')
})

test('a near search that starts or ends resets the sort, one that changes keeps it', () => {
  const near = { lat: 1, lon: 2, layer: 'current' as const, radiusKm: null }
  const started = withParams(params('sortkey=name&sortorder=desc&dataset=d'), nearChanges(near, false))
  assert.equal(started.get('sortkey'), null)
  assert.equal(started.get('sortorder'), null)
  assert.equal(started.get('dataset'), 'd')
  assert.equal(defaultSortKey(started), 'distance')
  const chosen = withParams(started, { sortkey: 'volume' })
  const edited = withParams(chosen, nearChanges({ ...near, radiusKm: 10 }, true))
  assert.equal(edited.get('sortkey'), 'volume')
  const sorted = withParams(started, { sortkey: 'distance', sortorder: 'desc' })
  const removed = withParams(sorted, nearChanges(null, true))
  assert.equal(removed.get('sortkey'), null)
  assert.equal(removed.get('sortorder'), null)
  assert.equal(parseNear(removed), null)
})

test('the default sort: distance under a near search, also with a fit; else match; else the id', () => {
  const fit = 'fit_mode=about&fit_size=1,2,3'
  const near = 'near_lat=1&near_lon=2'
  assert.equal(defaultSortKey(params('')), '_id')
  assert.equal(defaultSortKey(params(fit)), 'match')
  assert.equal(defaultSortKey(params(near)), 'distance')
  assert.equal(defaultSortKey(params(`${fit}&${near}`)), 'distance')
  assert.equal(defaultSortKey(params('near_lat=1')), '_id')
  // a fit that starts while a near search runs leaves the distance the sort
  const withFit = withParams(params(near), fitChanges({ mode: 'about', size: [1, 2, 3], tolerance: '10%' }, false))
  assert.equal(defaultSortKey(withFit), 'distance')
})

test('the sort options offer the distance only while a near search is set', () => {
  const plain = sortOptions(false).map((o) => o.value)
  assert.ok(!plain.includes('distance'))
  assert.deepEqual(sortOptions(false, false).map((o) => o.value), plain)
  assert.deepEqual(sortOptions(false, true).map((o) => o.value), ['distance', ...plain])
  assert.deepEqual(sortOptions(true, true).map((o) => o.value), ['distance', 'match', ...plain])
  assert.deepEqual(sortOptions(true).map((o) => o.value), ['match', ...plain])
  assert.equal(sortOptions(false, true)[0].label, 'Distance')
})

test('the chip names the point, the layer and the radius', () => {
  assert.equal(nearChipLabel({ lat: 49.8728, lon: 8.6512, layer: 'current', radiusKm: null }),
    'Near 49.8728, 8.6512 (current)')
  assert.equal(nearChipLabel({ lat: 49.8728, lon: 8.6512, layer: 'origin', radiusKm: 50 }),
    'Near 49.8728, 8.6512 (origin, within 50 km)')
})

test('a distance reads in metres under 1 km, else in km with one decimal', () => {
  assert.equal(distanceText(0), '0 m')
  assert.equal(distanceText(0.4), '0 m')
  assert.equal(distanceText(850.4), '850 m')
  assert.equal(distanceText(999.4), '999 m')
  assert.equal(distanceText(999.6), '1.0 km')
  assert.equal(distanceText(1000), '1.0 km')
  assert.equal(distanceText(26_512), '26.5 km')
  assert.equal(distanceText(443_700), '443.7 km')
  assert.equal(distanceText(12_345_678), '12345.7 km')
})

test('a row carries a distance only when the backend sent a usable one', () => {
  assert.equal(rowDistance({ distance_m: 120.5 }), 120.5)
  assert.equal(rowDistance({ distance_m: 0 }), 0)
  for (const bad of [null, undefined, {}, { distance_m: null }, { distance_m: -1 }, { distance_m: Number.NaN }]) {
    assert.equal(rowDistance(bad), null, JSON.stringify(bad))
  }
})

test('"Near this piece" opens Browse at the current place, else the origin place, else nowhere', () => {
  const here = { lat: 49.8728, lon: 8.6512 }
  const there = { lat: 52.52, lon: 13.405 }
  assert.equal(nearThisPieceLink(here, there), '/components?near_lat=49.8728&near_lon=8.6512')
  assert.equal(nearThisPieceLink(here, null), '/components?near_lat=49.8728&near_lon=8.6512')
  assert.equal(nearThisPieceLink(null, there), '/components?near_lat=52.52&near_lon=13.405&near_layer=origin')
  assert.equal(nearThisPieceLink(undefined, there), '/components?near_lat=52.52&near_lon=13.405&near_layer=origin')
  assert.equal(nearThisPieceLink(null, null), null)
  assert.equal(nearThisPieceLink(undefined, undefined), null)
  // a place off the globe is no place
  assert.equal(nearThisPieceLink({ lat: 95, lon: 0 }, there), '/components?near_lat=52.52&near_lon=13.405&near_layer=origin')
  // the link is read back by Browse as the search it names
  const link = nearThisPieceLink(null, there) as string
  assert.deepEqual(parseNear(new URLSearchParams(link.split('?')[1])),
    { lat: 52.52, lon: 13.405, layer: 'origin', radiusKm: null })
})

test('the two coordinate boxes of the origin form make a point, none, or a problem', () => {
  assert.deepEqual(locationFromBoxes('49.8728', '8.6512'), { location: { lat: 49.8728, lon: 8.6512 }, problem: null })
  assert.deepEqual(locationFromBoxes(' -33.5 ', ' 151 '), { location: { lat: -33.5, lon: 151 }, problem: null })
  // both empty: the origin has no location
  assert.deepEqual(locationFromBoxes('', ' '), { location: null, problem: null })
  for (const [lat, lon] of [['49.8', ''], ['', '8.6'], ['91', '8'], ['49', '181'], ['x', '8'], ['49', '8.6.1']]) {
    const found = locationFromBoxes(lat, lon)
    assert.equal(found.location, null, `${lat} / ${lon}`)
    assert.match(found.problem ?? '', /Latitude/, `${lat} / ${lon}`)
  }
})

/** Types `text` one character at a time into the boxes, the way the form does: the
 *  character goes to the focused box, and a `focus` answer moves the focus. */
function typeInto(text: string, start: 'lat' | 'lon' = 'lat', from: LatLonBoxes = { lat: '', lon: '' }) {
  let boxes = from
  let focused: 'lat' | 'lon' = start
  for (const char of text) {
    const result = latLonEdit(focused, boxes, boxes[focused] + char)
    boxes = result.boxes
    if (result.focus) focused = result.focus
  }
  return { boxes, focused }
}

test('a pair typed character by character goes latitude, comma, longitude', () => {
  assert.deepEqual(typeInto('49.8728, 8.6512'), { boxes: { lat: '49.8728', lon: '8.6512' }, focused: 'lon' })
  assert.deepEqual(typeInto('49.8728,8.6512').boxes, { lat: '49.8728', lon: '8.6512' })
  assert.deepEqual(typeInto('-33.5 ;  151.25').boxes, { lat: '-33.5', lon: '151.25' })
  // the comma is not inserted into the latitude
  const comma = latLonEdit('lat', { lat: '', lon: '' }, '49.8728,')
  assert.deepEqual(comma, { boxes: { lat: '49.8728', lon: '' }, focus: 'lon' })
  assert.deepEqual(latLonEdit('lat', { lat: '', lon: '' }, '49.8728 ,  '), { boxes: { lat: '49.8728', lon: '' }, focus: 'lon' })
  // a comma that follows no number is typed as it is, and the focus stays
  assert.deepEqual(latLonEdit('lat', { lat: '', lon: '' }, ','), { boxes: { lat: ',', lon: '' }, focus: null })
  // the longitude has no such rule
  assert.deepEqual(latLonEdit('lon', { lat: '49', lon: '' }, '8,'), { boxes: { lat: '49', lon: '8,' }, focus: null })
  // spaces alone do not split the box while typing; a pair left in a box is read when it is left
  const spaced = typeInto('49.8728 8.6512')
  assert.deepEqual(spaced.boxes, { lat: '49.8728 8.6512', lon: '' })
  assert.deepEqual(pairFromText(spaced.boxes.lat), { lat: '49.8728', lon: '8.6512' })
  // typing into the longitude box keeps the latitude; leading spaces go
  assert.deepEqual(typeInto(' 8.65', 'lon', { lat: '49.8', lon: '' }).boxes, { lat: '49.8', lon: '8.65' })
})

test('a pair in either box fills both boxes, a single number is a normal paste', () => {
  const filled = { lat: '49.8728', lon: '8.6512' }
  assert.deepEqual(latLonEdit('lat', { lat: '', lon: '' }, '49.8728, 8.6512'), { boxes: filled, focus: null })
  assert.deepEqual(latLonEdit('lon', { lat: '', lon: '' }, '49.8728, 8.6512'), { boxes: filled, focus: null })
  // over what the boxes held before
  assert.deepEqual(latLonEdit('lat', { lat: '1', lon: '2' }, '  (49.8728 ; 8.6512) '), { boxes: filled, focus: null })
  assert.deepEqual(latLonEdit('lon', { lat: '1', lon: '2' }, '49.8728\u00b0 8.6512\u00b0'), { boxes: filled, focus: null })
  assert.deepEqual(latLonEdit('lat', { lat: '', lon: '8' }, '49.8728'), { boxes: { lat: '49.8728', lon: '8' }, focus: null })
  assert.deepEqual(latLonEdit('lon', { lat: '49', lon: '' }, '8.6512'), { boxes: { lat: '49', lon: '8.6512' }, focus: null })
  // a pair off the globe is no pair: it stays as typed in its box
  assert.deepEqual(latLonEdit('lat', { lat: '', lon: '' }, '95, 8.6'), { boxes: { lat: '95, 8.6', lon: '' }, focus: null })
  assert.equal(pairFromText('49.8728, 8.6512')?.lon, '8.6512')
  assert.equal(pairFromText('49.8728'), null)
  assert.equal(pairFromText(''), null)
  assert.equal(pairFromText(null), null)
})

test('a form that holds no point on the globe cannot be saved', () => {
  assert.equal(locationProblem(null), null)
  assert.equal(locationProblem(undefined), null)
  assert.equal(locationProblem({ lat: 49.8, lon: 8.6 }), null)
  assert.equal(locationProblem({ lat: 0, lon: 0 }), null)
  assert.ok(locationProblem(INVALID_LOCATION))
  assert.ok(locationProblem({ lat: 95, lon: 0 }))
  assert.equal(originLocationProblem(null), null)
  assert.equal(originLocationProblem({ place: null }), null)
  assert.equal(originLocationProblem({ place: { location: null } }), null)
  assert.equal(originLocationProblem({ place: { location: { lat: 49.8, lon: 8.6 } } }), null)
  assert.ok(originLocationProblem({ place: { location: INVALID_LOCATION } }))
})

test('a stored location fills the coordinate boxes as plain decimals that read back', () => {
  assert.deepEqual(boxesOfLocation(null), { lat: '', lon: '' })
  assert.deepEqual(boxesOfLocation(undefined), { lat: '', lon: '' })
  assert.deepEqual(boxesOfLocation({ lat: 49.8728, lon: 8.6512 }), { lat: '49.8728', lon: '8.6512' })
  assert.deepEqual(boxesOfLocation({ lat: -33.5, lon: 151 }), { lat: '-33.5', lon: '151' })
  // below the six decimals the boxes keep (about 10 cm) a coordinate shows as 0, never as an exponent
  for (const [lat, lon] of [[1e-7, -0], [-1e-7, 1e-9], [0, 0], [5e-7, -5e-7]]) {
    const boxes = boxesOfLocation({ lat, lon })
    assert.equal(boxes.lat + boxes.lon, '00', `${lat} ${lon}`)
    assert.deepEqual(locationFromBoxes(boxes.lat, boxes.lon).location, { lat: 0, lon: 0 })
  }
  assert.equal(String(1e-7), '1e-7')
  assert.equal(locationFromBoxes(String(1e-7), '0').problem !== null, true)
})
