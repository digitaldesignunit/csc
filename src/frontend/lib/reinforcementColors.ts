/**
 * Colours of the reinforcement bars in the viewer (RL3, plan 0.6): by layout
 * (one colour per `reinforcement_layout` record; the default when more than
 * one layout is shown) or by diameter (a sequential scale), with a legend.
 * Pure: the viewer draws what this returns.
 */
import { formatDay } from '@/lib/utils'

export type BarColourMode = 'steel' | 'layout' | 'diameter'

export const BAR_COLOUR_OPTIONS: { value: BarColourMode; label: string }[] = [
  { value: 'steel', label: 'Steel' },
  { value: 'layout', label: 'Layout' },
  { value: 'diameter', label: 'Diameter' },
]

/** Colour-blind safe (Okabe and Ito), without black and the pale yellow. */
export const LAYOUT_COLOURS = [
  '#0072b2', '#d55e00', '#009e73', '#cc79a7', '#e69f00', '#56b4e9', '#7b3294', '#8c6d31',
]

export function layoutColour(index: number): string {
  return LAYOUT_COLOURS[((index % LAYOUT_COLOURS.length) + LAYOUT_COLOURS.length) % LAYOUT_COLOURS.length]
}

/** The mode when the bars load: the layouts apart when there are several. */
export function defaultColourMode(layoutCount: number): BarColourMode {
  return layoutCount > 1 ? 'layout' : 'steel'
}

// DIAMETER --------------------------------------------------------------------
/** Light to dark: yellow, green, teal, deep violet (a viridis-like ramp). */
const RAMP = [
  [253, 231, 37],
  [94, 201, 98],
  [33, 145, 140],
  [59, 82, 139],
  [68, 1, 84],
] as const

const hex = (n: number) => Math.round(n).toString(16).padStart(2, '0')

/** A sequential colour for `t` from 0 (smallest) to 1 (largest). */
export function rampColour(t: number): string {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0))
  const scaled = clamped * (RAMP.length - 1)
  const low = Math.min(RAMP.length - 2, Math.floor(scaled))
  const f = scaled - low
  const [a, b] = [RAMP[low], RAMP[low + 1]]
  return `#${hex(a[0] + (b[0] - a[0]) * f)}${hex(a[1] + (b[1] - a[1]) * f)}${hex(a[2] + (b[2] - a[2]) * f)}`
}

export function diameterRange(bars: { diameter_mm: number }[]): { min: number; max: number } {
  const sizes = bars.map((bar) => bar.diameter_mm).filter((d) => Number.isFinite(d) && d > 0)
  if (sizes.length === 0) return { min: 0, max: 0 }
  return { min: Math.min(...sizes), max: Math.max(...sizes) }
}

/**
 * The bars the diameter scale and its legend span: all of them, or only the bars
 * of the layout opened by `?layout=` (8.178) while one is picked; the other
 * bars are drawn faint and take the colour their diameter has on that scale.
 */
export function scaleBars<B extends { layout?: number }>(bars: B[], picked: number | null): B[] {
  return picked === null ? bars : bars.filter((bar) => bar.layout === picked)
}

export function diameterColour(diameter: number, range: { min: number; max: number }): string {
  // one diameter only: the middle of the ramp, not an arbitrary end
  if (range.max <= range.min) return rampColour(0.5)
  return rampColour((diameter - range.min) / (range.max - range.min))
}

// LAYOUTS ---------------------------------------------------------------------
export type BarLayout = {
  id: string
  label: string
  count: number
  /** The layout opened by `?layout=` (8.178): its status text, null for a current published one. */
  status?: string | null
  picked?: boolean
}

type RecordLike = {
  _id?: string
  observed_at?: string | null
  observed_at_precision?: string | null
  payload?: { document?: { title?: string | null } | null } | null
}

/** A name for each layout: the drawing's title, else the day, else a number;
 *  equal names get a number so that the legend tells them apart. */
export function layoutLabels(records: RecordLike[]): string[] {
  const base = records.map((record, i) => {
    const title = record.payload?.document?.title?.trim()
    if (title) return title
    if (record.observed_at) return `Layout of ${formatDay(record.observed_at, record.observed_at_precision)}`
    return `Layout ${i + 1}`
  })
  const seen = new Map<string, number>()
  base.forEach((label) => seen.set(label, (seen.get(label) ?? 0) + 1))
  const next = new Map<string, number>()
  return base.map((label) => {
    if ((seen.get(label) ?? 0) < 2) return label
    const n = (next.get(label) ?? 0) + 1
    next.set(label, n)
    return `${label} (${n})`
  })
}

export type ColouredBar = { diameter_mm: number; layout: number }

/** A bar the viewer can draw: a centreline of two points or more and a diameter. */
export type DrawableBar = { diameter_mm: number; points: number[][] }

export function isDrawableBar(bar: DrawableBar): boolean {
  return Array.isArray(bar.points) && bar.points.length >= 2 && bar.diameter_mm > 0
}

