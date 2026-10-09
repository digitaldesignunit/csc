import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  firstSentence,
  groupBySubcategory,
  noOutputsText,
  paragraphsOf,
  screenshotFor,
  xmlNameOf,
  searchComponents,
  subcategoryTitle,
  visibleComponents,
  type RefComponent,
} from './ghReference'

const C = (name: string, subcategory: string, over: Partial<RefComponent> = {}): RefComponent => ({
  file: `DDU_CSC_${name}.py`, name, nickname: name, category: 'DDU_CSC', subcategory,
  description: `${name} does a thing. More.`, version: '1', inputs: [], outputs: [], ...over,
})

const ALL = [
  C('Update', '0 Development'),
  C('Session', '1 Authentication'),
  C('FetchSnapshot', '2 Catalog Interface'),
  C('AddEvidence', '2 Catalog Interface', { inputs: [{ name: 'Dataset', description: 'The dataset slug' }] }),
  C('ComputeFrame', '10 Geometry'),
]

test('the maintainer tools are not in the reference, CSC_Update is', () => {
  const all = [...ALL, C('CreateReleaseFiles', '0 Development')]
  assert.deepEqual(visibleComponents(all).map((c) => c.name), ['Update', 'Session', 'FetchSnapshot', 'AddEvidence', 'ComputeFrame'])
})

test('a screenshot is the exact file csc_<name>, any known extension, else none', () => {
  const files = ['csc_session.jpg', 'csc_fetchsnapshot.PNG', 'csc_addcomponent.jpg', 'notes.txt']
  assert.equal(screenshotFor({ name: 'Session' }, files), 'csc_session.jpg')
  assert.equal(screenshotFor({ name: 'FetchSnapshot' }, files), 'csc_fetchsnapshot.PNG')
  // a renamed component does not take the old screenshot
  assert.equal(screenshotFor({ name: 'AddComponentIdentity' }, files), null)
  assert.equal(screenshotFor({ name: 'Session' }, []), null)
})

test('the XML name is the source file, a description splits into paragraphs', () => {
  assert.equal(xmlNameOf({ file: 'DDU_CSC_Update.py' }), 'DDU_CSC_Update')
  assert.deepEqual(paragraphsOf('One.'+ String.fromCharCode(10, 10) + ' Two. ' + String.fromCharCode(10) + 'Three.'), ['One.', 'Two.', 'Three.'])
  assert.deepEqual(paragraphsOf(''), [])
})

test('the subcategory title drops the sorting number', () => {
  assert.equal(subcategoryTitle('2 Catalog Interface'), 'Catalog Interface')
  assert.equal(subcategoryTitle('10 Geometry'), 'Geometry')
  assert.equal(subcategoryTitle(''), 'Other')
})

test('groups go by the number (10 after 2), components by name', () => {
  const groups = groupBySubcategory(visibleComponents(ALL))
  assert.deepEqual(groups.map((g) => g.title), ['Development', 'Authentication', 'Catalog Interface', 'Geometry'])
  assert.deepEqual(groups[2].components.map((c) => c.name), ['AddEvidence', 'FetchSnapshot'])
  // the key keeps the number, it is the heading of a group
  assert.deepEqual(groups.map((g) => g.key), ['0 Development', '1 Authentication', '2 Catalog Interface', '10 Geometry'])
})

test('the search looks at names, descriptions and ports', () => {
  assert.deepEqual(searchComponents(ALL, 'evidence').map((c) => c.name), ['AddEvidence'])
  assert.deepEqual(searchComponents(ALL, 'dataset slug').map((c) => c.name), ['AddEvidence'])
  assert.equal(searchComponents(ALL, '').length, ALL.length)
  assert.deepEqual(searchComponents(ALL, 'zzz'), [])
})

test('the first sentence ends at the first full stop', () => {
  assert.equal(firstSentence('Lists things. Second one.'), 'Lists things.')
  assert.equal(firstSentence('No stop here'), 'No stop here')
  assert.equal(firstSentence('Ends with stop.'), 'Ends with stop.')
})

test('"None" only when OUTPUTS is declared and empty, else "not declared"', () => {
  assert.equal(noOutputsText({ outputs: [], outputs_declared: true }), 'None')
  assert.equal(noOutputsText({ outputs: [], outputs_declared: false }), 'Outputs not declared in this release')
  // an older reference without the field is not a declaration either
  assert.equal(noOutputsText({ outputs: [] }), 'Outputs not declared in this release')
})
