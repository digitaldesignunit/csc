/**
 * The evidence form's state and its conversion to the bulk request
 * (spec 7.6: fan-out, repeat from the last record, apply to several
 * pieces; all ending in one `POST /evidence/bulk`). Pure functions: the
 * components only edit this state.
 */
import type { EvidenceBulkItem, EvidenceView } from '@/generated'
import type { MethodInfo, JsonSchema, QuantityInfo } from '@/lib/evidence/api'
import { getAt, fromPayload, emptyObject, parseNumber, setAt, toPayload, resolve, type FormObject, type FormValue } from '@/lib/evidence/schema'
import type { Vec3 } from '@/lib/evidence/grid'
import { layoutOf } from '@/lib/evidence/layout'

let counter = 0
export const newKey = () => `k${Date.now().toString(36)}${(counter += 1)}`

export type PositionState = {
  kind: 'none' | 'point' | 'region'
  description: string
  snapshotId: string | null
  point: Vec3 | null
}

export const emptyPosition = (): PositionState => ({
  kind: 'none', description: '', snapshotId: null, point: null,
})

export type DerivedState = {
  model: string
  value: string
  note: string
  reference: string
}

export const emptyDerived = (): DerivedState => ({ model: '', value: '', note: '', reference: '' })

export type RecordState = {
  key: string
  payload: FormObject
  position: PositionState
  derived: DerivedState
}

export type ObservationState = {
  key: string
  quantity: string
  value: string
  note: string
  photoIds: string[]
}

export type PhotoItem = { id: string; file: File }

export type SummaryState = {
  quantity: string
  value: string
  low: string
  high: string
  unit: string
  /** classes or categories, for a categorical quantity */
  classes: string[]
}

export const emptySummary = (): SummaryState => ({
  quantity: '', value: '', low: '', high: '', unit: '', classes: [],
})

export type FormState = {
  method: string
  shared: FormObject
  records: RecordState[]
  performers: FormObject[]
  standardCode: string
  standardYear: string
  observedAt: string
  notes: string
  selfAttested: boolean
  files: File[]
  summary: SummaryState
  pieces: string[]
  observations: ObservationState[]
  photos: PhotoItem[]
}

export function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function newRecord(method: MethodInfo): RecordState {
  const layout = layoutOf(method.name)
  const skeleton = emptyObject(method.payload_schema, method.payload_schema)
  const payload: FormObject = {}
  for (const [key, value] of Object.entries(skeleton)) {
    if (!layout.shared.includes(key)) payload[key] = value
  }
  return { key: newKey(), payload, position: emptyPosition(), derived: emptyDerived() }
}

export function initialState(method: MethodInfo, identityId: string): FormState {
  const layout = layoutOf(method.name)
  const skeleton = emptyObject(method.payload_schema, method.payload_schema)
  const shared: FormObject = {}
  for (const key of layout.shared) if (key in skeleton) shared[key] = skeleton[key]
  return {
    method: method.name,
    shared,
    records: layout.fanOut === 'observations' ? [] : [newRecord(method)],
    performers: [],
    standardCode: '',
    standardYear: '',
    observedAt: today(),
    notes: '',
    selfAttested: false,
    files: [],
    summary: emptySummary(),
    pieces: [identityId],
    observations: layout.fanOut === 'observations' ? [newObservation()] : [],
    photos: [],
  }
}

export function newObservation(quantity = ''): ObservationState {
  return { key: newKey(), quantity, value: '', note: '', photoIds: [] }
}

/** A copy of a record with its result parts emptied (add another / repeat). */
export function blankedCopy(method: MethodInfo, source: FormObject): FormObject {
  const layout = layoutOf(method.name)
  const fresh = emptyObject(method.payload_schema, method.payload_schema)
  let next: FormObject = JSON.parse(JSON.stringify(source)) as FormObject
  for (const path of layout.blankOnRepeat) {
    const steps = path.split('.')
    next = setAt(next, steps, getAt(fresh, steps) ?? '')
  }
  return next
}

