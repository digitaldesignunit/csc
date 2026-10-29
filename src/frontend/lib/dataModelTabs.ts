/**
 * The tabs of the "Data Model" page (decision 8.181 c, amended): seven tabs, the
 * lists of values and the example records folded inside theirs. Every anchor of
 * the page belongs to one tab, and to one folded section where it is a
 * vocabulary or an example record, so that `/reference#evidence-methods` opens
 * the tab "Lists of values", unfolds the evidence methods and scrolls there.
 */
import { EXAMPLE_RECORDS } from '@/lib/dataModelExamples'
import { ENTITY_SECTIONS, OVERVIEW, RULES, VOCAB_SECTIONS } from '@/lib/dataModelText'

export const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'dataset', label: 'Dataset' },
  { id: 'identity', label: 'Identity' },
  { id: 'snapshot', label: 'Versions' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'vocabularies', label: 'Lists of values' },
  { id: 'example', label: 'Example' },
] as const

export type TabId = (typeof TABS)[number]['id']
export const DEFAULT_TAB: TabId = 'overview'

/** The two groups of folded sections. */
export type FoldGroup = 'lists' | 'example'

/** The entity sections of each tab, in order (the overview and the two folded tabs are built apart). */
export const TAB_SECTIONS: Partial<Record<TabId, string[]>> = {
  dataset: ['dataset'],
  identity: ['identity', 'origin-exit'],
  snapshot: ['snapshot'],
  evidence: ['evidence', 'lifecycle', 'actor'],
}

/** The example records that start unfolded: the dataset, the identity and the two versions. */
export const EXAMPLE_OPEN_BY_DEFAULT = ['example-dataset', 'example-identity', 'example-snapshot-v0', 'example-snapshot-v1']

export type AnchorPlace = { tab: TabId; fold?: { group: FoldGroup; id: string } }

function buildAnchors(): Map<string, AnchorPlace> {
  const map = new Map<string, AnchorPlace>()
  const put = (id: string, place: AnchorPlace) => {
    if (map.has(id)) throw new Error(`the anchor "${id}" is on two tabs`)
    map.set(id, place)
  }
  for (const tab of TABS) put(tab.id, { tab: tab.id })
  // the overview section has the id of its tab
  if (OVERVIEW.id !== 'overview') put(OVERVIEW.id, { tab: 'overview' })
  put('rules', { tab: 'overview' })
  for (const rule of RULES) put(rule.id, { tab: 'overview' })
  const sectionTab = new Map<string, TabId>()
  for (const [tab, ids] of Object.entries(TAB_SECTIONS) as [TabId, string[]][]) {
    for (const id of ids) sectionTab.set(id, tab)
  }
  for (const section of ENTITY_SECTIONS) {
    const tab = sectionTab.get(section.id)
    if (!tab) throw new Error(`the section "${section.id}" is on no tab`)
    // the first section of a tab is the tab itself, already in the map
    if (!map.has(section.id)) put(section.id, { tab })
    for (const table of section.tables ?? []) put(table.id, { tab })
  }
  for (const vocab of VOCAB_SECTIONS) put(vocab.id, { tab: 'vocabularies', fold: { group: 'lists', id: vocab.id } })
  for (const record of EXAMPLE_RECORDS) put(record.id, { tab: 'example', fold: { group: 'example', id: record.id } })
  return map
}

const ANCHORS = buildAnchors()

/** Every anchor with its place. */
export function anchorPlaces(): ReadonlyMap<string, AnchorPlace> {
  return ANCHORS
}

/** The place of an anchor, or null when the page has no such anchor. */
export function placeOf(anchor: string): AnchorPlace | null {
  return ANCHORS.get(anchor) ?? null
}

/** What an address hash asks for: the tab to show and the anchor to scroll to (none for the tab itself). */
export function parseHash(hash: string): { tab: TabId; anchor: string | null; fold?: AnchorPlace['fold'] } {
  let raw = hash.replace(/^#/, '')
  try {
    raw = decodeURIComponent(raw)
  } catch {
    // a malformed escape is no anchor
  }
  const place = raw ? placeOf(raw) : null
  if (!place) return { tab: DEFAULT_TAB, anchor: null }
  const isTab = TABS.some((tab) => tab.id === raw)
  return place.fold
    ? { tab: place.tab, anchor: isTab ? null : raw, fold: place.fold }
    : { tab: place.tab, anchor: isTab ? null : raw }
}
