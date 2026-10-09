/**
 * Pure parts of the snapshot form (spec 7.6, decisions 7.5, 8.87): the
 * authored box from L x W x H, the request bodies of the four modes and the
 * checks the form makes before it asks the backend. Nothing here talks to
 * the network, so the unit test covers it.
 */
import type { Origin } from '@/generated/CatalogModels'

export type FormMode = 'new' | 'cut' | 'state' | 'correct'

export const MODE_TITLES: Record<FormMode, string> = {
  new: 'New component',
  cut: 'Cut from pieces',
  state: 'Record new state',
  correct: 'Correct this version',
}

const IDENTITY_PLACEMENT = { o: [0, 0, 0], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }

// DIMENSIONS ------------------------------------------------------------------
/** Parse a dimension text field; NaN when empty or invalid. */
export function parseDimensionMm(value: string): number {
  const trimmed = value.trim().replace(',', '.')
  if (!trimmed) return Number.NaN
  return parseFloat(trimmed)
}

/** Allow empty and partial decimals while the user types ("12.", ".5"). */
export function sanitizeDimensionInput(value: string): string {
  const v = value.replace(',', '.')
  if (v === '') return ''
  if (/^\d*\.?\d*$/.test(v)) return v
  return v.slice(0, -1)
}

/** L, W, H in mm as numbers, or null unless all three are positive. */
export function validDimensions(l: string, w: string, h: string): [number, number, number] | null {
  const values: [number, number, number] = [parseDimensionMm(l), parseDimensionMm(w), parseDimensionMm(h)]
  return values.every((v) => Number.isFinite(v) && v > 0) ? values : null
}

/**
 * Sort L / W / H into the box axes of the proxy (App. B: x longest, z
 * shortest); a column stands, its longest side along z.
 */
export function canonicalizeBoxAxesMm(
  lengthMm: number,
  widthMm: number,
  heightMm: number,
  column = false,
): { xMm: number; yMm: number; zMm: number } {
  const [longest, middle, shortest] = [lengthMm, widthMm, heightMm]
    .map((v) => Math.max(0.1, v))
    .sort((a, b) => b - a)
  return column
    ? { xMm: middle, yMm: shortest, zMm: longest }
    : { xMm: longest, yMm: middle, zMm: shortest }
}

export function boxAxisHint(column: boolean): string {
  return column
    ? 'a column stands: the longest side becomes its height'
    : 'the longest side lies along x, the shortest along z'
}

export type AuthoredGeometry = {
  meshes: unknown[]
  point_clouds: unknown[]
  proxies: unknown[]
}

/** An authored box proxy from L x W x H (the only geometry the web writes). */
export function authoredBox(lengthMm: number, widthMm: number, heightMm: number, column: boolean): AuthoredGeometry {
  const { xMm, yMm, zMm } = canonicalizeBoxAxesMm(lengthMm, widthMm, heightMm, column)
  return {
    meshes: [],
    point_clouds: [],
    proxies: [{
      primitive: 'box',
      role: 'primary',
      params: { size: [xMm, yMm, zMm] },
      placement: IDENTITY_PLACEMENT,
      fit: { method: 'authored' },
      regions: [],
    }],
  }
}

type StoredGeometry = {
  meshes?: unknown[] | null
  point_clouds?: unknown[] | null
  proxies?: { primitive?: string; params?: { size?: number[] }; fit?: { method?: string } | null }[] | null
}

/**
 * A snapshot whose whole geometry is one authored box (what the web wrote).
 * Only such a geometry is copied by a correction: stored mesh and point
 * cloud files are not copied by `supersede` (decision 8.88).
 */
export function isAuthoredBoxOnly(geometry: StoredGeometry | null | undefined): boolean {
  if (!geometry) return false
  if ((geometry.meshes ?? []).length > 0 || (geometry.point_clouds ?? []).length > 0) return false
  const proxies = geometry.proxies ?? []
  return proxies.length > 0 && proxies.every((p) => p.fit?.method === 'authored')
}

