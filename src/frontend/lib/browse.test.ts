import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  activeFilters,
  browseUrl,
  cardLine,
  EVIDENCE_METHOD_OPTIONS,
  circulationGroup,
  filterChipLabel,
  filterValue,
  isEvidenceMethod,
  parseCirculation,
  parsePickedColumns,
  piecesNote,
  rowName,
  rowStatus,
  searchTarget,
  sizeLabel,
  withParams,
  withoutFilters,
} from './browse'

const ID = '2e6f6e3c-165f-4ca2-9be9-884e6e8e84f5'

test('the circulation switch has three positions and keeps the backend values', () => {
  assert.equal(parseCirculation(undefined), 'active')
  assert.equal(parseCirculation('bogus'), 'active')
  for (const v of ['active', 'in_place', 'deinstalled', 'exited', 'all'] as const) {
    assert.equal(parseCirculation(v), v)
  }
  assert.equal(circulationGroup('active'), 'in')
  assert.equal(circulationGroup('in_place'), 'in')
  assert.equal(circulationGroup('deinstalled'), 'in')
  assert.equal(circulationGroup('exited'), 'out')
  assert.equal(circulationGroup('all'), 'all')
})

test('active filters are the known keys with a value, in a fixed order', () => {
  const params = new URLSearchParams('page=3&q=beam&material=concrete&original_function=IfcBeam&size=20&fragment=true&dataset=')
  assert.deepEqual(activeFilters(params), [
    { key: 'original_function', value: 'IfcBeam' },
    { key: 'material', value: 'concrete' },
    { key: 'fragment', value: 'true' },
  ])
})

test('a filter chip says what it filters', () => {
  assert.equal(filterChipLabel('original_function', 'IfcBeam'), 'Function: Beam')
  assert.equal(filterChipLabel('material', 'concrete'), 'Material: concrete')
  assert.equal(filterChipLabel('material', 'concrete', { material: () => 'Concrete' }), 'Material: Concrete')
  assert.equal(filterChipLabel('dataset', 'later_dataset'), 'Dataset: later_dataset')
  assert.equal(filterChipLabel('fragment', 'true'), 'Fragments only')
  assert.equal(filterChipLabel('fragment', 'false'), 'No fragments')
  assert.equal(filterChipLabel('bbx_min_x', '100'), 'Size X min: 100')
  assert.equal(filterChipLabel('bbx_max_z', '900'), 'Size Z max: 900')
})

test('a change of the list goes back to page 1, the rest stays', () => {
  const params = new URLSearchParams('page=4&material=concrete&circulation=exited&q=beam')
  const next = withParams(params, { dataset: 'a', material: null })
  assert.equal(next.get('page'), null)
  assert.equal(next.get('dataset'), 'a')
  assert.equal(next.get('material'), null)
  assert.equal(next.get('circulation'), 'exited')
  assert.equal(next.get('q'), 'beam')
  assert.equal(withParams(params, { page: '5' }, true).get('page'), '5')
  assert.equal(params.get('material'), 'concrete')   // a copy
})

test('clearing the filters keeps the circulation, the search and the sort', () => {
  const params = new URLSearchParams('page=2&material=concrete&dataset=a&circulation=all&q=x&sortkey=name&bbx_min_x=3')
  const next = withoutFilters(params)
  assert.equal(next.toString(), 'circulation=all&q=x&sortkey=name')
})

test('the search opens a piece by a complete id or a link, else it is the list search', () => {
  assert.deepEqual(searchTarget('  '), { kind: 'none' })
  assert.deepEqual(searchTarget(ID), { kind: 'id', id: ID })
  assert.deepEqual(searchTarget(ID.toUpperCase()), { kind: 'id', id: ID })
  assert.deepEqual(searchTarget(`https://csc.example/components/${ID}`), { kind: 'id', id: ID })
  assert.deepEqual(searchTarget('beam 07'), { kind: 'q', q: 'beam 07' })
  assert.deepEqual(searchTarget('#12'), { kind: 'q', q: '#12' })
  assert.deepEqual(searchTarget(ID.slice(0, 8)), { kind: 'q', q: ID.slice(0, 8) })
})

test('the size is millimetres, whole, and empty without a box', () => {
  assert.equal(sizeLabel([4457.2, 643.9, 601]), '4457 x 644 x 601')
  assert.equal(sizeLabel(null), '')
  assert.equal(sizeLabel([0, 0, 0]), '')
  assert.equal(sizeLabel([1, 2]), '')
})

