/**
 * Proxy faces with UV coordinates and deviation-map textures (data model
 * spec appendix B). Everything is built in the proxy's **local** axes (mm);
 * the caller places the group with the proxy's `placement` and the usual
 * Rhino-to-three conversion.
 *
 * Face ids, UV conventions and the map layout mirror
 * `apps/catalog/proxies/` in the backend: column from `u`, row from `v`,
 * row 0 at `v` minimum (a `DataTexture` row 0 is also at `v = 0`).
 */

import * as THREE from 'three'
import type { Rgb16Image } from '@/lib/png16'

export type ProxyDoc = {
  primitive: 'box' | 'prism' | 'cylinder' | 'hull'
  params: Record<string, unknown>
  placement: { o: number[]; x: number[]; y: number[]; z: number[] }
}

export type MapChannel = 'distance' | 'normal_deviation' | 'occupancy'

export type FaceMap = {
  image: Rgb16Image
  scaleMm: number
  offsetMm: number
}

const CYLINDER_SEGMENTS = 64
const CAP_RINGS = 6

type Vec2 = [number, number]

/** Local -> stored (Rhino) coordinates, as a matrix of the proxy group. */
export function placementMatrix(placement: ProxyDoc['placement']): THREE.Matrix4 {
  const [ox, oy, oz] = placement.o
  const [xx, xy, xz] = placement.x
  const [yx, yy, yz] = placement.y
  const [zx, zy, zz] = placement.z
  return new THREE.Matrix4().set(
    xx, yx, zx, ox,
    xy, yy, zy, oy,
    xz, yz, zz, oz,
    0, 0, 0, 1,
  )
}

class FaceBuilder {
  positions: number[] = []
  uvs: number[] = []

  triangle(a: number[], b: number[], c: number[], ua: Vec2, ub: Vec2, uc: Vec2) {
    this.positions.push(...a, ...b, ...c)
    this.uvs.push(...ua, ...ub, ...uc)
  }

  /** A quad ``p00 p10 p11 p01`` with the unit square as UV. */
  quad(p00: number[], p10: number[], p11: number[], p01: number[]) {
    this.triangle(p00, p10, p11, [0, 0], [1, 0], [1, 1])
    this.triangle(p00, p11, p01, [0, 0], [1, 1], [0, 1])
  }

  geometry(): THREE.BufferGeometry {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(this.positions, 3))
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute(this.uvs, 2))
    geometry.computeVertexNormals()
    return geometry
  }
}

/** A grid of ``nu x nv`` cells over ``at(u, v)``, u and v in 0..1. */
function grid(builder: FaceBuilder, nu: number, nv: number, at: (u: number, v: number) => number[]) {
  for (let i = 0; i < nu; i += 1) {
    for (let j = 0; j < nv; j += 1) {
      const u0 = i / nu
      const u1 = (i + 1) / nu
      const v0 = j / nv
      const v1 = (j + 1) / nv
      builder.triangle(at(u0, v0), at(u1, v0), at(u1, v1), [u0, v0], [u1, v0], [u1, v1])
      builder.triangle(at(u0, v0), at(u1, v1), at(u0, v1), [u0, v0], [u1, v1], [u0, v1])
    }
  }
}

function boxFaces(params: { size: number[] }): Record<string, THREE.BufferGeometry> {
  const [hx, hy, hz] = params.size.map((v) => v / 2)
  const faces: Record<string, THREE.BufferGeometry> = {}
  const make = (id: string, at: (u: number, v: number) => number[]) => {
    const b = new FaceBuilder()
    b.quad(at(0, 0), at(1, 0), at(1, 1), at(0, 1))
    faces[id] = b.geometry()
  }
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t
  for (const sign of [1, -1]) {
    const s = sign > 0 ? '+' : '-'
    make(`${s}x`, (u, v) => [sign * hx, lerp(-hy, hy, u), lerp(-hz, hz, v)])
    make(`${s}y`, (u, v) => [lerp(-hx, hx, u), sign * hy, lerp(-hz, hz, v)])
    make(`${s}z`, (u, v) => [lerp(-hx, hx, u), lerp(-hy, hy, v), sign * hz])
  }
  return faces
}

