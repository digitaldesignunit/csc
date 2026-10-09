/**
 * The pure parts of Browse and its filter bar (plan P11 stage 2, decision
 * 8.118 Q6, Q8, Q9, Q10): the circulation switch kept in the URL, the filters
 * and their chips, the card line of a phone, the search field that also takes
 * a number or an id, the status of a row.
 *
 * Nothing here reads the DOM, the session or the network.
 */
import { ORIGINAL_FUNCTION_LABELS, SHAPE_CLASS_LABELS, vocabLabel } from '@/generated/Vocab'
import { circulationChip, type Chip } from '@/lib/componentDetail'
import { uuidFromScan } from '@/lib/scanIds'

// CIRCULATION ------------------------------------------------------------------
/** The values of `?circulation=` (they are the backend's, so links keep working). */
export const CIRCULATION_VALUES = ['active', 'in_place', 'deinstalled', 'exited', 'all'] as const
export type Circulation = (typeof CIRCULATION_VALUES)[number]
export type CirculationGroup = 'in' | 'out' | 'all'

export function parseCirculation(value: string | null | undefined): Circulation {
  return (CIRCULATION_VALUES as readonly string[]).includes(value ?? '')
    ? (value as Circulation)
    : 'active'
}

export function circulationGroup(value: Circulation): CirculationGroup {
  if (value === 'exited') return 'out'
  if (value === 'all') return 'all'
  return 'in'
}

/** The three positions of the switch (glossary: in circulation / out of circulation). */
export const CIRCULATION_GROUPS: { group: CirculationGroup; label: string; value: Circulation }[] = [
  { group: 'in', label: 'In circulation', value: 'active' },
  { group: 'out', label: 'Out of circulation', value: 'exited' },
  { group: 'all', label: 'All', value: 'all' },
]

/** The sub-filter of "In circulation". */
export const IN_CIRCULATION_PARTS: { value: Circulation; label: string }[] = [
  { value: 'active', label: 'Any' },
  { value: 'in_place', label: 'In place' },
  { value: 'deinstalled', label: 'Not in place' },
]

export const CIRCULATION_HELP =
  'In circulation: pieces that can still be reused, in place in their construction work or not. '
  + 'Out of circulation: pieces that left it (split, installed elsewhere, recycled, returned or lost). '
  + 'All shows both.'

/** What `URLSearchParams` and Next's read-only search params both offer. */
export type ParamsLike = { get(name: string): string | null; toString(): string }

// FILTERS ----------------------------------------------------------------------
/** The URL parameters that filter the list (not the paging, the sort or the search). */
export const FILTER_KEYS = [
  'original_function',
  'material',
  'dataset',
  'shape_class',
  'complexity',
  'fragment',
  'bbx_min_x',
  'bbx_max_x',
  'bbx_min_y',
  'bbx_max_y',
  'bbx_min_z',
  'bbx_max_z',
] as const
export type FilterKey = (typeof FILTER_KEYS)[number]

/** The Browse link of a dataset or a material: the filter bar reads it from the URL. */
export function browseUrl(key: 'dataset' | 'material', value: string): string {
  return `/components?${key}=${encodeURIComponent(value)}`
}

/** The three that are always visible; the others sit behind "More filters". */
export const MAIN_FILTER_KEYS: FilterKey[] = ['original_function', 'material', 'dataset']

export function activeFilters(params: ParamsLike): { key: FilterKey; value: string }[] {
  const out: { key: FilterKey; value: string }[] = []
  for (const key of FILTER_KEYS) {
    const value = params.get(key)
    if (value) out.push({ key, value })
  }
  return out
}

const AXIS = { x: 'X', y: 'Y', z: 'Z' } as const

/** The chip of one active filter: "Function: Beam", "Width min: 100". */
export function filterChipLabel(
  key: FilterKey,
  value: string,
  labels: { material?: (id: string) => string } = {},
): string {
  switch (key) {
    case 'original_function':
      return `Function: ${vocabLabel(ORIGINAL_FUNCTION_LABELS, value)}`
    case 'material':
      return `Material: ${labels.material ? labels.material(value) : value}`
    case 'dataset':
      return `Dataset: ${value}`
    case 'shape_class':
      return `Shape class: ${vocabLabel(SHAPE_CLASS_LABELS, value)}`
    case 'complexity':
      return `Complexity: ${value}`
    case 'fragment':
      return value === 'true' ? 'Fragments only' : 'No fragments'
    default: {
      const match = /^bbx_(min|max)_([xyz])$/.exec(key)
      if (!match) return `${key}: ${value}`
      return `Size ${AXIS[match[2] as 'x' | 'y' | 'z']} ${match[1]}: ${value}`
    }
  }
}

/** The params with some set or removed (null / empty removes); a change of the
 *  list goes back to page 1 unless `keepPage`. */
