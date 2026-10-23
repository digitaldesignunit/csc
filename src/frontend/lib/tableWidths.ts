/**
 * Column widths of the Browse table (decisions 8.118 Q6, 8.169, 8.170).
 *
 * Every column has a minimum width in px (what its header and its cell need
 * whole) and a weight (how the room above the minimums is shared). The table is
 * never narrower than the sum of the minimums of the columns it shows (the base
 * set, Match, Distance and the columns picked in the column menu): below that
 * its frame scrolls sideways and the page does not; above it, every column has
 * its minimum plus its weighted share of what is left. Columns without a weight
 * (the actions, the optional columns) keep their minimum.
 *
 * Pure: the table component measures its frame and calls these.
 */

export type ColumnSize = {
  /** The narrowest the column may be, px. */
  minPx: number
  /** Share of the room above the minimums; 0 = stays at its minimum. */
  weight: number
}

/**
 * The columns of Browse by id. Minimums are what the header (with its sort
 * arrow and, while sorted, its reset cross) and the cell need: measured text
 * widths plus the 12 px padding on each side. The weights are the shares the
 * columns had as percentages before.
 */
export const BROWSE_COLUMN_SIZES: Record<string, ColumnSize> = {
  name: { minPx: 150, weight: 23 },
  original_function: { minPx: 106, weight: 11 },
  material: { minPx: 112, weight: 15 },
  dataset: { minPx: 112, weight: 15 },
  size: { minPx: 114, weight: 12 },
  // Distance: the header with its reset cross is 110 px wide
  distance: { minPx: 144, weight: 11 },
  // Match: "30 % waste" over "0.0021 m3 per piece" (which may wrap)
  fit: { minPx: 110, weight: 14 },
  shape_class: { minPx: 126, weight: 9.5 },
  status: { minPx: 100, weight: 10 },
  actions: { minPx: 44, weight: 0 },
  // the optional columns of the column menu: their own width, no share
  _id: { minPx: 300, weight: 0 },
  catalog_number: { minPx: 152, weight: 0 },
  effective_from: { minPx: 130, weight: 0 },
  color: { minPx: 140, weight: 0 },
  fragment: { minPx: 100, weight: 0 },
  complexity: { minPx: 124, weight: 0 },
  location: { minPx: 220, weight: 0 },
  created: { minPx: 170, weight: 0 },
  lastmodified: { minPx: 170, weight: 0 },
}

/** The size of a column; one that is not listed keeps a safe minimum. */
export function sizeOf(id: string): ColumnSize {
  return BROWSE_COLUMN_SIZES[id] ?? { minPx: 120, weight: 0 }
}

/** The narrowest the table may be for these columns (px). */
export function minTableWidth(ids: readonly string[]): number {
  return ids.reduce((sum, id) => sum + sizeOf(id).minPx, 0)
}

/**
 * The width of each column for a frame `frame` px wide (null = not measured
 * yet). Every column is at least its minimum; the room above the sum of the
 * minimums goes to the columns by weight, so the table fills the frame exactly;
 * below the sum the widths are the minimums and the table is wider than the
 * frame. Whole pixels: the remainder goes to the heaviest column.
 */
export function columnWidths(
  frame: number | null,
  ids: readonly string[],
): { widths: number[]; total: number; scrolls: boolean } | null {
  if (frame === null || !Number.isFinite(frame) || frame <= 0) return null
  const sizes = ids.map(sizeOf)
  const minTotal = sizes.reduce((sum, s) => sum + s.minPx, 0)
  const weightTotal = sizes.reduce((sum, s) => sum + s.weight, 0)
  const extra = Math.max(0, Math.floor(frame) - minTotal)
  if (extra === 0 || weightTotal === 0) {
    return { widths: sizes.map((s) => s.minPx), total: minTotal, scrolls: minTotal > frame }
  }
  const widths = sizes.map((s) => s.minPx + Math.floor((extra * s.weight) / weightTotal))
  const left = Math.floor(frame) - widths.reduce((sum, w) => sum + w, 0)
  if (left > 0) {
    let heaviest = 0
    sizes.forEach((s, i) => {
      if (s.weight > sizes[heaviest].weight) heaviest = i
    })
    widths[heaviest] += left
  }
  return { widths, total: widths.reduce((sum, w) => sum + w, 0), scrolls: false }
}

/** Percent widths for the first paint, before the frame is measured: the
 *  weighted columns share 100 %, the others keep their minimum in px. */
export function firstPaintWidths(ids: readonly string[]): string[] {
  const sizes = ids.map(sizeOf)
  const weightTotal = sizes.reduce((sum, s) => sum + s.weight, 0)
  return sizes.map((s) => (s.weight > 0 && weightTotal > 0 ? `${((s.weight / weightTotal) * 100).toFixed(2)}%` : `${s.minPx}px`))
}
