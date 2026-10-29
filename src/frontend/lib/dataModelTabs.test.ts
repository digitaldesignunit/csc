/**
 * The tabs of the "Data Model" page (decision 8.181 c, amended): every anchor of
 * the page belongs to one tab, the folded ones to one fold, and an address
 * hash opens the right place.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { EXAMPLE_RECORDS } from './dataModelExamples'
import { ENTITY_SECTIONS, RULES, VOCAB_SECTIONS } from './dataModelText'
import {
  DEFAULT_TAB,
  EXAMPLE_OPEN_BY_DEFAULT,
  TABS,
  TAB_SECTIONS,
  anchorPlaces,
  parseHash,
  placeOf,
} from './dataModelTabs'

test('there are seven tabs, with the names the maintainer asked for', () => {
  assert.deepEqual(TABS.map((tab) => tab.label), [
    'Overview', 'Dataset', 'Identity', 'Versions', 'Evidence', 'Lists of values', 'Example',
  ])
  assert.equal(new Set(TABS.map((tab) => tab.id)).size, 7)
  assert.equal(DEFAULT_TAB, 'overview')
})

/** The ids the page sets, listed from the content (not from the tab map, which the test checks). */
function pageAnchors(): string[] {
  return [
    'overview', 'rules', ...RULES.map((rule) => rule.id),
    ...ENTITY_SECTIONS.flatMap((section) => [section.id, ...(section.tables ?? []).map((table) => table.id)]),
    'vocabularies', ...VOCAB_SECTIONS.map((vocab) => vocab.id),
    'example', ...EXAMPLE_RECORDS.map((record) => record.id),
  ]
}

test('every anchor of the page is on a tab, and the map has no anchor the page lacks', () => {
  const anchors = pageAnchors()
  assert.equal(new Set(anchors).size, anchors.length, 'an id is set twice')
  for (const id of anchors) assert.ok(placeOf(id), `"${id}" is on no tab`)
  assert.deepEqual([...anchorPlaces().keys()].sort(), [...anchors].sort())
})

test('every tab holds something and every tab id is itself an anchor of that tab', () => {
  for (const tab of TABS) {
    assert.equal(placeOf(tab.id)?.tab, tab.id, tab.id)
    const members = [...anchorPlaces().values()].filter((place) => place.tab === tab.id)
    assert.ok(members.length > 0, tab.id)
  }
})

test('every entity section is on exactly one tab, and its tables with it', () => {
  const listed = Object.values(TAB_SECTIONS).flat()
  assert.equal(new Set(listed).size, listed.length)
  assert.deepEqual([...listed].sort(), ENTITY_SECTIONS.map((section) => section.id).sort())
  for (const [tab, ids] of Object.entries(TAB_SECTIONS)) {
    for (const id of ids ?? []) {
      assert.equal(placeOf(id)?.tab, tab, id)
      const section = ENTITY_SECTIONS.find((entry) => entry.id === id)
      for (const table of section?.tables ?? []) assert.equal(placeOf(table.id)?.tab, tab, table.id)
    }
  }
})

test('a vocabulary is folded in "Lists of values", an example record in "Example"', () => {
  for (const vocab of VOCAB_SECTIONS) {
    assert.deepEqual(placeOf(vocab.id), { tab: 'vocabularies', fold: { group: 'lists', id: vocab.id } })
  }
  for (const record of EXAMPLE_RECORDS) {
    assert.deepEqual(placeOf(record.id), { tab: 'example', fold: { group: 'example', id: record.id } })
  }
  // nothing else is folded
  for (const [id, place] of anchorPlaces()) {
    if (place.fold) assert.ok(VOCAB_SECTIONS.some((v) => v.id === id) || EXAMPLE_RECORDS.some((r) => r.id === id), id)
  }
})

test('the records that start open are the dataset, the identity and the two versions; the evidence is folded', () => {
  assert.deepEqual(EXAMPLE_OPEN_BY_DEFAULT, ['example-dataset', 'example-identity', 'example-snapshot-v0', 'example-snapshot-v1'])
  for (const id of EXAMPLE_OPEN_BY_DEFAULT) assert.ok(placeOf(id)?.fold, id)
  const evidence = EXAMPLE_RECORDS.filter((r) => r.model === 'EvidenceView').map((r) => r.id)
  assert.equal(evidence.length, 7)
  for (const id of evidence) assert.ok(!EXAMPLE_OPEN_BY_DEFAULT.includes(id), id)
})

test('an empty or unknown hash is the Overview', () => {
  for (const hash of ['', '#', '#nonsense', '#%E0%A4%A', '#Evidence', '#/evidence']) {
    assert.deepEqual(parseHash(hash), { tab: 'overview', anchor: null }, hash)
  }
})

test('the hash of a tab opens the tab and scrolls nowhere', () => {
  for (const tab of TABS) assert.deepEqual(parseHash(`#${tab.id}`), { tab: tab.id, anchor: null }, tab.id)
})

test('the hash of a section, a table or a rule opens its tab and scrolls to it', () => {
  assert.deepEqual(parseHash('#origin'), { tab: 'identity', anchor: 'origin' })
  assert.deepEqual(parseHash('#evidence-verification'), { tab: 'evidence', anchor: 'evidence-verification' })
  assert.deepEqual(parseHash('#lifecycle'), { tab: 'evidence', anchor: 'lifecycle' })
  assert.deepEqual(parseHash('#actor'), { tab: 'evidence', anchor: 'actor' })
  assert.deepEqual(parseHash('#rule-time'), { tab: 'overview', anchor: 'rule-time' })
  assert.deepEqual(parseHash('#snapshot-fields'), { tab: 'snapshot', anchor: 'snapshot-fields' })
})

test('the hash of a vocabulary or an example record opens its tab and unfolds it', () => {
  assert.deepEqual(parseHash('#evidence-methods'), {
    tab: 'vocabularies', anchor: 'evidence-methods', fold: { group: 'lists', id: 'evidence-methods' },
  })
  assert.deepEqual(parseHash('#example-core-compression'), {
    tab: 'example', anchor: 'example-core-compression', fold: { group: 'example', id: 'example-core-compression' },
  })
})