/** The size of a stored authored box as strings for the three fields. */
export function boxDimensionsOf(geometry: StoredGeometry | null | undefined): [string, string, string] | null {
  const size = geometry?.proxies?.find((p) => p.primitive === 'box')?.params?.size
  if (!Array.isArray(size) || size.length !== 3 || !size.every((v) => typeof v === 'number' && v > 0)) return null
  return size.map((v) => String(Math.round(v * 100) / 100)) as [string, string, string]
}

/** The geometry a correction keeps: the authored proxies, as stored. */
export function keptGeometry(geometry: StoredGeometry): AuthoredGeometry {
  return { meshes: [], point_clouds: [], proxies: [...(geometry.proxies ?? [])] }
}

// FIELDS ----------------------------------------------------------------------
export type SnapshotFields = {
  name: string
  notes: string
  color: [number, number, number]
  /** Decimal degrees as typed; both empty = no location. */
  lat: string
  lon: string
  quantity: number
  fragment: boolean
  /** `YYYY-MM-DD`: when the state began (cut / new state); empty = now. */
  effectiveOn: string
}

export function emptyFields(): SnapshotFields {
  return {
    name: '', notes: '', color: [110, 110, 110], lat: '', lon: '', quantity: 1, fragment: false, effectiveOn: '',
  }
}

