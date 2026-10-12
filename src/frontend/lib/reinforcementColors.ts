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

export function diameterColour(diameter: number, range: { min: number; max: number }): string {
  // one diameter only: the middle of the ramp, not an arbitrary end
  if (range.max <= range.min) return rampColour(0.5)
  return rampColour((diameter - range.min) / (range.max - range.min))
}

// LAYOUTS ---------------------------------------------------------------------
export type BarLayout = { id: string; label: string; count: number }

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
  | { kind: 'layout'; items: { colour: string; label: string; count: number }[] }
  | { kind: 'diameter'; min: number; max: number; stops: string[] }

export function barLegend(
  mode: BarColourMode,
  layouts: BarLayout[],
  bars: { diameter_mm: number }[],
): BarLegend | null {
  if (mode === 'layout') {
    return { kind: 'layout', items: layouts.map((l, i) => ({ colour: layoutColour(i), label: l.label, count: l.count })) }
  }
  if (mode === 'diameter') {
    const { min, max } = diameterRange(bars)
    return { kind: 'diameter', min, max, stops: [0, 0.25, 0.5, 0.75, 1].map(rampColour) }
  }
  return null
}
