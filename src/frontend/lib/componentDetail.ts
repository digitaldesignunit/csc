/**
 * The pure parts of the component page (plan P11 stage 1, decisions 8.101,
 * 8.102, 8.118): the chips of the header strip, the banners, the facts of the
 * two groups, which actions the Actions menu offers a caller, and the merge of
 * the timeline with the lineage events for the History card.
 *
 * Nothing here reads the DOM or the session: the backend decides what a caller
 * may do, these functions only choose what to show.
 */
import { EXIT_KIND_LABELS, ORIGIN_KIND_LABELS, STATUS_LABELS, vocabLabel } from '@/generated/Vocab'
import { conditionLabel } from '@/components/components/componentDetailShared'
import { formatDay } from '@/lib/utils'
import { CUTTABLE_EXIT_KINDS, TERMINAL_EXIT_KINDS, WORKS_ORIGIN_KINDS } from '@/lib/lineage'

type Origin = {
  kind?: string | null
  planned?: boolean | null
  at?: string | null
  at_precision?: string | null
} | null | undefined

type Exit = { kind: string; at?: string | null; at_precision?: string | null; recorded_by_user_id?: string | null } | null | undefined

export type IdentityLike = {
  origin?: Origin
  exit?: Exit
  withdrawn?: { at?: string | null; reason?: string | null } | null
  is_reserved?: boolean | null
  is_public?: boolean | null
  current_snapshot_id?: string | null
  remaining?: number | null
  dataset?: string | null
  created_by_user_id?: string | null
  /** response-only: the undo of the deinstall act is open (8.115 a) */
  can_undo_deinstall?: boolean | null
}

export { formatDay }

// CHIPS -------------------------------------------------------------------------
export type ChipTone = 'neutral' | 'good' | 'info' | 'warn' | 'bad'
export type Chip = { label: string; tone: ChipTone; title?: string }

export function statusChip(snapshot: { status?: string | null }): Chip {
  const status = snapshot.status ?? 'published'
  if (status === 'published') return { label: 'Published', tone: 'good' }
  const label = vocabLabel(STATUS_LABELS, status)
  return { label: label.charAt(0).toUpperCase() + label.slice(1), tone: status === 'rejected' ? 'bad' : 'warn' }
}

/** Where the piece is: in place (identified in its works, not yet deinstalled),
 *  not in place (deinstalled or recovered, in circulation), in circulation, or
 *  the kind of its exit. */
export function circulationChip(identity: IdentityLike): Chip {
  const exit = identity.exit
  if (exit) {
    const when = formatDay(exit.at, exit.at_precision)
    return {
      label: vocabLabel(EXIT_KIND_LABELS, exit.kind),
      tone: 'warn',
      title: when ? `Left circulation on ${when}` : 'Left circulation',
    }
  }
  const origin = identity.origin
  if (origin?.planned) {
    return { label: 'In place', tone: 'info', title: 'Identified in its construction work, not yet deinstalled' }
  }
  if (origin?.kind && (WORKS_ORIGIN_KINDS as string[]).includes(origin.kind)) {
    return { label: 'Not in place', tone: 'neutral', title: 'Taken out of its construction work, in circulation' }
  }
  return { label: 'In circulation', tone: 'neutral' }
}

/** The condition chip: the grade with its label, or "not assessed". */
export function conditionChip(grade: number | null): Chip {
  if (grade === null) return { label: 'Condition not assessed', tone: 'neutral' }
  const tone: ChipTone = grade >= 3 ? 'good' : grade === 2 ? 'warn' : 'bad'
  return { label: `Condition ${conditionLabel(grade)}`, tone }
}

// BANNERS -----------------------------------------------------------------------
export type Banner = { id: string; tone: 'info' | 'warn' | 'bad'; text: string }

