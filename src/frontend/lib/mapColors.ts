/**
 * Colour by a field on the component map (plan P11 stage 2, decision 8.118
 * C-2): dataset, shape class, material or circulation (in place or not),
 * with a legend. Pure: the page passes the labels.
 */
import { SHAPE_CLASS_LABELS, vocabLabel } from '@/generated/Vocab'

export type ColorBy = 'dataset' | 'shape_class' | 'material' | 'circulation'

export const COLOR_BY_OPTIONS: { value: ColorBy; label: string }[] = [
  { value: 'shape_class', label: 'Shape class' },
  { value: 'dataset', label: 'Dataset' },
  { value: 'material', label: 'Material' },
  { value: 'circulation', label: 'In place or not' },
]

/** Distinguishable on a light and on a dark ground; the CI blue and magenta first. */
export const PALETTE = [
  '#2563eb', // blue
  '#d6146f', // magenta
  '#16a34a', // green
  '#f59e0b', // amber
  '#7c3aed', // violet
  '#0891b2', // cyan
  '#dc2626', // red
  '#65a30d', // lime
  '#c2410c', // orange
  '#4b5563', // grey
]
/** Everything after the palette and the points without a value. */
export const OTHER_COLOR = '#9ca3af'
const NONE_KEY = ''

type PointLike = {
  dataset?: string | null
  material?: string | null
  shape_class?: string | null
  in_place?: boolean | null
}

export function colorKey(point: PointLike, by: ColorBy): string {
  switch (by) {
    case 'dataset':
      return point.dataset ?? NONE_KEY
    case 'material':
      return point.material ?? NONE_KEY
    case 'shape_class':
      return point.shape_class ?? NONE_KEY
    case 'circulation':
      return point.in_place ? 'in_place' : 'not_in_place'
  }
}

export type LegendEntry = { key: string; label: string; color: string; count: number }

export function keyLabel(
  by: ColorBy,
  key: string,
  labels: { material?: (id: string) => string } = {},
): string {
  if (key === NONE_KEY) return 'Not stated'
  switch (by) {
    case 'shape_class':
      return vocabLabel(SHAPE_CLASS_LABELS, key)
    case 'material':
      return labels.material ? labels.material(key) : key
    case 'circulation':
      return key === 'in_place' ? 'In place' : 'Not in place'
    default:
      return key
  }
}

/**
 * The legend of a colouring, the most frequent value first: each of the first
 * ten values has its own colour, the rest share one ("Other"); points without
 * a value are "Not stated". Circulation has two fixed colours.
 */
export function legendOf(
  points: PointLike[],
  by: ColorBy,
  labels: { material?: (id: string) => string } = {},
): LegendEntry[] {
  const counts = new Map<string, number>()
  for (const p of points) {
    const key = colorKey(p, by)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  if (by === 'circulation') {
    return ['in_place', 'not_in_place']
      .filter((key) => counts.has(key))
      .map((key) => ({
        key,
        label: keyLabel(by, key),
        color: key === 'in_place' ? PALETTE[0] : PALETTE[3],
        count: counts.get(key) ?? 0,
      }))
  }
  const ordered = [...counts.entries()]
    .filter(([key]) => key !== NONE_KEY)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
  const entries: LegendEntry[] = ordered.slice(0, PALETTE.length).map(([key, count], index) => ({
    key,
    label: keyLabel(by, key, labels),
    color: PALETTE[index],
    count,
  }))
  const rest = ordered.slice(PALETTE.length).reduce((sum, [, count]) => sum + count, 0)
  if (rest > 0) entries.push({ key: '__other__', label: 'Other', color: OTHER_COLOR, count: rest })
  if (counts.has(NONE_KEY)) {
    entries.push({ key: NONE_KEY, label: 'Not stated', color: OTHER_COLOR, count: counts.get(NONE_KEY) ?? 0 })
  }
  return entries
}

/** The colour of each point id for a colouring. */
export function colorMap(
  points: (PointLike & { id: string })[],
  by: ColorBy,
): Map<string, string> {
  const legend = legendOf(points, by)
  const byKey = new Map(legend.map((entry) => [entry.key, entry.color]))
  const out = new Map<string, string>()
  for (const p of points) {
    out.set(p.id, byKey.get(colorKey(p, by)) ?? OTHER_COLOR)
  }
  return out
}