export type LayoutRecord<B extends DrawableBar = DrawableBar> = RecordLike & {
  identity_id?: string
  status?: string | null
  superseded_by?: string | null
  position?: { snapshot_id?: string | null } | null
  payload?: { bars?: B[]; document?: { title?: string | null } | null } | null
}

/**
 * The layouts of one snapshot and their bars (RL1, 0.6.3.1): every record that
 * is positioned on the snapshot and has a drawable bar is one layout, in the
 * order given, and every bar of every layout is drawn, each with the index of
 * its layout. Two layouts on one piece are two cards and two sets of bars.
 */
export function layoutsOnSnapshot<B extends DrawableBar>(
  records: LayoutRecord<B>[],
  snapshotId: string,
): { bars: (B & { layout: number })[]; layouts: BarLayout[] } {
  const here = records
    .filter((record) => record.position?.snapshot_id === snapshotId)
    .filter((record) => (record.payload?.bars ?? []).some(isDrawableBar))
  const labels = layoutLabels(here)
  const bars = here.flatMap((record, layout) =>
    (record.payload?.bars ?? []).filter(isDrawableBar).map((bar) => ({ ...bar, layout })))
  const layouts = here.map((record, layout) => ({
    id: String(record._id ?? layout),
    label: labels[layout],
    count: bars.filter((bar) => bar.layout === layout).length,
  }))
  return { bars, layouts }
}

/** The status a legend names: draft, pending, rejected, withdrawn or superseded; null for a current published record. */
export function layoutStatusText(record: { status?: string | null; superseded_by?: string | null }): string | null {
  if (record.superseded_by) return 'superseded'
  if (record.status && record.status !== 'published') return record.status
  return null
}

export type PickedProblem = 'other_version' | 'no_bars'

/**
 * The published layouts and, in addition, one record the link names (8.178,
 * `?layout=`), whatever its status: appended after the published ones, not
 * twice when it is one of them, and only when it is positioned on the version
 * shown (its bars are in the stored coordinates of that version). `picked` is
 * the index of its layout, `problem` says why it is not drawn.
 */
export function layoutsWithPicked<B extends DrawableBar>(
  published: LayoutRecord<B>[],
  pickedRecord: LayoutRecord<B> | null,
  snapshotId: string,
): {
  bars: (B & { layout: number })[]
  layouts: BarLayout[]
  picked: number | null
  problem: PickedProblem | null
} {
  if (!pickedRecord) return { ...layoutsOnSnapshot(published, snapshotId), picked: null, problem: null }
  const id = String(pickedRecord._id ?? '')
  const problem: PickedProblem | null =
    pickedRecord.position?.snapshot_id !== snapshotId ? 'other_version'
      : !(pickedRecord.payload?.bars ?? []).some(isDrawableBar) ? 'no_bars'
        : null
  const listed = published.some((record) => String(record._id ?? '') === id)
  const records = problem || listed ? published : [...published, pickedRecord]
  const { bars, layouts } = layoutsOnSnapshot(records, snapshotId)
  const picked = problem ? null : layouts.findIndex((layout) => layout.id === id)
  if (picked === null || picked < 0) return { bars, layouts, picked: null, problem }
  return {
    bars,
    layouts: layouts.map((layout, i) =>
      i === picked ? { ...layout, status: layoutStatusText(pickedRecord), picked: true } : layout),
    picked,
    problem,
  }
}

/** "Show in viewer": the page of the piece on the version of the layout, with the layout opened; null when there is nothing to draw. */
export function layoutViewerHref(record: LayoutRecord): string | null {
  const snapshotId = record.position?.snapshot_id
  if (!record._id || !record.identity_id || !snapshotId) return null
  if (!(record.payload?.bars ?? []).some(isDrawableBar)) return null
  const query = new URLSearchParams({ snapshot: snapshotId, layout: String(record._id) })
  return `/components/${encodeURIComponent(record.identity_id)}?${query}#component-viewer`
}

/** The colour of a bar, or null for the steel material. */
export function barColour(
  mode: BarColourMode,
  bar: ColouredBar,
  range: { min: number; max: number },
): string | null {
  if (mode === 'layout') return layoutColour(bar.layout)
  if (mode === 'diameter') return diameterColour(bar.diameter_mm, range)
  return null
}

export type BarLegend =
  | { kind: 'layout'; items: { id: string; colour: string; label: string; count: number; status?: string | null; picked?: boolean }[] }
  | { kind: 'diameter'; min: number; max: number; stops: string[] }

export function barLegend(
  mode: BarColourMode,
  layouts: BarLayout[],
  bars: { diameter_mm: number; layout?: number }[],
  /** the index of the layout opened by `?layout=`: the diameter scale spans its bars only */
  picked: number | null = null,
): BarLegend | null {
  if (mode === 'layout') {
    return { kind: 'layout', items: layouts.map((l, i) => ({
        id: l.id, colour: layoutColour(i), label: l.label, count: l.count, status: l.status, picked: l.picked })) }
  }
  if (mode === 'diameter') {
    const { min, max } = diameterRange(scaleBars(bars, picked))
    return { kind: 'diameter', min, max, stops: [0, 0.25, 0.5, 0.75, 1].map(rampColour) }
  }
  return null
}