/** A fresh record that starts as a copy of `from` with the results emptied. */
export function repeatedRecord(method: MethodInfo, from: RecordState): RecordState {
  return {
    key: newKey(),
    payload: blankedCopy(method, from.payload),
    position: { ...emptyPosition(), snapshotId: from.position.snapshotId },
    derived: emptyDerived(),
  }
}

/**
 * The form values of my latest record of this method (repeat from my last
 * record): instrument, performers, standard and lab details are kept;
 * readings and results start empty, dates default to today.
 */
export function stateFromLast(
  method: MethodInfo,
  identityId: string,
  last: EvidenceView,
  actorRoot: JsonSchema | null,
): FormState {
  const layout = layoutOf(method.name)
  const state = initialState(method, identityId)
  const full = fromPayload(method.payload_schema, last.payload ?? {}, method.payload_schema)
  for (const key of layout.shared) if (key in full) state.shared[key] = full[key]
  const blanked = blankedCopy(method, full)
  const record = state.records[0]
  if (record) {
    for (const key of Object.keys(record.payload)) {
      if (key in blanked) record.payload[key] = blanked[key]
    }
  }
  if (actorRoot) {
    const actorSchema = resolve({ $ref: '#/$defs/Actor' }, actorRoot).schema
    state.performers = (last.performed_by ?? []).map((actor) =>
      fromPayload(actorSchema, actor as unknown as Record<string, unknown>, actorRoot))
  }
  if (last.standard) {
    state.standardCode = last.standard.code
    state.standardYear = last.standard.year ? String(last.standard.year) : ''
  }
  return state
}

// BUILDING THE REQUEST ---------------------------------------------------------
export type BuildContext = {
  identityId: string
  method: MethodInfo
  actorRoot: JsonSchema | null
  snapshotId: string
  quantities: QuantityInfo[]
}

function positionBody(position: PositionState, method: MethodInfo, ctx: BuildContext): Record<string, unknown> | undefined {
  if (method.name === 'reinforcement_layout') {
    return {
      kind: 'region', snapshot_id: ctx.snapshotId,
      description: position.description.trim() || undefined,
    }
  }
  const description = position.description.trim() || undefined
  if (position.kind === 'point' && position.point && position.snapshotId) {
    return { kind: 'point', snapshot_id: position.snapshotId, point: position.point, description }
  }
  if (position.kind === 'region' && position.snapshotId) {
    return { kind: 'region', snapshot_id: position.snapshotId, description }
  }
  if (description) return { kind: 'none', description }
  return undefined
}

function actorsBody(state: FormState, ctx: BuildContext): Record<string, unknown>[] {
  if (!ctx.actorRoot) return []
  const actorSchema = resolve({ $ref: '#/$defs/Actor' }, ctx.actorRoot).schema
  return state.performers
    .map((actor) => toPayload(actorSchema, actor, ctx.actorRoot as JsonSchema))
    .filter((actor) => Object.keys(actor).length > 0 && actor.kind !== undefined)
}

function summaryBody(summary: SummaryState, quantity: QuantityInfo | undefined): Record<string, unknown> | undefined {
  if (!summary.quantity) return undefined
  const body: Record<string, unknown> = { quantity: summary.quantity }
  const value = parseNumber(summary.value)
  if (quantity?.kind === 'scalar') {
    if (summary.value.trim() !== '') body.value = value ?? summary.value
    const low = parseNumber(summary.low)
    const high = parseNumber(summary.high)
    if (summary.low.trim() !== '' || summary.high.trim() !== '') {
      body.range = [low ?? summary.low, high ?? summary.high]
    }
    if (summary.unit) body.unit = summary.unit
  } else if (summary.classes.length) {
    body.range = summary.classes
  }
  return body
}

