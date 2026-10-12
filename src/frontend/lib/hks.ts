/**
 * The stored heat kernel signature (decision 8.6) as a curve (level 1 of the
 * HKS in the viewer, plan 0.6): `descriptors.hks` holds `2 * HKS_TIMES`
 * floats, the mass-weighted mean over the surface for each time, then the
 * variance for each time, L2-normalised together. The times are the frozen
 * log-spaced grid of the backend (`apps/descriptors/hks.py`), in area-
 * normalised units.
 */
/**
 * Whether the HKS is shown in the web app (the descriptors card on the
 * component page, a basis of the component map). Off: the pooled curve carries
 * little meaning, since the mean half is the heat trace over the area, nearly
 * shape-independent after area normalisation, and the L2 normalisation lets it
 * dominate. The code stays; the API and the cache job are unchanged.
 */
export const HKS_VISIBLE = false

export const HKS_TIMES = 16
export const HKS_T_MIN = 5.187876e-03
export const HKS_T_MAX = 3.454702e-01

/** The time of each step: `HKS_TIMES` values, log-spaced. */
export function hksTimes(): number[] {
  const lo = Math.log10(HKS_T_MIN)
  const hi = Math.log10(HKS_T_MAX)
  return Array.from({ length: HKS_TIMES }, (_, i) => 10 ** (lo + ((hi - lo) * i) / (HKS_TIMES - 1)))
}

export type HksCurves = { mean: number[]; variance: number[] }

/** The mean and the variance curve of a snapshot's descriptors, or null when it has none. */
export function parseHks(descriptors: unknown): HksCurves | null {
  const raw = (descriptors as { hks?: unknown } | null | undefined)?.hks
  if (!Array.isArray(raw) || raw.length !== 2 * HKS_TIMES) return null
  const values = raw.map((v) => (typeof v === 'number' ? v : Number.NaN))
  if (!values.every(Number.isFinite)) return null
  return { mean: values.slice(0, HKS_TIMES), variance: values.slice(HKS_TIMES) }
}

export type ChartPoint = { x: number; y: number; t: number; value: number }

/**
 * The points of a curve in a `width` x `height` box with `pad` around it:
 * the steps evenly along x (the times are log-spaced), the values between
 * their smallest and largest (a flat curve sits in the middle).
 */
export function chartPoints(
  values: number[],
  width: number,
  height: number,
  pad = 6,
): { points: ChartPoint[]; min: number; max: number } {
  const times = hksTimes()
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min
  const points = values.map((value, i) => ({
    x: pad + ((width - 2 * pad) * i) / Math.max(1, values.length - 1),
    y: span > 0 ? height - pad - ((height - 2 * pad) * (value - min)) / span : height / 2,
    t: times[i] ?? Number.NaN,
    value,
  }))
  return { points, min, max }
}

/** `M x y L x y ...` for the points of a curve. */
export function linePath(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
}