test('the card line is function, material and size', () => {
  assert.equal(
    cardLine({ original_function: 'IfcBeam', material: 'concrete', bbx: [4457, 644, 601] }, 'Concrete'),
    'Beam / Concrete / 4457 x 644 x 601 mm',
  )
  assert.equal(cardLine({ original_function: 'IfcBeam', material: 'concrete', bbx: null }), 'Beam / concrete')
  assert.equal(cardLine({}), '')
})

test('a batch says how many pieces it holds', () => {
  assert.equal(piecesNote({ quantity: 356 }), '356 elements')
  assert.equal(piecesNote({ quantity: 1 }), '')
  assert.equal(piecesNote({}), '')
})

test('the status is one chip: exit, reserved, in place, else available', () => {
  assert.equal(rowStatus({ exit: { kind: 'installed' } }).label, 'Installed')
  assert.equal(rowStatus({ is_reserved: true }).label, 'Reserved')
  assert.equal(rowStatus({ exit: { kind: 'recycled' }, is_reserved: true }).label, 'Recycled')
  assert.equal(rowStatus({ origin: { kind: 'deinstallation', planned: true } }).label, 'In place')
  assert.equal(rowStatus({ origin: { kind: 'deinstallation', planned: false } }).label, 'Available')
  assert.equal(rowStatus({}).label, 'Available')
})

test('a row without a name is called by its number', () => {
  assert.equal(rowName({ name: ' Beam 07 ', catalog_number: 7 }), 'Beam 07')
  assert.equal(rowName({ name: '', catalog_number: 7 }), 'Component #7')
  assert.equal(rowName({}), 'Unnamed component')
})

test('the stored column picks keep only known optional columns', () => {
  assert.deepEqual(parsePickedColumns(null), [])
  assert.deepEqual(parsePickedColumns('not json'), [])
  assert.deepEqual(parsePickedColumns('{"a":1}'), [])
  assert.deepEqual(parsePickedColumns('["color","bogus","created",3]'), ['color', 'created'])
})

test('the Browse link of a dataset or a material carries the filter the bar reads', () => {
  assert.equal(browseUrl('dataset', 'dbu_zirkus'), '/components?dataset=dbu_zirkus')
  assert.equal(browseUrl('material', 'cast_iron'), '/components?material=cast_iron')
  assert.equal(browseUrl('material', 'a b/c'), '/components?material=a%20b%2Fc')
  assert.deepEqual(activeFilters(new URL('http://x' + browseUrl('dataset', 'd1')).searchParams), [{ key: 'dataset', value: 'd1' }])
})

test('the evidence method filter offers the methods with their labels and is a chip', () => {
  assert.deepEqual(EVIDENCE_METHOD_OPTIONS.map((o) => o.value).sort(), [
    'archival_document', 'core_compression', 'era_heuristic', 'manufacturer_datasheet',
    'rebound_hammer', 'reinforcement_layout', 'visual_inspection',
  ])
  assert.equal(EVIDENCE_METHOD_OPTIONS.find((o) => o.value === 'reinforcement_layout')?.label, 'Reinforcement layout')
  assert.equal(filterChipLabel('evidence_method', 'rebound_hammer'), 'Evidence: Rebound hammer')
  const params = new URLSearchParams('page=2&evidence_method=reinforcement_layout&material=concrete')
  assert.deepEqual(activeFilters(params), [
    { key: 'material', value: 'concrete' },
    { key: 'evidence_method', value: 'reinforcement_layout' },
  ])
})

test('an unknown evidence method in the URL is left out, the backend would answer 422', () => {
  assert.equal(isEvidenceMethod('rebound_hammer'), true)
  assert.equal(isEvidenceMethod('bogus'), false)
  assert.equal(isEvidenceMethod('constructor'), false)
  assert.equal(isEvidenceMethod(''), false)
  assert.equal(filterValue(new URLSearchParams('evidence_method=bogus'), 'evidence_method'), null)
  assert.equal(filterValue(new URLSearchParams('evidence_method=rebound_hammer'), 'evidence_method'), 'rebound_hammer')
  assert.equal(filterValue(new URLSearchParams('material=anything'), 'material'), 'anything')
  assert.deepEqual(activeFilters(new URLSearchParams('evidence_method=bogus')), [])
})

test('the evidence method is set, kept with the other filters and cleared with them', () => {
  const set = withParams(new URLSearchParams('page=3&material=concrete'), { evidence_method: 'reinforcement_layout' })
  assert.equal(set.toString(), 'material=concrete&evidence_method=reinforcement_layout')    // page 1
  const cleared = withParams(set, { evidence_method: null })
  assert.equal(cleared.toString(), 'material=concrete')
  assert.equal(withoutFilters(set).toString(), '')
})