export function derivedBody(derived: DerivedState, method: MethodInfo): Record<string, unknown>[] {
  const model = method.derived_models.find((m) => m.kind === derived.model)
  if (!model || model.server_built) return []
  const item: Record<string, unknown> = {
    quantity: model.quantity,
    kind: 'derived',
    model: {
      kind: model.kind,
      reference: derived.reference.trim() || undefined,
      note: derived.note.trim() || undefined,
    },
  }
  if (derived.value.trim() !== '') {
    const n = parseNumber(derived.value)
    item.value = n === null ? derived.value.trim() : n
  }
  return [item]
}

/** A date typed in a date field as the UTC midnight the server stores (precision day). */
function midnight(date: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? `${date}T00:00:00Z` : date
}

/** The payload with the dates the server reads as the record's own as timestamps. */
function stamped(payload: Record<string, unknown>, paths: string[]): Record<string, unknown> {
  const out = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>
  for (const path of paths) {
    const steps = path.split('.')
    let node: Record<string, unknown> | undefined = out
    for (const step of steps.slice(0, -1)) node = node?.[step] as Record<string, unknown> | undefined
    const key = steps[steps.length - 1]
    if (node && typeof node[key] === 'string') node[key] = midnight(node[key] as string)
  }
  return out
}

export function buildItems(state: FormState, ctx: BuildContext): EvidenceBulkItem[] {
  const { method } = ctx
  const layout = layoutOf(method.name)
  const schema = method.payload_schema
  const performed_by = actorsBody(state, ctx)
  const standard = state.standardCode.trim()
    ? { code: state.standardCode.trim(), year: parseNumber(state.standardYear) ?? undefined }
    : undefined
  const common = {
    standard,
    performed_by,
    notes: state.notes.trim() || undefined,
    self_attested: state.selfAttested || undefined,
    ...(method.context_time === 'sampled_at'
      // a core's dates are in its payload; only the precision is the form's
      ? { observed_at_precision: 'day' as const, sampled_at_precision: 'day' as const }
      : { observed_at: state.observedAt ? midnight(state.observedAt) : undefined, observed_at_precision: 'day' as const }),
  }

  if (layout.fanOut === 'observations') {
    return state.observations.map((o) => ({
      ...common,
      identity_id: ctx.identityId,
      method: method.name as EvidenceBulkItem['method'],
      payload: {
        observations: [{
          quantity: o.quantity,
          value: parseNumber(o.value) ?? o.value,
          note: o.note.trim() || undefined,
        }],
      },
    })) as unknown as EvidenceBulkItem[]
  }

  if (layout.fanOut === 'pieces') {
    const quantity = ctx.quantities.find((q) => q.name === state.summary.quantity)
    const payload = stamped(toPayload(schema, state.records[0]?.payload ?? {}, schema), layout.timestampFields)
    return state.pieces.map((identityId) => ({
      ...common,
      identity_id: identityId,
      method: method.name as EvidenceBulkItem['method'],
      payload,
      summary: summaryBody(state.summary, quantity),
    })) as unknown as EvidenceBulkItem[]
  }

  return state.records.map((record) => {
    const merged: FormObject = { ...record.payload }
    for (const key of layout.shared) merged[key] = state.shared[key]
    return {
      ...common,
      identity_id: ctx.identityId,
      method: method.name as EvidenceBulkItem['method'],
      payload: stamped(toPayload(schema, merged, schema), layout.timestampFields),
      position: positionBody(record.position, method, ctx),
      derived: derivedBody(record.derived, method),
    }
  }) as unknown as EvidenceBulkItem[]
}

export type CandidateRebound = {
  id: string
  label: string
  observedAt: string
  precision: string | null
  median: number | null
  status: string
}

/**
 * Rebound records a core may name (8.42): same component, not discarded,
 * not after the coring, not already paired.
 */