/** One sentence each, only what applies, nothing a chip already says. */
export function bannersOf(input: {
  identity: IdentityLike
  signedIn: boolean
  geometryFailed: boolean
}): Banner[] {
  const { identity } = input
  const out: Banner[] = []
  if (identity.withdrawn) {
    // the reason is free text: it may end with a full stop of its own
    const given = (identity.withdrawn.reason ?? '').trim().replace(/[.!?]+$/, '')
    const reason = given ? `: ${given}` : ''
    out.push({
      id: 'withdrawn', tone: 'bad',
      text: `Withdrawn on ${formatDay(identity.withdrawn.at)}${reason}. Only members of its dataset see this record.`,
    })
  }
  if (identity.exit) {
    out.push({ id: 'exited', tone: 'warn', text: 'This piece left circulation; its record stays.' })
  }
  if (input.signedIn && identity.is_public === false) {
    out.push({
      id: 'not-public', tone: 'info',
      text: `Not public: only members of ${identity.dataset ?? 'its dataset'} and the moderators see this piece.`,
    })
  }
  if (input.geometryFailed) {
    out.push({
      id: 'geometry', tone: 'bad',
      text: 'The geometry of this version could not be processed: size, class and proxies describe the previous geometry.',
    })
  }
  return out
}

// FACTS -------------------------------------------------------------------------
export type Fact = {
  label: string
  value: string
  /** an identity unit of the inheritance marker (lineage) */
  inheritedUnit?: string
  /** an RGB triple, drawn as a swatch next to the value */
  swatch?: [number, number, number]
}

export type FactGroups = { component: Fact[]; state: Fact[] }

const CAPTURE_METHODS: Record<string, string> = {
  photogrammetry: 'Photogrammetry',
  lidar: 'LiDAR',
  structured_light: 'Structured light',
  manual: 'Manual',
}

/** The facts of the page in their two groups, without duplicates: what is true
 *  of the component, and what is true of this state. The recorder and the
 *  timestamps are history, not facts. */
export function factGroups(input: {
  identity: {
    original_function: string
    material: string
    trade_name?: string | null
    material_class?: string | null
    material_class_source?: string | null
    dataset?: string | null
    remaining?: number | null
  }
  snapshot: {
    shape_class?: string | null
    bbx?: number[] | null
    complexity?: number | null
    color?: number[] | null
    quantity?: number | null
    fragment?: boolean | null
    effective_from?: string | null
    effective_from_precision?: string | null
    capture?: { method?: string | null } | null
    notes?: string | null
  }
  functionLabel: string
  shapeClassLabel: string | null
  /** the materials list's label; the id where the list does not name it */
  materialLabel?: string | null
}): FactGroups {
  const { identity, snapshot } = input
  const quantity = typeof snapshot.quantity === 'number' && snapshot.quantity >= 1 ? snapshot.quantity : 1
  const component: Fact[] = [
    { label: 'Original function', value: input.functionLabel, inheritedUnit: 'original_function' },
    {
      label: 'Material',
      value: `${input.materialLabel || identity.material}${identity.trade_name ? ` (${identity.trade_name})` : ''}`,
      inheritedUnit: 'material',
    },
  ]
  if (identity.material_class) {
    component.push({
      label: 'Waste class',
      value: `${identity.material_class}${identity.material_class_source === 'assigned' ? ' (set by hand)' : ''}`,
    })
  }
  const remaining = identity.remaining
  if (remaining !== null && remaining !== undefined && quantity > 1) {
    component.push({
      label: 'Batch',
      value: `${quantity} recorded, ${quantity - remaining} drawn, ${remaining} remaining`,
    })
  } else if (quantity > 1) {
    component.push({ label: 'Quantity', value: String(quantity) })
  }
  if (snapshot.fragment) component.push({ label: 'Fragment', value: 'Yes, of a larger piece' })
  if (identity.dataset) component.push({ label: 'Dataset', value: identity.dataset })

  const state: Fact[] = []
  if (input.shapeClassLabel) state.push({ label: 'Shape class', value: input.shapeClassLabel })
  const bbx = snapshot.bbx
  if (bbx && bbx.length >= 3 && bbx.some((v) => v > 0)) {
    state.push({ label: 'Size', value: `${bbx.slice(0, 3).map((v) => Math.round(v)).join(' x ')} mm` })
  }
  if (typeof snapshot.complexity === 'number') {
    state.push({ label: 'Complexity', value: String(snapshot.complexity) })
  }
  if (snapshot.color && snapshot.color.length >= 3) {
    const [r, g, b] = snapshot.color
    state.push({ label: 'Colour', value: `${r}/${g}/${b}`, swatch: [r, g, b] })
  }
  if (snapshot.effective_from) {
    state.push({
      label: 'State since',
      value: formatDay(snapshot.effective_from, snapshot.effective_from_precision),
    })
  }
  const method = snapshot.capture?.method
  if (method) state.push({ label: 'Capture', value: CAPTURE_METHODS[method] ?? method })
  if (snapshot.notes && snapshot.notes.trim()) state.push({ label: 'Notes', value: snapshot.notes.trim() })
  return { component, state }
}

