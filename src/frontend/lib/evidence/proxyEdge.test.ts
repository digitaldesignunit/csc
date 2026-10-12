import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'

import { proxyEdgeDistances, proxyEdgeModel, proxyEdgeWarnings } from '@/lib/evidence/proxyEdge'
import { facePatchEdges } from '@/lib/evidence/pick'
import { distanceToEdges, type Edge } from '@/lib/evidence/grid'
import type { ProxyDoc } from '@/lib/proxyOverlay'

const identity = { o: [0, 0, 0], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }

const box = (size: number[], placement = identity): ProxyDoc => ({
  primitive: 'box', params: { size }, placement,
})

const near = (a: number, b: number, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`)

test('a point on the middle of a box face is half the short side from its edge', () => {
  const model = proxyEdgeModel(box([600, 400, 200]))
  assert.ok(model)
  // top face z = +100, 600 x 400: the middle is 200 mm from the long edges
  near(proxyEdgeDistances(model, [[0, 0, 100]])[0], 200)
  // 50 mm off the middle along x
  near(proxyEdgeDistances(model, [[50, 0, 100]])[0], 200)
  // 30 mm from a short edge
  near(proxyEdgeDistances(model, [[270, 0, 100]])[0], 30)
})

test('a point above or below the proxy is projected onto the nearest face', () => {
  const model = proxyEdgeModel(box([600, 400, 200]))
  assert.ok(model)
  // a scan bump 3 mm over the top face and 20 mm from a short edge
  near(proxyEdgeDistances(model, [[280, 0, 103]])[0], 20)
  // a scan point 4 mm inside the proxy
  near(proxyEdgeDistances(model, [[280, 0, 96]])[0], 20)
})

test('a point beside the face projects onto its rim: distance 0', () => {
  const model = proxyEdgeModel(box([600, 400, 200]))
  assert.ok(model)
  near(proxyEdgeDistances(model, [[500, 0, 100]])[0], 0, 1e-3)
})

test('the placement turns and moves the faces', () => {
  const placed = box([600, 400, 200], { o: [1000, 0, 0], x: [0, 1, 0], y: [-1, 0, 0], z: [0, 0, 1] })
  const model = proxyEdgeModel(placed)
  assert.ok(model)
  // local x runs along stored y: the 600 side is stored y; the 400 side stored x
  near(proxyEdgeDistances(model, [[1000, 0, 100]])[0], 200)
  near(proxyEdgeDistances(model, [[1000, 270, 100]])[0], 30)
})

test('warnings list the points closer than the minimum', () => {
  const model = proxyEdgeModel(box([600, 400, 200]))
  assert.ok(model)
  const result = proxyEdgeWarnings(model, [[0, 0, 100], [270, 0, 100], [0, 190, 100]], 25)
  assert.deepEqual(result.tooClose, [2])
})

test('a prism or cylinder proxy is measured to its rim', () => {
  const cylinder = proxyEdgeModel({
    primitive: 'cylinder', params: { radius: 100, height: 300 }, placement: identity,
  })
  assert.ok(cylinder)
  near(proxyEdgeDistances(cylinder, [[0, 0, 150]])[0], 100, 0.5)
  near(proxyEdgeDistances(cylinder, [[70, 0, 150]])[0], 30, 0.5)
  // on the lateral face: 40 mm from the top rim
  near(proxyEdgeDistances(cylinder, [[100, 0, 110]])[0], 40, 0.5)
})

test('a hull merges coplanar triangles into one facet', () => {
  // a cube of 100 mm as a hull: 12 triangles, 6 facets
  const vertices = [
    [-50, -50, -50], [50, -50, -50], [50, 50, -50], [-50, 50, -50],
    [-50, -50, 50], [50, -50, 50], [50, 50, 50], [-50, 50, 50],
  ]
  const faces = [
    [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
    [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
    [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
  ]
  const model = proxyEdgeModel({ primitive: 'hull', params: { vertices, faces }, placement: identity })
  assert.ok(model)
  assert.equal(model.patches.length, 6)
  // the diagonal of a facet is not an edge: the middle is 50 mm from the rim
  near(proxyEdgeDistances(model, [[0, 0, 50]])[0], 50)
})

test('a proxy without parameters gives no model', () => {
  assert.equal(proxyEdgeModel(null), null)
  assert.equal(proxyEdgeModel({ primitive: 'box', params: {}, placement: identity }), null)
})

// MESH FALLBACK ---------------------------------------------------------------
/** A plate in the X-Z plane (scene metres), n x n cells of `cell`, y = height(i, j). */
function plate(n: number, cell: number, height: (i: number, j: number) => number, skip: (i: number, j: number) => boolean = () => false) {
  const positions: number[] = []
  for (let j = 0; j <= n; j += 1) {
    for (let i = 0; i <= n; i += 1) positions.push(i * cell, height(i, j), j * cell)
  }
  const indices: number[] = []
  for (let j = 0; j < n; j += 1) {
    for (let i = 0; i < n; i += 1) {
      if (skip(i, j)) continue
      const a = j * (n + 1) + i
      const b = a + 1
      const c = a + n + 1
      const d = c + 1
      indices.push(a, c, b, b, c, d)
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  const mesh = new THREE.Mesh(geometry)
  const root = new THREE.Group()
  root.add(mesh)
  root.updateMatrixWorld(true)
  return { mesh, root }
}

test('the mesh fallback ignores holes and bumps: only the outer boundary counts', () => {
  const n = 20
  const cell = 0.01 // 10 mm cells, a 200 mm plate
  // a bump of 8 mm in the middle (outside 3 mm) and a missing block
  const { mesh, root } = plate(
    n, cell,
    (i, j) => (i >= 8 && i <= 11 && j >= 8 && j <= 11 ? 0.008 : 0),
    (i, j) => i >= 3 && i <= 4 && j >= 3 && j <= 4,
  )
  const edges = facePatchEdges(mesh, 0, root) as Edge[]
  assert.ok(edges && edges.length > 0)
  // the centre of the plate is 100 mm from the outer rim; the rims of the hole
  // and of the bump are not edges
  const centre: [number, number, number] = [100, -100, 0]
  assert.ok(distanceToEdges(centre, edges) > 90, `centre at ${distanceToEdges(centre, edges)}`)
})

test('the mesh fallback follows a gently tilted, noisy face', () => {
  const n = 20
  const cell = 0.01
  // 1 mm noise and a 5 degree tilt over 200 mm: all inside 3 mm / 20 degrees
  const { mesh, root } = plate(n, cell, (i, j) => 0.0005 * ((i * 7 + j * 3) % 3) + i * cell * Math.tan(0.087))
  const edges = facePatchEdges(mesh, 0, root) as Edge[]
  assert.ok(edges)
  assert.ok(distanceToEdges([100, -100, 17], edges) > 80)
})