export function pairingCandidates(
  rebounds: EvidenceView[],
  cores: EvidenceView[],
  coredAt: string,
  taken: string[],
): CandidateRebound[] {
  const paired = new Set<string>(taken)
  for (const core of cores) {
    if (core.status === 'rejected' || core.status === 'withdrawn' || core.superseded_by) continue
    const id = ((core.payload?.sampling as { paired_rebound_id?: string } | undefined)?.paired_rebound_id)
    if (id) paired.add(id)
  }
  const limit = coredAt ? Date.parse(coredAt.length === 10 ? `${coredAt}T23:59:59Z` : coredAt) : Infinity
  return rebounds
    .filter((r) => r.status !== 'rejected' && r.status !== 'withdrawn' && !r.superseded_by)
    .filter((r) => !paired.has(r._id))
    .filter((r) => (r.payload?.set_discarded as boolean | null | undefined) !== true)
    .filter((r) => !Number.isFinite(limit) || Date.parse(r.observed_at) <= limit)
    .map((r) => {
      const area = (r.payload?.test_area ?? {}) as { label?: string | null }
      const median = typeof r.payload?.median === 'number' ? (r.payload.median as number) : null
      return {
        id: r._id,
        label: area.label || r._id.slice(0, 8),
        observedAt: r.observed_at,
        precision: r.observed_at_precision ?? null,
        median,
        status: r.status,
      }
    })
}

export type FormValueLike = FormValue

/** The form for a correction: every value of the record being superseded. */
export function stateFromRecord(
  method: MethodInfo,
  record: EvidenceView,
  actorRoot: JsonSchema | null,
): FormState {
  const layout = layoutOf(method.name)
  const state = initialState(method, record.identity_id)
  const full = fromPayload(method.payload_schema, record.payload ?? {}, method.payload_schema)
  for (const key of layout.shared) if (key in full) state.shared[key] = full[key]
  const first = state.records[0]
  if (first) {
    for (const key of Object.keys(first.payload)) first.payload[key] = full[key] ?? first.payload[key]
    const position = record.position
    if (position) {
      first.position = {
        kind: position.kind === 'point' || position.kind === 'region' ? position.kind : 'none',
        description: position.description ?? '',
        snapshotId: position.snapshot_id ?? null,
        point: Array.isArray(position.point) && position.point.length === 3
          ? (position.point as Vec3) : null,
      }
    }
    const derived = (record.derived ?? []).find((d) => {
      const model = method.derived_models.find((m) => m.kind === d.model.kind)
      return model && !model.server_built
    })
    if (derived) {
      first.derived = {
        model: derived.model.kind,
        value: derived.value !== undefined && derived.value !== null ? String(derived.value) : '',
        note: derived.model.note ?? '',
        reference: derived.model.reference ?? '',
      }
    }
  }
  if (actorRoot) {
    const actorSchema = resolve({ $ref: '#/$defs/Actor' }, actorRoot).schema
    state.performers = (record.performed_by ?? []).map((actor) =>
      fromPayload(actorSchema, actor as unknown as Record<string, unknown>, actorRoot))
  }
  if (record.standard) {
    state.standardCode = record.standard.code
    state.standardYear = record.standard.year ? String(record.standard.year) : ''
  }
  state.observedAt = (record.observed_at ?? '').slice(0, 10) || today()
  state.notes = record.notes ?? ''
  state.summary = {
    ...emptySummary(),
    quantity: record.summary.quantity,
    value: record.summary.value !== undefined && record.summary.value !== null ? String(record.summary.value) : '',
    low: Array.isArray(record.summary.range) && typeof record.summary.range[0] === 'number' ? String(record.summary.range[0]) : '',
    high: Array.isArray(record.summary.range) && typeof record.summary.range[1] === 'number' ? String(record.summary.range[1]) : '',
    unit: record.summary.unit ?? '',
    classes: Array.isArray(record.summary.range) && typeof record.summary.range[0] !== 'number'
      ? record.summary.range.map(String) : [],
  }
  if (layout.fanOut === 'observations') {
    const observation = ((record.payload?.observations ?? []) as { quantity: string; value: number; note?: string | null }[])[0]
    state.observations = [{
      ...newObservation(observation?.quantity ?? record.summary.quantity),
      value: observation ? String(observation.value) : '',
      note: observation?.note ?? '',
    }]
  }
  state.pieces = [record.identity_id]
  return state
}
