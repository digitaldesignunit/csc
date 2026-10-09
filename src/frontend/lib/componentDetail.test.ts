/**
 * The pure parts of the component page (plan P11 stage 1, 8.101, 8.102,
 * 8.115, 8.118): chips, banners, facts, the Actions menu per role, and the
 * History card's merge of the timeline and the lineage events.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  availableActions,
  bannersOf,
  circulationChip,
  conditionChip,
  factGroups,
  formatDay,
  lineageEvents,
  mergeHistory,
  statusChip,
  versionOffers,
  type ActionsInput,
  type HistoryEvent,
} from './componentDetail'

test('days are shown at day precision, never with seconds', () => {
  assert.equal(formatDay('2024-07-24T00:00:00Z', 'day'), '24.07.2024')
  assert.equal(formatDay('2024-07-24T00:00:00Z'), '24.07.2024')
  assert.equal(formatDay('2022-03-01T00:00:00Z', 'month'), '03.2022')
  assert.equal(formatDay('2022-03-01T00:00:00Z', 'year'), '2022')
  assert.equal(formatDay('2026-10-06T10:16:13Z', 'exact'), '06.10.2026')
  assert.equal(formatDay(null), '')
})

test('the circulation chip: in place, not in place, in circulation, the exit', () => {
  assert.equal(circulationChip({ origin: { kind: 'deinstallation', planned: true } }).label, 'In place')
  assert.equal(circulationChip({ origin: { kind: 'deinstallation', planned: false } }).label, 'Not in place')
  assert.equal(circulationChip({ origin: { kind: 'demolition', planned: false } }).label, 'Not in place')
  assert.equal(circulationChip({ origin: { kind: 'offcut' } }).label, 'In circulation')
  assert.equal(circulationChip({}).label, 'In circulation')
  const exited = circulationChip({
    origin: { kind: 'deinstallation', planned: true },
    exit: { kind: 'installed', at: '2025-05-02T00:00:00Z' },
  })
  assert.equal(exited.label, 'Installed')
  assert.match(exited.title ?? '', /02\.05\.2025/)
})

test('the status and condition chips', () => {
  assert.deepEqual(statusChip({ status: 'published' }), { label: 'Published', tone: 'good' })
  assert.equal(statusChip({ status: 'pending' }).label, 'Pending')
  assert.equal(statusChip({ status: 'rejected' }).tone, 'bad')
  assert.equal(conditionChip(null).label, 'Condition not assessed')
  assert.equal(conditionChip(3).label, 'Condition 3 --- Good')
  assert.equal(conditionChip(1).tone, 'bad')
})

test('a banner only when it applies, one sentence each', () => {
  assert.deepEqual(bannersOf({ identity: { is_public: true }, signedIn: false, geometryFailed: false }), [])
  // not public is for someone who can see it: a member
  assert.deepEqual(bannersOf({ identity: { is_public: false }, signedIn: false, geometryFailed: false }), [])
  const notPublic = bannersOf({
    identity: { is_public: false, dataset: 'dbu_zirkus' }, signedIn: true, geometryFailed: false,
  })
  assert.equal(notPublic.length, 1)
  assert.match(notPublic[0].text, /^Not public: only members of dbu_zirkus/)
  const out = bannersOf({
    identity: { exit: { kind: 'split' }, withdrawn: { at: '2026-01-05T00:00:00Z', reason: 'duplicate' } },
    signedIn: true, geometryFailed: true,
  })
  assert.deepEqual(out.map((b) => b.id), ['withdrawn', 'exited', 'geometry'])
  assert.match(out[0].text, /^Withdrawn on 05\.01\.2026: duplicate\./)
  // a reason that ends with a full stop does not double it
  const stopped = bannersOf({
    identity: { withdrawn: { at: '2026-01-05T00:00:00Z', reason: 'Recorded by mistake. ' } },
    signedIn: true, geometryFailed: false,
  })
  assert.match(stopped[0].text, /^Withdrawn on 05\.01\.2026: Recorded by mistake\. Only members/)
  // the exit kind is the chip's job, not the banner's
  assert.doesNotMatch(out[1].text, /Split/)
})

const IDENTITY = { original_function: 'IfcBeam', material: 'concrete', material_class: '17 01 01', dataset: 'dbu_zirkus' }
const SNAPSHOT = {
  shape_class: 'linear', bbx: [4457.2, 644, 601.4], complexity: 1, color: [168, 168, 168],
  effective_from: '2024-07-24T00:00:00Z', effective_from_precision: 'day', capture: { method: 'photogrammetry' },
}

test('the facts in two groups, without the recorder or timestamps', () => {
  const groups = factGroups({ identity: IDENTITY, snapshot: SNAPSHOT, functionLabel: 'Beam', shapeClassLabel: 'Linear' })
  assert.deepEqual(groups.component.map((f) => f.label), ['Original function', 'Material', 'Waste class', 'Dataset'])
  // the material by its id until the materials list names it
  assert.equal(groups.component.find((f) => f.label === 'Material')?.value, 'concrete')
  assert.deepEqual(groups.state.map((f) => f.label),
    ['Shape class', 'Size', 'Complexity', 'Colour', 'State since', 'Capture'])
  assert.equal(groups.state.find((f) => f.label === 'Size')?.value, '4457 x 644 x 601 mm')
  assert.equal(groups.state.find((f) => f.label === 'State since')?.value, '24.07.2024')
  const all = [...groups.component, ...groups.state].map((f) => f.label.toLowerCase())
  assert.ok(!all.some((label) => /added|created|modified|snapshot id/.test(label)))
})

test('a batch has its line, a trade name joins the material label, notes are a state fact', () => {
  const groups = factGroups({
    identity: { ...IDENTITY, material: 'autoclaved_aerated_concrete', trade_name: 'ExampleBlock', remaining: 354 },
    snapshot: { ...SNAPSHOT, quantity: 356, fragment: true, notes: ' catalogue note ' },
    functionLabel: 'Wall', shapeClassLabel: 'Planar', materialLabel: 'Autoclaved aerated concrete',
  })
  assert.equal(groups.component.find((f) => f.label === 'Material')?.value, 'Autoclaved aerated concrete (ExampleBlock)')
  assert.equal(groups.component.find((f) => f.label === 'Batch')?.value, '356 recorded, 2 drawn, 354 remaining')
  assert.ok(groups.component.find((f) => f.label === 'Fragment'))
  assert.equal(groups.state.find((f) => f.label === 'Notes')?.value, 'catalogue note')
  // a plain quantity without a batch line
  const plain = factGroups({
    identity: IDENTITY, snapshot: { ...SNAPSHOT, quantity: 3 }, functionLabel: 'Beam', shapeClassLabel: null,
  })
  assert.equal(plain.component.find((f) => f.label === 'Quantity')?.value, '3')
  assert.equal(plain.state.some((f) => f.label === 'Shape class'), false)
})

const VERSIONS = [
  { _id: 'a', version: 0, status: 'published', is_current: false, superseded_by: 'b' },
  { _id: 'b', version: 1, status: 'published', is_current: true },
]

function input(over: Partial<ActionsInput> = {}): ActionsInput {
  return {
    identity: { current_snapshot_id: 'b', origin: { kind: 'deinstallation', planned: false } },
    versions: VERSIONS, signedIn: true, isModerator: false, isContributor: false,
    hasGeometryFiles: true, isCero: true, ...over,
  }
}

test('a visitor gets the passport editions and nothing else', () => {
  assert.deepEqual(availableActions(input({ signedIn: false })), { record: ['pdf', 'cero'], moderate: [] })
  assert.deepEqual(availableActions(input({ signedIn: false, isCero: false })), { record: ['pdf'], moderate: [] })
})

test('a signed-in user without a role records nothing and moderates nothing', () => {
  assert.deepEqual(availableActions(input()), { record: ['pdf', 'cero', 'geometry', 'locate'], moderate: [] })
})

test('a contributor cuts, records a state and corrects a live version', () => {
  const got = availableActions(input({ isContributor: true }))
  assert.deepEqual(got.record, ['pdf', 'cero', 'geometry', 'locate', 'cut', 'state'])
  assert.deepEqual(got.moderate, ['correct'])
})

test('a batch is drawn from while pieces remain, not cut', () => {
  const batch = (remaining: number) => availableActions(input({
    isContributor: true,
    identity: { current_snapshot_id: 'b', remaining, origin: { kind: 'deinstallation', planned: true } },
  }))
  assert.ok(batch(5).record.includes('draw') && !batch(5).record.includes('cut'))
  assert.ok(!batch(0).record.includes('draw') && !batch(0).record.includes('cut'))
})

test('a moderator gets the moderate group by what the piece allows', () => {
  const open = input({
    isModerator: true, isContributor: true,
    identity: { current_snapshot_id: 'b', origin: { kind: 'deinstallation', planned: false }, can_undo_deinstall: true },
  })
  const got = availableActions(open)
  assert.deepEqual(got.moderate, ['correct', 'withdraw-version', 'exit', 'undo-deinstall', 'withdraw-component'])
  assert.ok(got.record.includes('edit'))
  // the undo is offered only while the backend says the deinstall act can be taken back (8.115 a)
  for (const flag of [false, undefined, null]) {
    const closed = availableActions(input({
      isModerator: true,
      identity: { current_snapshot_id: 'b', origin: { kind: 'deinstallation', planned: false }, can_undo_deinstall: flag },
    }))
    assert.ok(!closed.moderate.includes('undo-deinstall'), String(flag))
  }
  // an in-place piece: record the deinstallation; a live older version can be made current
  const inPlace = availableActions(input({
    isModerator: true,
    identity: { current_snapshot_id: 'b', origin: { kind: 'deinstallation', planned: true } },
    versions: [
      { _id: 'a', version: 0, status: 'published', is_current: false },
      { _id: 'b', version: 1, status: 'published', is_current: true },
    ],
  }))
  assert.ok(inPlace.moderate.includes('deinstall') && inPlace.moderate.includes('promote'))
  assert.ok(!inPlace.moderate.includes('undo-deinstall'))
})

test('exits: undo what was recorded, re-enter what can come back, explain what the pieces set', () => {
  const exited = (exit: { kind: string; recorded_by_user_id?: string | null }) => availableActions(input({
    isModerator: true, identity: { current_snapshot_id: 'b', exit, origin: { kind: 'offcut' } },
  })).moderate
  assert.deepEqual(exited({ kind: 'installed', recorded_by_user_id: 'u1' }),
    ['withdraw-version', 'undo-exit', 'reenter', 'withdraw-component'])
  assert.ok(exited({ kind: 'split' }).includes('exit-set-by-pieces'))
  assert.ok(!exited({ kind: 'recycled', recorded_by_user_id: 'u1' }).includes('reenter'))
})

test('a withdrawn piece can only be reinstated', () => {
  const got = availableActions(input({
    isModerator: true, isContributor: true,
    identity: { current_snapshot_id: 'b', withdrawn: { at: '2026-01-01T00:00:00Z' } },
  }))
  assert.deepEqual(got.moderate.filter((k) => k.includes('component')), ['reinstate-component'])
  assert.ok(!got.record.includes('state') && !got.record.includes('cut'))
})

test('unfinished versions are managed by their author or a moderator', () => {
  const versions = [...VERSIONS, { _id: 'c', version: 2, status: 'pending', added_by_user_id: 'u1' }]
  assert.ok(availableActions(input({ versions, meId: 'u1' })).moderate.includes('manage-versions'))
  assert.ok(!availableActions(input({ versions, meId: 'u2' })).moderate.includes('manage-versions'))
  assert.ok(availableActions(input({ versions, meId: 'u2', isModerator: true })).moderate.includes('manage-versions'))
})

test('a version dialog lists only the versions the caller can act on', () => {
  const live = { _id: 'a', version: 0, status: 'published', is_current: false }
  const current = { _id: 'b', version: 1, status: 'published', is_current: true }
  const corrected = { _id: 'x', version: 2, status: 'published', superseded_by: 'b' }
  const mine = { _id: 'c', version: 3, status: 'draft', added_by_user_id: 'u1' }
  const theirs = { _id: 'd', version: 4, status: 'pending', added_by_user_id: 'u2' }
  const withdrawn = { _id: 'e', version: 5, status: 'withdrawn', added_by_user_id: 'u2' }
  const contributor = { isModerator: false, isContributor: true, meId: 'u1' }
  const moderator = { isModerator: true, isContributor: true, meId: 'u9' }
  const rows = [live, current, corrected, mine, theirs, withdrawn]
  const ids = (mode: Parameters<typeof versionOffers>[0], caller: typeof contributor) =>
    rows.filter((row) => versionOffers(mode, row, caller)).map((row) => row._id)
  assert.deepEqual(ids('correct', contributor), ['a', 'b'])               // live versions only
  assert.deepEqual(ids('promote', contributor), [])                      // a moderator's act
  assert.deepEqual(ids('promote', moderator), ['a'])                     // not the current one
  assert.deepEqual(ids('withdraw-version', moderator), ['a', 'b', 'x'])
  assert.deepEqual(ids('withdraw-version', contributor), [])
  assert.deepEqual(ids('manage-versions', contributor), ['c'])           // only their own draft
  assert.deepEqual(ids('manage-versions', moderator), ['c', 'd', 'e'])
  // a caller with nothing to act on gets no entry at all
  const reader = { isModerator: false, isContributor: false, meId: 'u7' }
  const got = availableActions(input({ versions: rows, ...reader }))
  assert.deepEqual(got.moderate, [])
})

test('a cut starts from a piece in circulation or one already cut (8.34)', () => {
  const cut = (exit?: { kind: string; recorded_by_user_id?: string | null }) =>
    availableActions(input({
      isContributor: true, identity: { current_snapshot_id: 'b', exit, origin: { kind: 'offcut' } },
    })).record.includes('cut')
  assert.equal(cut(), true)
  assert.equal(cut({ kind: 'split' }), true)                  // cut again
  assert.equal(cut({ kind: 'merged' }), true)
  for (const kind of ['installed', 'returned', 'lost']) assert.equal(cut({ kind, recorded_by_user_id: 'u1' }), false, kind)
  for (const kind of ['recycled', 'disposed']) assert.equal(cut({ kind, recorded_by_user_id: 'u1' }), false, kind)
  // a batch is drawn from by the same rule
  const draw = (exit?: { kind: string }) => availableActions(input({
    isContributor: true, identity: { current_snapshot_id: 'b', remaining: 3, exit, origin: { kind: 'offcut' } },
  })).record.includes('draw')
  assert.equal(draw(), true)
  assert.equal(draw({ kind: 'installed' }), false)
})

test('Edit details: a moderator, or the creator while nothing is published (8.9)', () => {
  const edit = (over: Partial<ActionsInput>) => availableActions(input(over)).record.includes('edit')
  const unpublished = { created_by_user_id: 'u1' }
  assert.equal(edit({ isModerator: true }), true)
  assert.equal(edit({ identity: unpublished, meId: 'u1' }), true)           // the creator, unpublished
  assert.equal(edit({ identity: unpublished, meId: 'u2' }), false)          // someone else
  assert.equal(edit({ identity: { ...unpublished, current_snapshot_id: 'b' }, meId: 'u1' }), false)   // published
  assert.equal(edit({ isContributor: true, meId: 'u3' }), false)            // a contributor is not enough
  assert.equal(edit({ isModerator: true, identity: { withdrawn: { at: '2026-01-01T00:00:00Z' } } }), false)
})

const EVENTS: HistoryEvent[] = [
  { kind: 'origin', at: '1972-01-01T00:00:00Z', section: 'before_cataloguing' },
  { kind: 'evidence', at: '1974-01-01T00:00:00Z', section: 'before_cataloguing' },
  { kind: 'snapshot', at: '2025-06-15T00:00:00Z', section: 'history', version: 0 },
  { kind: 'evidence', at: '2025-06-16T00:00:00Z', section: 'history' },
  { kind: 'snapshot', at: '2026-08-01T00:00:00Z', section: 'history', version: 1 },
  { kind: 'exit', at: '2026-09-01T00:00:00Z', section: 'history' },
]
const ALL = { lineage: true, states: true, evidence: true }

test('lineage events: cut from the parents, cut into the children of one day', () => {
  const events = lineageEvents({
    startedAt: '2025-06-15T00:00:00Z',
    parents: [{ id: 'p', catalogNumber: 700 }],
    children: [
      { id: 'c1', catalogNumber: 812, at: '2026-05-17T10:00:00Z' },
      { id: 'c2', catalogNumber: 813, at: '2026-05-17T11:00:00Z' },
      { id: 'c3', catalogNumber: 814, at: '2026-06-01T09:00:00Z' },
    ],
  })
  assert.deepEqual(events.map((e) => [e.direction, e.related.map((r) => r.catalogNumber)]),
    [['from', [700]], ['into', [812, 813]], ['into', [814]]])
  assert.deepEqual(lineageEvents({ startedAt: null, parents: [], children: [] }), [])
})

test('the history puts lineage events in date order and the layers filter', () => {
  const lineage = lineageEvents({
    startedAt: null, parents: [], children: [{ id: 'c1', catalogNumber: 812, at: '2026-05-17T10:00:00Z' }],
  })
  const merged = mergeHistory(EVENTS, lineage, ALL)
  assert.deepEqual(merged.map((s) => s.id), ['before_cataloguing', 'history'])
  assert.deepEqual(merged[1].rows.map((e) => e.kind), ['snapshot', 'evidence', 'lineage', 'snapshot', 'exit'])

  const noEvidence = mergeHistory(EVENTS, lineage, { ...ALL, evidence: false })
  assert.ok(noEvidence.every((s) => s.rows.every((e) => e.kind !== 'evidence')))
  assert.deepEqual(noEvidence.map((s) => s.id), ['before_cataloguing', 'history'])   // the origin stays

  const noStates = mergeHistory(EVENTS, lineage, { ...ALL, states: false })
  assert.ok(noStates.every((s) => s.rows.every((e) => e.kind !== 'snapshot')))
  const noLineage = mergeHistory(EVENTS, lineage, { ...ALL, lineage: false })
  assert.ok(noLineage.every((s) => s.rows.every((e) => e.kind !== 'lineage')))
  // the origin, the deinstallation and the exit belong to no layer
  const none = mergeHistory(EVENTS, lineage, { lineage: false, states: false, evidence: false })
  assert.deepEqual(none.flatMap((s) => s.rows.map((e) => e.kind)), ['origin', 'exit'])
})

test('plain record changes are not listed: they stay in the change history', () => {
  const withChanges: HistoryEvent[] = [
    ...EVENTS,
    { kind: 'metadata_changed', at: '2026-08-15T00:00:00Z', section: 'history', paths: ['origin'] },
    { kind: 'metadata_changed', at: '2026-09-15T00:00:00Z', section: 'history', paths: ['current_snapshot_id'] },
  ]
  const merged = mergeHistory(withChanges, [], ALL)
  assert.ok(merged.every((s) => s.rows.every((e) => e.kind !== 'metadata_changed')))
  assert.deepEqual(merged[1].rows.map((e) => e.kind), ['snapshot', 'evidence', 'snapshot', 'exit'])
})

test('an undated lineage event sits at the start of its section', () => {
  const lineage = lineageEvents({ startedAt: null, parents: [{ id: 'p', catalogNumber: 1 }], children: [] })
  const merged = mergeHistory(EVENTS, lineage, ALL)
  assert.equal(merged[1].rows[0].kind, 'lineage')
})