export function hexToRgb(hex: string): [number, number, number] | null {
  const m = hex.trim().replace(/^#/, '')
  if (!/^[0-9a-f]{6}$/i.test(m)) return null
  return [parseInt(m.slice(0, 2), 16), parseInt(m.slice(2, 4), 16), parseInt(m.slice(4, 6), 16)]
}

/** A location from two text fields; null when empty, undefined when wrong. */
export function parseLocation(lat: string, lon: string): { lat: number; lon: number } | null | undefined {
  if (!lat.trim() && !lon.trim()) return null
  const la = parseFloat(lat.trim().replace(',', '.'))
  const lo = parseFloat(lon.trim().replace(',', '.'))
  if (!Number.isFinite(la) || !Number.isFinite(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) return undefined
  return { lat: la, lon: lo }
}

/** `YYYY-MM-DD` as a day-precise timestamp; empty stays null. */
export function dayToTimestamp(day: string): string | null {
  const trimmed = day.trim()
  return /^\d{4}-\d{2}-\d{2}$/.test(trimmed) ? `${trimmed}T00:00:00Z` : null
}

// REQUEST BODIES --------------------------------------------------------------
/** The body of `POST /identities/{id}/snapshots` and `.../supersede`. */
export function snapshotBody(
  fields: SnapshotFields,
  /** Omitted for a draw from a batch: the server copies the batch's proxy (8.105). */
  geometry: AuthoredGeometry | undefined,
  options: { inheritDate: boolean },
) {
  const location = parseLocation(fields.lat, fields.lon)
  const effective = options.inheritDate ? null : dayToTimestamp(fields.effectiveOn)
  return {
    name: fields.name.trim() || null,
    ...(geometry ? { geometry } : {}),
    fragment: fields.fragment,
    quantity: Math.max(1, Math.floor(fields.quantity) || 1),
    color: fields.color,
    ...(location ? { location } : {}),
    notes: fields.notes.trim() || null,
    ...(effective ? { effective_from: effective, effective_from_precision: 'day' } : {}),
  }
}

export type IdentityFields = {
  /** The id on the tag; empty = generated (cut only). */
  tag: string
  dataset: string
  parents: string[]
  originalFunction: string | null
  material: string
  tradeName: string
  origin: Origin | null
}

/** The body of `POST /identities`: a child omits whatever it inherits (3.1.2). */
export function identityBody(identity: IdentityFields, snapshot: ReturnType<typeof snapshotBody>) {
  const child = identity.parents.length > 0
  return {
    ...(identity.tag ? { id: identity.tag } : {}),
    dataset: identity.dataset,
    ...(child ? { parent_identities: identity.parents } : {}),
    ...(identity.originalFunction ? { original_function: identity.originalFunction } : {}),
    // a child states only what it overrides, e.g. a merge of parents that disagree
    ...(identity.material ? { material: identity.material } : {}),
    ...(identity.tradeName.trim() ? { trade_name: identity.tradeName.trim() } : {}),
    ...(identity.origin && !child ? { origin: identity.origin } : {}),
    snapshot,
  }
}

// EDIT ------------------------------------------------------------------------
/** The mutable metadata of a snapshot (spec 3.2.2), as the edit page holds it. */
export type Metadata = Pick<SnapshotFields, 'name' | 'notes' | 'color' | 'lat' | 'lon'>

/**
 * The `PATCH /snapshots/{sid}` body: only what changed; `undefined` when
 * the location text is not a location.
 */
export function metadataPatch(before: Metadata, after: Metadata): Record<string, unknown> | undefined {
  const patch: Record<string, unknown> = {}
  if (after.name.trim() !== before.name.trim()) patch.name = after.name.trim() || null
  if (after.notes.trim() !== before.notes.trim()) patch.notes = after.notes.trim() || null
  if (after.color.join() !== before.color.join()) patch.color = after.color
  if (after.lat.trim() !== before.lat.trim() || after.lon.trim() !== before.lon.trim()) {
    const location = parseLocation(after.lat, after.lon)
    if (location === undefined) return undefined
    patch.location = location
  }
  return patch
}

// CHECKS ----------------------------------------------------------------------
export type Problem = { field: string; message: string }

export type CheckInput = {
  mode: FormMode
  fields: SnapshotFields
  identity: IdentityFields
  dimensions: [string, string, string]
  /** Correct: the geometry is kept unless a size is typed again. */
  sizeEntered: boolean
  /** A draw from a batch with this many pieces left (8.105); undefined otherwise. */
  draw?: { remaining: number }
}

/** What blocks a submit, in the order the form shows it. */
export function problemsOf(input: CheckInput): Problem[] {
  const out: Problem[] = []
  const { mode, fields, identity } = input
  if (mode === 'new' || mode === 'cut') {
    if (!identity.dataset) {
      out.push({ field: 'dataset', message: 'You contribute to no dataset; ask its moderator for the contributor role.' })
    }
  }
  if (mode === 'new') {
    if (!identity.tag) out.push({ field: 'tag', message: 'Scan or paste the id on the tag.' })
    if (!identity.originalFunction) out.push({ field: 'original_function', message: 'Choose the original function.' })
    if (!identity.material) out.push({ field: 'material', message: 'Choose the material.' })
  }
  if (mode === 'cut' && identity.parents.length === 0) {
    out.push({ field: 'parents', message: 'Scan at least one parent tag.' })
  }
  // a correction keeps its geometry and a draw takes the batch's proxy, unless a size is typed
  const needsSize = mode === 'correct' || input.draw ? input.sizeEntered : true
  if (needsSize && !validDimensions(...input.dimensions)) {
    out.push({ field: 'size', message: 'Give length, width and height in mm.' })
  }
  if (input.draw && fields.quantity > input.draw.remaining) {
    out.push({
      field: 'quantity',
      message: input.draw.remaining > 0
        ? `Only ${input.draw.remaining} ${input.draw.remaining === 1 ? 'piece remains' : 'pieces remain'} in the batch.`
        : 'No pieces remain in the batch.',
    })
  }
  if (parseLocation(fields.lat, fields.lon) === undefined) {
    out.push({ field: 'location', message: 'Latitude and longitude: two numbers within range, or both empty.' })
  }
  if (fields.effectiveOn.trim() && !dayToTimestamp(fields.effectiveOn)) {
    out.push({ field: 'effective_on', message: 'The date must be a day.' })
  }
  return out
}