function ringOf(profile: number[][]): Vec2[] {
  let ring = profile.map((p) => [p[0], p[1]] as Vec2)
  const first = ring[0]
  const last = ring[ring.length - 1]
  if (ring.length > 1 && first[0] === last[0] && first[1] === last[1]) ring = ring.slice(0, -1)
  let area = 0
  ring.forEach((p, i) => {
    const q = ring[(i + 1) % ring.length]
    area += p[0] * q[1] - q[0] * p[1]
  })
  return area < 0 ? [...ring].reverse() : ring
}

function prismFaces(params: {
  profile: number[][]
  holes?: number[][][] | null
  height: number
}): Record<string, THREE.BufferGeometry> {
  const ring = ringOf(params.profile)
  const half = params.height / 2
  const xs = ring.map((p) => p[0])
  const ys = ring.map((p) => p[1])
  const [u0, u1] = [Math.min(...xs), Math.max(...xs)]
  const [v0, v1] = [Math.min(...ys), Math.max(...ys)]
  const faces: Record<string, THREE.BufferGeometry> = {}

  const contour = ring.map((p) => new THREE.Vector2(p[0], p[1]))
  const holes = (params.holes ?? []).map((h) => ringOf(h).map((p) => new THREE.Vector2(p[0], p[1])))
  const triangles = THREE.ShapeUtils.triangulateShape(contour, holes)
  const points = [...contour, ...holes.flat()]
  for (const [id, z, flip] of [['top', half, false], ['bottom', -half, true]] as const) {
    const b = new FaceBuilder()
    for (const [i, j, k] of triangles) {
      const idx = flip ? [i, k, j] : [i, j, k]
      const p = idx.map((n) => points[n])
      const uv = (q: THREE.Vector2): Vec2 => [(q.x - u0) / (u1 - u0 || 1), (q.y - v0) / (v1 - v0 || 1)]
      b.triangle(
        [p[0].x, p[0].y, z], [p[1].x, p[1].y, z], [p[2].x, p[2].y, z],
        uv(p[0]), uv(p[1]), uv(p[2]),
      )
    }
    faces[id] = b.geometry()
  }
  ring.forEach((a, k) => {
    const b2 = ring[(k + 1) % ring.length]
    const b = new FaceBuilder()
    b.quad([a[0], a[1], -half], [b2[0], b2[1], -half], [b2[0], b2[1], half], [a[0], a[1], half])
    faces[`side_${k}`] = b.geometry()
  })
  return faces
}

function cylinderFaces(params: { radius: number; height: number }): Record<string, THREE.BufferGeometry> {
  const { radius, height } = params
  const half = height / 2
  const faces: Record<string, THREE.BufferGeometry> = {}
  for (const [id, z] of [['top', half], ['bottom', -half]] as const) {
    const b = new FaceBuilder()
    grid(b, CYLINDER_SEGMENTS, CAP_RINGS, (u, v) => {
      const theta = u * 2 * Math.PI
      return [radius * v * Math.cos(theta), radius * v * Math.sin(theta), z]
    })
    faces[id] = b.geometry()
  }
  const b = new FaceBuilder()
  grid(b, CYLINDER_SEGMENTS, 1, (u, v) => {
    const theta = u * 2 * Math.PI
    return [radius * Math.cos(theta), radius * Math.sin(theta), -half + v * height]
  })
  faces.lateral = b.geometry()
  return faces
}

