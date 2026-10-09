/**
 * Grid and edge geometry for positions picked on the viewer (decision
 * 8.43). Everything is in the stored coordinates of a snapshot (mm, Rhino
 * Z-up), never in the canonical frame. Pure functions: no three.js here.
 */

export type Vec3 = [number, number, number]

export type GridSpec = {
  origin: Vec3
  u: Vec3
  v: Vec3
  rows: number
  cols: number
  spacing_mm: number
}

export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
export const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
export const scale = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k]
export const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
export const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
]
export const length = (a: Vec3): number => Math.hypot(a[0], a[1], a[2])

export function unit(a: Vec3): Vec3 | null {
  const l = length(a)
  return l > 1e-12 ? scale(a, 1 / l) : null
}

/** `v` with its component along `n` removed, as a unit vector (null if parallel). */
export function inPlane(v: Vec3, n: Vec3): Vec3 | null {
  return unit(sub(v, scale(n, dot(v, n))))
}

export const AXES: { id: 'x' | 'y' | 'z'; label: string; vec: Vec3 }[] = [
  { id: 'x', label: 'X', vec: [1, 0, 0] },
  { id: 'y', label: 'Y', vec: [0, 1, 0] },
  { id: 'z', label: 'Z', vec: [0, 0, 1] },
]

/**
 * The in-plane direction u that follows the stored axis best (the axis most
 * parallel to the face), and v = n x u. Gives the same defaults every time
 * for the same face.
 */
export function defaultDirections(normal: Vec3): { u: Vec3; v: Vec3 } | null {
  const n = unit(normal)
  if (!n) return null
  const candidates = AXES
    .map((axis) => ({ axis, projected: inPlane(axis.vec, n) }))
    .filter((c): c is { axis: (typeof AXES)[number]; projected: Vec3 } => c.projected !== null)
    // most in-plane first: the axis that lies along the face
    .sort((a, b) => Math.abs(dot(a.axis.vec, n)) - Math.abs(dot(b.axis.vec, n)))
  const first = candidates[0]
  if (!first) return null
  const u = first.projected
  return { u, v: unit(cross(n, u)) ?? u }
}

/** The grid points row by row (reading i belongs to point i), in mm. */
export function gridPoints(grid: GridSpec): Vec3[] {
  const points: Vec3[] = []
  for (let r = 0; r < grid.rows; r += 1) {
    for (let c = 0; c < grid.cols; c += 1) {
      points.push(
        add(
          add(grid.origin, scale(grid.u, c * grid.spacing_mm)),
          scale(grid.v, r * grid.spacing_mm),
        ),
      )
    }
  }
  return points
}

export function gridCentre(grid: GridSpec): Vec3 {
  return add(
    add(grid.origin, scale(grid.u, ((grid.cols - 1) / 2) * grid.spacing_mm)),
    scale(grid.v, ((grid.rows - 1) / 2) * grid.spacing_mm),
  )
}

/** Origin that puts the grid's centre on `centre`. */
export function originForCentre(grid: Omit<GridSpec, 'origin'>, centre: Vec3): Vec3 {
  return sub(
    centre,
    add(
      scale(grid.u, ((grid.cols - 1) / 2) * grid.spacing_mm),
      scale(grid.v, ((grid.rows - 1) / 2) * grid.spacing_mm),
    ),
  )
}

/** Distance from `p` to the segment `a`-`b`. */
export function distanceToSegment(p: Vec3, a: Vec3, b: Vec3): number {
  const ab = sub(b, a)
  const len2 = dot(ab, ab)
  if (len2 < 1e-18) return length(sub(p, a))
  const t = Math.max(0, Math.min(1, dot(sub(p, a), ab) / len2))
  return length(sub(p, add(a, scale(ab, t))))
}

/** Boundary edges of a face patch: segment pairs of vertex positions. */
export type Edge = [Vec3, Vec3]

/** Smallest distance from `p` to any of the edges (Infinity for none). */
export function distanceToEdges(p: Vec3, edges: Edge[]): number {
  let best = Infinity
  for (const [a, b] of edges) {
    const d = distanceToSegment(p, a, b)
    if (d < best) best = d
  }
  return best
}

/**
 * The patch edge distance for each point and the indices closer to an edge
 * than `minEdgeMm` (the viewer's warning, A.1 `min_edge_distance_mm`). A
 * point outside the patch's outline counts as on an edge.
 */
export function edgeWarnings(
  points: Vec3[],
  edges: Edge[] | null,
  minEdgeMm: number,
): { distances: (number | null)[]; tooClose: number[] } {
  if (!edges || edges.length === 0) {
    return { distances: points.map(() => null), tooClose: [] }
  }
  const distances = points.map((p) => distanceToEdges(p, edges))
  const tooClose = distances.flatMap((d, i) => (d !== null && d < minEdgeMm ? [i] : []))
  return { distances, tooClose }
}

/** Spacing check of the backend: `spacing_mm >= min_spacing_mm`. */
export function spacingProblem(spacingMm: number, minSpacingMm: number): string | null {
  return spacingMm >= minSpacingMm
    ? null
    : `Spacing must be at least ${minSpacingMm} mm (the minimum distance between impacts).`
}

export function roundVec(v: Vec3, digits = 3): Vec3 {
  const k = 10 ** digits
  return [Math.round(v[0] * k) / k, Math.round(v[1] * k) / k, Math.round(v[2] * k) / k]
}

export function parseVec(text: string): Vec3 | null {
  const parts = text.trim().split(/[\s,;]+/).filter(Boolean).map(Number)
  return parts.length === 3 && parts.every(Number.isFinite) ? [parts[0], parts[1], parts[2]] : null
}
