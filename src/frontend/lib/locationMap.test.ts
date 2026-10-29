/**
 * The Location Map page (decisions 8.170, 8.171): the layer in the URL, the
 * query the backend takes, the links to Browse, the box the map fits and the
 * words about the pieces without a point.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { withParams } from './browse'
import { parseNear } from './near'
import {
  DEFAULT_MAP_LAYER,
  TILE_ATTRIBUTION,
  TILE_HOST,
  TILE_URL,
  boundsOf,
  clampLat,
  clickedPointText,
  emptyLayerText,
  layerChanges,
  locationsBackendParams,
  mapCountText,
  parseLayer,
  searchNearHereLink,
  showAsListLink,
  wrapLon,
} from './locationMap'

const params = (text: string) => new URLSearchParams(text)

test('the layer is Current unless the URL says origin, and Current is not written', () => {
  assert.equal(DEFAULT_MAP_LAYER, 'current')
  assert.equal(parseLayer(params('')), 'current')
  assert.equal(parseLayer(params('layer=origin')), 'origin')
  assert.equal(parseLayer(params('layer=current')), 'current')
  assert.equal(parseLayer(params('layer=sky')), 'current')
  assert.deepEqual(layerChanges('origin'), { layer: 'origin' })
  assert.deepEqual(layerChanges('current'), { layer: null })
  // the round trip through the URL
  const origin = withParams(params('dataset=d'), layerChanges('origin'))
  assert.equal(parseLayer(origin), 'origin')
  assert.equal(origin.get('dataset'), 'd')
  assert.equal(parseLayer(withParams(origin, layerChanges('current'))), 'current')
  assert.equal(withParams(origin, layerChanges('current')).toString(), 'dataset=d')
})

test('the backend gets the circulation, the filters, a usable search and the layer', () => {
  assert.equal(locationsBackendParams(params('')).toString(), 'circulation=active&layer=current')
  const full = locationsBackendParams(params(
    'circulation=all&material=timber&dataset=d&q=beam&bbx_min_x=100&fit_mode=can_hold&fit_size=240,200,100'
    + '&near_lat=50.1109&near_lon=8.6821&radius_km=30&layer=origin&page=4&sortkey=name'))
  assert.equal(full.get('circulation'), 'all')
  assert.equal(full.get('material'), 'timber')
  assert.equal(full.get('dataset'), 'd')
  assert.equal(full.get('q'), 'beam')
  assert.equal(full.get('bbx_min_x'), '100')
  assert.equal(full.get('fit_mode'), 'can_hold')
  assert.equal(full.get('fit_size'), '240,200,100')
  assert.equal(full.get('near_lat'), '50.1109')
  assert.equal(full.get('near_layer'), 'current')
  assert.equal(full.get('radius_km'), '30')
  assert.equal(full.get('layer'), 'origin')
  // no paging and no sort: the map takes every point
  assert.equal(full.get('page'), null)
  assert.equal(full.get('sortkey'), null)
  // an unusable circulation, fit or near search is left out, not sent
  const bad = locationsBackendParams(params('circulation=x&fit_mode=about&fit_size=oops&near_lat=95&near_lon=8'))
  assert.equal(bad.toString(), 'circulation=active&layer=current')
})

test('"Show as list" keeps every filter and drops the layer and the page', () => {
  assert.equal(showAsListLink(params('')), '/components')
  assert.equal(showAsListLink(params('layer=origin')), '/components')
  assert.equal(
    showAsListLink(params('dataset=d&circulation=all&fit_mode=about&fit_size=1,2,3&near_lat=1&near_lon=2&layer=origin&page=2')),
    '/components?dataset=d&circulation=all&fit_mode=about&fit_size=1%2C2%2C3&near_lat=1&near_lon=2')
})

test('"Search near here" sets the clicked point on the layer shown, with no radius', () => {
  const link = searchNearHereLink(params('dataset=d&layer=origin'), 49.87281234, 8.65121234, 'origin')
  assert.ok(link.startsWith('/components?'))
  const query = params(link.split('?')[1])
  assert.deepEqual(parseNear(query), { lat: 49.872812, lon: 8.651212, layer: 'origin', radiusKm: null })
  assert.equal(query.get('dataset'), 'd')
  assert.equal(query.get('layer'), null)
  // the current layer is the default and is not written, Browse reads it the same
  const current = params(searchNearHereLink(params(''), 50.1109, 8.6821, 'current').split('?')[1])
  assert.equal(current.get('near_layer'), null)
  assert.deepEqual(parseNear(current), { lat: 50.1109, lon: 8.6821, layer: 'current', radiusKm: null })
  // an earlier near search, its radius and the sort are replaced
  const again = params(searchNearHereLink(
    params('near_lat=1&near_lon=2&near_layer=origin&radius_km=5&sortkey=name&page=3'), 50, 8, 'current').split('?')[1])
  assert.deepEqual(parseNear(again), { lat: 50, lon: 8, layer: 'current', radiusKm: null })
  assert.equal(again.get('radius_km'), null)
  assert.equal(again.get('sortkey'), null)
  assert.equal(again.get('page'), null)
})

test('a click beyond the poles or on another copy of the world is the same place', () => {
  assert.equal(clampLat(95), 90)
  assert.equal(clampLat(-120.5), -90)
  assert.equal(clampLat(49.8728), 49.8728)
  assert.equal(wrapLon(8.65), 8.65)
  assert.equal(wrapLon(188.65), -171.35)
  assert.equal(wrapLon(-188.65), 171.35)
  assert.equal(wrapLon(540), -180)
  const link = searchNearHereLink(params(''), 99, 368.65, 'current')
  assert.deepEqual(parseNear(params(link.split('?')[1])), { lat: 90, lon: 8.65, layer: 'current', radiusKm: null })
})

test('the popup shows the point that "Search near here" searches', () => {
  assert.equal(clickedPointText(49.87281234, 8.65121234), '49.872812, 8.651212')
  assert.equal(clickedPointText(49.8728, 368.65), '49.8728, 8.65')
  assert.equal(clickedPointText(-33.5, -188.65), '-33.5, 171.35')
  assert.equal(clickedPointText(99, 540), '90, -180')
  // the text and the link name the same point, on any copy of the world
  for (const [lat, lon] of [[49.87, 8.65], [49.87, 368.65], [49.87, -351.35], [95, 10]]) {
    const near = parseNear(params(searchNearHereLink(params(''), lat, lon, 'current').split('?')[1]))!
    assert.equal(clickedPointText(lat, lon), `${near.lat}, ${near.lon}`)
  }
})

test('the map fits the points, and one site gets a box of about a kilometre', () => {
  assert.equal(boundsOf([]), null)
  assert.deepEqual(boundsOf([{ lat: 49.8, lon: 8.6 }, { lat: 50.1, lon: 8.7 }, { lat: 49.9, lon: 8.2 }]),
    [[49.8, 8.2], [50.1, 8.7]])
  const site = boundsOf([{ lat: 49.86, lon: 8.67 }, { lat: 49.86, lon: 8.67 }])!
  assert.ok(Math.abs(site[1][0] - site[0][0] - 0.01) < 1e-9)
  assert.ok(Math.abs(site[1][1] - site[0][1] - 0.01) < 1e-9)
  assert.ok(site[0][0] < 49.86 && site[1][0] > 49.86 && site[0][1] < 8.67 && site[1][1] > 8.67)
  // a wide box is left as it is, one narrow side is widened
  const line = boundsOf([{ lat: 49.86, lon: 8.0 }, { lat: 49.86, lon: 9.0 }])!
  assert.equal(line[1][1] - line[0][1], 1)
  assert.ok(line[1][0] - line[0][0] >= 0.0099)
})

test('the page says how many pieces are on the map and how many have no point', () => {
  assert.equal(mapCountText('current', { total: 697, displayed: 697, left_out: 0 }), '697 elements on the map')
  assert.equal(mapCountText('current', { total: 1, displayed: 1, left_out: 0 }), '1 element on the map')
  assert.equal(mapCountText('origin', { total: 697, displayed: 2, left_out: 695 }),
    '2 elements on the map; 695 have no origin location.')
  assert.equal(mapCountText('current', { total: 5, displayed: 4, left_out: 1 }),
    '4 elements on the map; 1 has no current location.')
  assert.equal(mapCountText('origin', { total: 697, displayed: 0, left_out: 697 }),
    'None of the 697 elements has an origin location to show.')
  assert.equal(mapCountText('current', { total: 3, displayed: 0, left_out: 3 }),
    'None of the 3 elements has a current location to show.')
  assert.equal(mapCountText('current', { total: 0, displayed: 0, left_out: 0 }), 'No elements match the filters.')
  assert.match(emptyLayerText('origin', 697), /origin location/)
  assert.match(emptyLayerText('origin', 697), /Edit provenance/)
  assert.match(emptyLayerText('current', 5), /current location/)
  assert.match(emptyLayerText('origin', 0), /No elements match/)
})

test('the tiles come from one host, with the attribution of OpenStreetMap and FOSSGIS', () => {
  assert.equal(TILE_URL, `${TILE_HOST}/{z}/{x}/{y}.png`)
  assert.equal(TILE_HOST, 'https://tile.openstreetmap.de')
  assert.match(TILE_ATTRIBUTION, /\(c\) <a href="https:\/\/www\.openstreetmap\.org\/copyright"[^>]*>OpenStreetMap contributors<\/a>/)
  assert.match(TILE_ATTRIBUTION, /tiles by <a href="https:\/\/fossgis\.de"[^>]*>FOSSGIS e\.V\.<\/a>/)
  assert.ok(![...TILE_ATTRIBUTION].some((c) => c.charCodeAt(0) > 127))
})