function hullFaces(params: { vertices: number[][]; faces: number[][] }): Record<string, THREE.BufferGeometry> {
  const b = new FaceBuilder()
  const direction = (p: number[]): Vec2 => {
    const r = Math.hypot(p[0], p[1], p[2]) || 1
    const theta = (Math.atan2(p[1], p[0]) + 2 * Math.PI) % (2 * Math.PI)
    return [theta / (2 * Math.PI), Math.acos(Math.max(-1, Math.min(1, p[2] / r))) / Math.PI]
  }
  for (const [i, j, k] of params.faces) {
    const p = [params.vertices[i], params.vertices[j], params.vertices[k]]
    const uv = p.map(direction)
    if (Math.max(...uv.map((q) => q[0])) - Math.min(...uv.map((q) => q[0])) > 0.5) {
      uv.forEach((q) => { if (q[0] < 0.5) q[0] += 1 })    // across the seam (wrapS repeats)
    }
    b.triangle(p[0], p[1], p[2], uv[0], uv[1], uv[2])
  }
  return { sphere: b.geometry() }
}

/** The faces of a proxy by face id, in local axes (mm). */
export function proxyFaceGeometries(proxy: ProxyDoc): Record<string, THREE.BufferGeometry> {
  const params = proxy.params as never
  switch (proxy.primitive) {
    case 'box': return boxFaces(params)
    case 'prism': return prismFaces(params)
    case 'cylinder': return cylinderFaces(params)
    case 'hull': return hullFaces(params)
    default: return {}
  }
}

// COLOUR ----------------------------------------------------------------------
export type ChannelScale = { label: string; unit: string; range: number }

function diverging(t: number): [number, number, number] {
  // t in -1..1: blue (inside) -- white -- red (outside)
  const a = Math.min(1, Math.abs(t))
  const white = 255
  return t < 0
    ? [white * (1 - a) + 40 * a, white * (1 - a) + 90 * a, white * (1 - a) + 200 * a]
    : [white * (1 - a) + 205 * a, white * (1 - a) + 50 * a, white * (1 - a) + 40 * a]
}

function sequential(t: number): [number, number, number] {
  const a = Math.min(1, Math.max(0, t))
  return [255 - 150 * a, 245 - 190 * a, 220 - 200 * a]
}

/** The colour range of a channel over all maps of a proxy: the 95th
 *  percentile of |distance| (so one outlier does not wash the rest out). */
export function channelRange(maps: Record<string, FaceMap>, channel: MapChannel): number {
  if (channel === 'normal_deviation') return 45
  const values: number[] = []
  for (const { image, scaleMm, offsetMm } of Object.values(maps)) {
    for (let i = 0; i < image.width * image.height; i += 1) {
      if (image.data[i * 3 + 2] === 0) continue
      values.push(
        channel === 'distance'
          ? Math.abs(image.data[i * 3] * scaleMm + offsetMm)
          : image.data[i * 3 + 2],
      )
    }
  }
  if (values.length === 0) return 1
  values.sort((a, b) => a - b)
  const p95 = values[Math.floor(0.95 * (values.length - 1))]
  return channel === 'distance' ? Math.max(0.5, p95) : Math.max(1, p95)
}

export function faceTexture(map: FaceMap, channel: MapChannel, range: number): THREE.DataTexture {
  const { image, scaleMm, offsetMm } = map
  const rgba = new Uint8Array(image.width * image.height * 4)
  for (let i = 0; i < image.width * image.height; i += 1) {
    const occupancy = image.data[i * 3 + 2]
    if (occupancy === 0) continue                                  // transparent
    let colour: [number, number, number]
    if (channel === 'distance') {
      colour = diverging((image.data[i * 3] * scaleMm + offsetMm) / range)
    } else if (channel === 'normal_deviation') {
      colour = sequential((image.data[i * 3 + 1] * 0.01) / range)
    } else {
      colour = sequential(Math.log1p(occupancy) / Math.log1p(range))
    }
    rgba.set([...colour, 255], i * 4)
  }
  const texture = new THREE.DataTexture(rgba, image.width, image.height, THREE.RGBAFormat)
  texture.magFilter = THREE.NearestFilter
  texture.minFilter = THREE.NearestFilter
  texture.wrapS = THREE.RepeatWrapping
  texture.needsUpdate = true
  return texture
}