// ACTIONS -----------------------------------------------------------------------
export type ActionKey =
  | 'pdf' | 'cero' | 'geometry' | 'locate' | 'cut' | 'draw' | 'state' | 'edit'
  | 'correct' | 'promote' | 'withdraw-version' | 'manage-versions'
  | 'exit' | 'undo-exit' | 'exit-set-by-pieces' | 'reenter'
  | 'deinstall' | 'undo-deinstall'
  | 'withdraw-component' | 'reinstate-component'

export type VersionRow = {
  _id: string
  version: number
  status: string
  is_current?: boolean
  superseded_by?: string | null
  added_by_user_id?: string | null
}

export type ActionsInput = {
  identity: IdentityLike & { dataset?: string | null; created_by_user_id?: string | null }
  versions: VersionRow[]
  signedIn: boolean
  isModerator: boolean
  isContributor: boolean
  meId?: string | null
  hasGeometryFiles: boolean
  isCero: boolean
}

const isLive = (row: VersionRow) => row.status === 'published' && !row.superseded_by

export type VersionMode = 'correct' | 'promote' | 'withdraw-version' | 'manage-versions'

/** Whether a version offers the caller something in the Actions menu's
 *  version dialogs: a row without an action for them is not listed. */
export function versionOffers(
  mode: VersionMode,
  row: VersionRow,
  caller: { isModerator: boolean; isContributor: boolean; meId?: string | null },
): boolean {
  const author = !!caller.meId && row.added_by_user_id === caller.meId
  switch (mode) {
    case 'correct':
      return caller.isContributor && isLive(row)
    case 'promote':
      return caller.isModerator && isLive(row) && !row.is_current
    case 'withdraw-version':
      return caller.isModerator && row.status === 'published'
    default:
      // the author's own draft, pending or rejected version; a moderator's
      // publish, reject, reinstate and delete
      if (['draft', 'pending', 'rejected'].includes(row.status)) return caller.isModerator || author
      return row.status === 'withdrawn' && caller.isModerator
  }
}

/** What the Actions menu offers, by group, for a caller (the backend checks
 *  again). The group order is the order shown. */
export function availableActions(input: ActionsInput): { record: ActionKey[]; moderate: ActionKey[] } {
  const { identity, versions, isModerator, isContributor, meId } = input
  const record: ActionKey[] = ['pdf']
  if (input.isCero) record.push('cero')
  const moderate: ActionKey[] = []
  if (!input.signedIn) return { record, moderate }

  if (input.hasGeometryFiles) record.push('geometry')
  record.push('locate')
  const exit = identity.exit
  const published = !!identity.current_snapshot_id
  const withdrawn = !!identity.withdrawn
  const batch = typeof identity.remaining === 'number'
  // a cut starts from a piece in circulation or one already cut (8.34); an
  // installed, returned or lost piece re-enters first
  const cuttable = !withdrawn && published && (!exit || CUTTABLE_EXIT_KINDS.includes(exit.kind))
  if (cuttable && isContributor) {
    if (!batch) record.push('cut')
    else if ((identity.remaining ?? 0) > 0) record.push('draw')
  }
  if (isContributor && !withdrawn && !exit && published) record.push('state')
  // the edit page's rule (8.9, 3.2.2): a moderator, or the creator while
  // nothing is published
  const canEdit = !withdrawn && (isModerator
    || (!published && !!meId && identity.created_by_user_id === meId))
  if (canEdit) record.push('edit')

  const caller = { isModerator, isContributor, meId }
  const offered = (mode: VersionMode) => versions.some((row) => versionOffers(mode, row, caller))
  if (offered('correct')) moderate.push('correct')
  if (offered('promote')) moderate.push('promote')
  if (offered('withdraw-version')) moderate.push('withdraw-version')
  if (offered('manage-versions')) moderate.push('manage-versions')

  if (isModerator && !withdrawn) {
    const serverSet = !!exit && !exit.recorded_by_user_id
    if (!exit && published) moderate.push('exit')
    if (exit && !serverSet) moderate.push('undo-exit')
    if (exit && serverSet) moderate.push('exit-set-by-pieces')
    if (exit && !TERMINAL_EXIT_KINDS.includes(exit.kind)) moderate.push('reenter')
    const works = !!identity.origin?.kind && (WORKS_ORIGIN_KINDS as string[]).includes(identity.origin.kind)
    if (works) {
      const inPlace = identity.origin?.planned === true
      const authoredExit = !!exit && !!exit.recorded_by_user_id
      if (inPlace && !authoredExit) moderate.push('deinstall')
      // only while the deinstall act can be taken back: the backend says so
      if (!inPlace && identity.can_undo_deinstall === true) moderate.push('undo-deinstall')
    }
  }
  if (isModerator) moderate.push(withdrawn ? 'reinstate-component' : 'withdraw-component')
  return { record, moderate }
}