export function withParams(
  params: ParamsLike,
  changes: Record<string, string | null | undefined>,
  keepPage = false,
): URLSearchParams {
  const next = new URLSearchParams(params.toString())
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || value === undefined || value === '') next.delete(key)
    else next.set(key, value)
  }
  if (!keepPage) next.delete('page')
  return next
}

/** The params without any filter (the circulation, the search and the sort stay). */
export function withoutFilters(params: ParamsLike): URLSearchParams {
  const next = new URLSearchParams(params.toString())
  for (const key of FILTER_KEYS) next.delete(key)
  next.delete('page')
  return next
}

// SEARCH -----------------------------------------------------------------------
export type SearchTarget =
  | { kind: 'id'; id: string }
  | { kind: 'q'; q: string }
  | { kind: 'none' }

/** What the search field means: a complete id or a link to one opens the
 *  piece; anything else (a name, a number, the start of an id) is the list's
 *  `q`. */
export function searchTarget(text: string): SearchTarget {
  const trimmed = text.trim()
  if (!trimmed) return { kind: 'none' }
  const id = uuidFromScan(trimmed)
  if (id) return { kind: 'id', id }
  return { kind: 'q', q: trimmed }
}

// ROWS -------------------------------------------------------------------------
type RowLike = {
  bbx?: number[] | null
  original_function?: string | null
  material?: string | null
  quantity?: number | null
  exit?: { kind: string; at?: string | null; at_precision?: string | null } | null
  origin?: { kind?: string | null; planned?: boolean | null } | null
  is_reserved?: boolean | null
  reserved?: string | null
  name?: string | null
  catalog_number?: number | null
}

/** "4457 x 644 x 601" (millimetres), or an empty text when the state has no box. */
export function sizeLabel(bbx: number[] | null | undefined): string {
  if (!bbx || bbx.length < 3 || !bbx.slice(0, 3).every((v) => typeof v === 'number' && v > 0)) return ''
  return bbx.slice(0, 3).map((v) => Math.round(v)).join(' x ')
}

/** "Beam / concrete / 4457 x 644 x 601 mm": what a phone card says in one line. */
export function cardLine(row: RowLike, materialLabel?: string | null): string {
  const parts = [
    vocabLabel(ORIGINAL_FUNCTION_LABELS, row.original_function),
    materialLabel ?? row.material ?? '',
  ].filter(Boolean)
  const size = sizeLabel(row.bbx)
  if (size) parts.push(`${size} mm`)
  return parts.join(' / ')
}

/** "N pieces" for a batch (a state with more than one piece), else nothing. */
export function piecesNote(row: RowLike): string {
  const quantity = row.quantity ?? 1
  return quantity > 1 ? `${quantity} pieces` : ''
}

/** The status of a row, one chip: where it is, or that somebody has reserved
 *  it. A reservation is shown as a status only, never as a person (8.101). */
export function rowStatus(row: RowLike): Chip {
  if (row.exit) return circulationChip(row)
  if (row.is_reserved || row.reserved) return { label: 'Reserved', tone: 'warn' }
  const where = circulationChip(row)
  if (where.label === 'In place') return where
  return { label: 'Available', tone: 'good' }
}

/** The name of a row: its name, else its number, else "Unnamed component". */
export function rowName(row: RowLike): string {
  const name = typeof row.name === 'string' ? row.name.trim() : ''
  if (name) return name
  return row.catalog_number != null ? `Component #${row.catalog_number}` : 'Unnamed component'
}

/** "#12", under the name. */
export function rowNumber(row: RowLike): string {
  return row.catalog_number != null ? `#${row.catalog_number}` : ''
}

// COLUMNS ----------------------------------------------------------------------
/** The eight columns of the desktop table, then those the picker can add. */
export const BASE_COLUMNS = ['name', 'original_function', 'material', 'dataset', 'size', 'shape_class', 'status'] as const
export const OPTIONAL_COLUMNS: { key: string; label: string }[] = [
  { key: '_id', label: 'Identity id' },
  { key: 'color', label: 'Colour' },
  { key: 'fragment', label: 'Fragment' },
  { key: 'complexity', label: 'Complexity' },
  { key: 'location', label: 'Location' },
  { key: 'created', label: 'Created' },
  { key: 'lastmodified', label: 'Last modified' },
]

/** The picked optional columns from a stored text, only known keys. */
export function parsePickedColumns(text: string | null | undefined): string[] {
  if (!text) return []
  try {
    const value: unknown = JSON.parse(text)
    if (!Array.isArray(value)) return []
    const known = new Set(OPTIONAL_COLUMNS.map((c) => c.key))
    return value.filter((v): v is string => typeof v === 'string' && known.has(v))
  } catch {
    return []
  }
}
