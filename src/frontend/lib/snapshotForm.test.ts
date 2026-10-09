/**
 * The pure parts of the snapshot form (spec 7.6, decisions 7.5, 8.87): the
 * authored box, the request bodies of the four modes, the checks before a
 * submit and the edit page's patch.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  authoredBox,
  boxDimensionsOf,
  canonicalizeBoxAxesMm,
  dayToTimestamp,
  emptyFields,
  identityBody,
  isAuthoredBoxOnly,
  keptGeometry,
  metadataPatch,
  parseLocation,
  problemsOf,
  sanitizeDimensionInput,
  snapshotBody,
  validDimensions,
  type CheckInput,
  type IdentityFields,
} from '@/lib/snapshotForm'

const identity = (patch: Partial<IdentityFields> = {}): IdentityFields => ({
  tag: '', dataset: 'ds', parents: [], originalFunction: null, material: '', tradeName: '', origin: null, ...patch,
})

const check = (patch: Partial<CheckInput>): string[] =>
  problemsOf({
    mode: 'new', fields: emptyFields(), identity: identity(), dimensions: ['100', '50', '20'], sizeEntered: true,
    ...patch,
  }).map((p) => p.field)

test('L x W x H become the box axes: longest along x, a column stands', () => {
  assert.deepEqual(canonicalizeBoxAxesMm(50, 300, 20), { xMm: 300, yMm: 50, zMm: 20 })
  assert.deepEqual(canonicalizeBoxAxesMm(50, 300, 20, true), { xMm: 50, yMm: 20, zMm: 300 })
})

test('an authored box is one primary proxy with fit method authored and no scan data', () => {
  const geometry = authoredBox(100, 400, 25, false)
  assert.deepEqual(geometry.meshes, [])
  assert.deepEqual(geometry.point_clouds, [])
  assert.equal(geometry.proxies.length, 1)
  const proxy = geometry.proxies[0] as { primitive: string; role: string; params: { size: number[] }; fit: { method: string } }
  assert.equal(proxy.primitive, 'box')
  assert.equal(proxy.role, 'primary')
  assert.deepEqual(proxy.params.size, [400, 100, 25])
  assert.equal(proxy.fit.method, 'authored')
  assert.deepEqual(boxDimensionsOf(geometry as never), ['400', '100', '25'])
})

test('only a geometry of authored boxes is kept by a correction', () => {
  const authored = authoredBox(10, 20, 30, false)
  assert.ok(isAuthoredBoxOnly(authored as never))
  assert.deepEqual(keptGeometry(authored as never), authored)
  const scanned = { ...authored, meshes: [{ vertices: [], faces: [] }] }
  assert.ok(!isAuthoredBoxOnly(scanned as never))
  const fitted = { meshes: [], point_clouds: [], proxies: [{ primitive: 'box', fit: { method: 'obb' } }] }
  assert.ok(!isAuthoredBoxOnly(fitted as never))
  assert.ok(!isAuthoredBoxOnly(null))
})

test('dimension input: decimals while typing, commas read as points, positive numbers only', () => {
  assert.equal(sanitizeDimensionInput('12,5'), '12.5')
  assert.equal(sanitizeDimensionInput('12.5x'), '12.5')
  assert.deepEqual(validDimensions('10', '20,5', '3'), [10, 20.5, 3])
  assert.equal(validDimensions('10', '', '3'), null)
  assert.equal(validDimensions('10', '0', '3'), null)
})

test('locations: both empty is none, a pair is checked, a half or a wild value is wrong', () => {
  assert.equal(parseLocation('', ''), null)
  assert.deepEqual(parseLocation('49,8', '8.67'), { lat: 49.8, lon: 8.67 })
  assert.equal(parseLocation('49.8', ''), undefined)
  assert.equal(parseLocation('95', '8'), undefined)
  assert.equal(dayToTimestamp('2026-10-03'), '2026-10-03T00:00:00Z')
  assert.equal(dayToTimestamp('3.10.2026'), null)
})

test('a snapshot body: a correction inherits the date, a new state sends one when set', () => {
  const geometry = authoredBox(10, 20, 30, false)
  const fields = { ...emptyFields(), name: ' Lintel ', notes: ' ', effectiveOn: '2026-09-01', lat: '49.8', lon: '8.6' }
  const state = snapshotBody(fields, geometry, { inheritDate: false })
  assert.equal(state.name, 'Lintel')
  assert.equal(state.notes, null)
  assert.equal(state.effective_from, '2026-09-01T00:00:00Z')
  assert.equal(state.effective_from_precision, 'day')
  assert.deepEqual(state.location, { lat: 49.8, lon: 8.6 })
  const correction = snapshotBody(fields, geometry, { inheritDate: true })
  assert.ok(!('effective_from' in correction))
  const bare = snapshotBody(emptyFields(), geometry, { inheritDate: false })
  assert.ok(!('effective_from' in bare))
  assert.ok(!('location' in bare))
  assert.equal(bare.quantity, 1)
})

test('POST /identities: a new component states what it is, a cut leaves the rest to the parents', () => {
  const snapshot = snapshotBody(emptyFields(), authoredBox(10, 20, 30, false), { inheritDate: false })
  const created = identityBody(identity({
    tag: 'tag-id', originalFunction: 'IfcBeam', material: 'concrete', tradeName: ' X ',
  }), snapshot)
  assert.equal(created.id, 'tag-id')
  assert.equal(created.original_function, 'IfcBeam')
  assert.equal(created.material, 'concrete')
  assert.equal(created.trade_name, 'X')
  assert.ok(!('parent_identities' in created))

  const cut = identityBody(identity({ parents: ['p1', 'p2'] }), snapshot)
  assert.deepEqual(cut.parent_identities, ['p1', 'p2'])
  assert.ok(!('material' in cut) && !('trade_name' in cut) && !('original_function' in cut) && !('id' in cut))
  // parents that disagree: the merge states the material
  const merged = identityBody(identity({ parents: ['p1', 'p2'], material: 'steel' }), snapshot)
  assert.equal(merged.material, 'steel')
})

test('what blocks a submit, per mode', () => {
  assert.deepEqual(check({ mode: 'new' }), ['tag', 'original_function', 'material'])
  assert.deepEqual(
    check({ mode: 'new', identity: identity({ tag: 't', originalFunction: 'IfcBeam', material: 'm' }) }), [])
  assert.deepEqual(check({ mode: 'cut', identity: identity({ parents: [] }) }), ['parents'])
  assert.deepEqual(check({ mode: 'cut', identity: identity({ parents: ['p'] }) }), [])
  assert.deepEqual(check({ mode: 'cut', identity: identity({ parents: ['p'], dataset: '' }) }), ['dataset'])
  assert.deepEqual(check({ mode: 'state', dimensions: ['', '', ''] }), ['size'])
  assert.deepEqual(check({ mode: 'state' }), [])
  // a correction keeps its geometry unless a size is entered again
  assert.deepEqual(check({ mode: 'correct', dimensions: ['', '', ''], sizeEntered: false }), [])
  assert.deepEqual(check({ mode: 'correct', dimensions: ['', '', ''], sizeEntered: true }), ['size'])
  assert.deepEqual(check({ mode: 'state', fields: { ...emptyFields(), lat: '12' } }), ['location'])
  assert.deepEqual(check({ mode: 'state', fields: { ...emptyFields(), effectiveOn: 'tomorrow' } }), ['effective_on'])
})

test('a draw from a batch: no size needed, never more pieces than remain', () => {
  const draw = (quantity: number, remaining: number, sizeEntered = false) => check({
    mode: 'cut', identity: identity({ parents: ['batch'] }), fields: { ...emptyFields(), quantity },
    dimensions: ['', '', ''], sizeEntered, draw: { remaining },
  })
  assert.deepEqual(draw(3, 7), [])
  assert.deepEqual(draw(8, 7), ['quantity'])
  assert.deepEqual(draw(1, 0), ['quantity'])
  const said = (remaining: number) => problemsOf({
    mode: 'cut', identity: identity({ parents: ['batch'] }), fields: { ...emptyFields(), quantity: 5 },
    dimensions: ['', '', ''], sizeEntered: false, draw: { remaining },
  }).map((p) => p.message)
  assert.deepEqual(said(1), ['Only 1 piece remains in the batch.'])
  assert.deepEqual(said(2), ['Only 2 pieces remain in the batch.'])
  // a size of its own must be complete
  assert.deepEqual(draw(1, 7, true), ['size'])
  // without geometry the body leaves the key out, so the server copies the batch's proxy
  const body = snapshotBody({ ...emptyFields(), quantity: 3 }, undefined, { inheritDate: false })
  assert.ok(!('geometry' in body))
  assert.equal(body.quantity, 3)
})

test('the edit page patches only what changed', () => {
  const before = { name: 'A', notes: '', color: [1, 2, 3] as [number, number, number], lat: '', lon: '' }
  assert.deepEqual(metadataPatch(before, { ...before }), {})
  assert.deepEqual(metadataPatch(before, { ...before, name: 'B', notes: 'n' }), { name: 'B', notes: 'n' })
  assert.deepEqual(metadataPatch(before, { ...before, name: '' }), { name: null })
  assert.deepEqual(metadataPatch(before, { ...before, color: [9, 9, 9] }), { color: [9, 9, 9] })
  assert.deepEqual(metadataPatch(before, { ...before, lat: '1', lon: '2' }), { location: { lat: 1, lon: 2 } })
  assert.equal(metadataPatch(before, { ...before, lat: '1' }), undefined)
  const placed = { ...before, lat: '1', lon: '2' }
  assert.deepEqual(metadataPatch(placed, { ...placed, lat: '', lon: '' }), { location: null })
})