// HISTORY -----------------------------------------------------------------------
export type Layers = { lineage: boolean; states: boolean; evidence: boolean }

export type HistoryEvent = {
  kind: string
  at?: string | null
  precision?: string | null
  section?: string
  [key: string]: unknown
}

export type LineageEvent = HistoryEvent & {
  kind: 'lineage'
  direction: 'from' | 'into'
  /** the related identities, number and id */
  related: { id: string; catalogNumber?: number | null }[]
}

/** The lineage events of this identity, from its relatives: "cut from #700"
 *  (its own start) and "cut into #812, #813" (the date its children began). A
 *  piece with several parents was assembled from them. */
export function lineageEvents(input: {
  startedAt: string | null | undefined
  parents: { id: string; catalogNumber?: number | null }[]
  children: { id: string; catalogNumber?: number | null; at?: string | null }[]
}): LineageEvent[] {
  const out: LineageEvent[] = []
  if (input.parents.length > 0) {
    out.push({
      kind: 'lineage', direction: 'from', at: input.startedAt ?? null, precision: 'day',
      section: 'history', related: input.parents,
    })
  }
  // children that began on the same day are one event ("cut into #812, #813")
  const byDay = new Map<string, LineageEvent>()
  for (const child of input.children) {
    const day = child.at ? child.at.slice(0, 10) : 'unknown'
    const event = byDay.get(day) ?? {
      kind: 'lineage', direction: 'into' as const, at: child.at ?? null, precision: 'day',
      section: 'history', related: [],
    }
    event.related.push({ id: child.id, catalogNumber: child.catalogNumber })
    byDay.set(day, event)
  }
  out.push(...byDay.values())
  return out
}

const LAYER_OF: Record<string, keyof Layers | null> = {
  lineage: 'lineage',
  snapshot: 'states',
  evidence: 'evidence',
}

/** The timeline and the lineage events as one list per section, the layers
 *  applied; dated events in order, undated ones at the start of their section.
 *  The origin, the deinstallation and the exit belong to no layer: they are
 *  always there. */
export function mergeHistory(
  events: HistoryEvent[],
  lineage: LineageEvent[],
  layers: Layers,
): { id: string; rows: HistoryEvent[] }[] {
  // a plain record change is in the collapsed change history, not here
  const all = [...events, ...lineage].filter((event) => {
    if (event.kind === 'metadata_changed') return false
    const layer = LAYER_OF[event.kind]
    return layer ? layers[layer] : true
  })
  const sections = ['before_cataloguing', 'history', 'after_leaving_circulation']
  return sections
    .map((id) => {
      const rows = all.filter((e) => (e.section ?? 'history') === id)
      // the timeline is in order already; only the lineage events need a place
      const placed = rows.filter((e) => e.kind !== 'lineage')
      for (const event of rows.filter((e) => e.kind === 'lineage')) {
        const index = event.at ? placed.findIndex((e) => !!e.at && String(e.at) > String(event.at)) : 0
        if (index === -1) placed.push(event)
        else placed.splice(index, 0, event)
      }
      return { id, rows: placed }
    })
    .filter((section) => section.rows.length > 0)
}

/** The label of an origin kind for the facts and the history. */
export function originLabel(kind: string | null | undefined): string {
  return vocabLabel(ORIGIN_KIND_LABELS, kind ?? 'unknown')
}
