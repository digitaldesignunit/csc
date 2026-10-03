/**
 * The solid and the overlay draw one geometry (decision 8.85): for a rotated
 * box, a prism along x, a tilted cylinder and a hull, the world vertices of
 * the solid equal those of the overlay faces and the stored vertices the
 * proxy's placement gives (stored mm, z up -> viewer metres, y up).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as THREE from 'three'

import type { ProxyDoc } from '@/lib/proxyOverlay'
import {
  buildProxyShape,
  isDrawableProxy,
  sceneVertices,
  solidGeometry,
} from '@/lib/proxyShape'

type Placement = ProxyDoc['placement']

const proxies: Record<string, ProxyDoc> = {
  'rotated box': {
    primitive: 'box',
    params: { size: [400, 100, 50] },
    placement: { o: [1000, 2000, 500], x: [0, 1, 0], y: [-1, 0, 0], z: [0, 0, 1] },
  },
  'prism along x': {
    primitive: 'prism',
    params: { profile: [[-50, -25], [50, -25], [50, 25], [-50, 25]], height: 300 },
    placement: { o: [-300, 40, 70], x: [0, 1, 0], y: [0, 0, 1], z: [1, 0, 0] },
  },
  'tilted cylinder': {
    primitive: 'cylinder',
    params: { radius: 80, height: 250 },
    placement: { o: [10, -20, 30], x: [0.8, 0, -0.6], y: [0, 1, 0], z: [0.6, 0, 0.8] },
  },
  hull: {
    primitive: 'hull',
    params: {
      vertices: [[-100, -80, -60], [120, -70, -50], [10, 110, -40], [0, 5, 130]],
      faces: [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]],
    },
    placement: { o: [500, 250, 120], x: [0, -1, 0], y: [1, 0, 0], z: [0, 0, 1] },
  },
}

/** Stored mm of a local vertex, then the viewer scene (x, z, -y) in metres. */
function expectedScene(placement: Placement, local: THREE.Vector3): THREE.Vector3 {
  const [ox, oy, oz] = placement.o
  const stored = new THREE.Vector3(
    ox + placement.x[0] * local.x + placement.y[0] * local.y + placement.z[0] * local.z,
    oy + placement.x[1] * local.x + placement.y[1] * local.y + placement.z[1] * local.z,
    oz + placement.x[2] * local.x + placement.y[2] * local.y + placement.z[2] * local.z,
  )
  return new THREE.Vector3(stored.x, stored.z, -stored.y).multiplyScalar(0.001)
}

function assertSame(actual: THREE.Vector3[], expected: THREE.Vector3[], what: string) {
  assert.equal(actual.length, expected.length, `${what}: vertex count`)
  actual.forEach((v, i) => {
    assert.ok(v.distanceTo(expected[i]) < 1e-9, `${what}: vertex ${i} ${v.toArray()} vs ${expected[i].toArray()}`)
  })
}

for (const [name, proxy] of Object.entries(proxies)) {
  test(`${name}: solid, overlay and the placement give the same world vertices`, () => {
    assert.ok(isDrawableProxy(proxy))
    const shape = buildProxyShape(proxy)
    assert.ok(shape, 'a shape')

    const overlay = Object.values(shape.faces).flatMap((geometry) => sceneVertices(shape, geometry))
    const solid = sceneVertices(shape, solidGeometry(shape))
    assertSame(solid, overlay, 'solid vs overlay')

    const local = Object.values(shape.faces).flatMap((geometry) => {
      const position = geometry.getAttribute('position')
      return Array.from({ length: position.count }, (_, i) => new THREE.Vector3().fromBufferAttribute(position, i))
    })
    assertSame(solid, local.map((v) => expectedScene(proxy.placement, v)), 'solid vs stored placement')
  })
}

test('the placement is applied: a rotated box is not the box of the identity placement', () => {
  const rotated = buildProxyShape(proxies['rotated box'])
  const identity = buildProxyShape({
    ...proxies['rotated box'],
    placement: { o: [0, 0, 0], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] },
  })
  assert.ok(rotated && identity)
  const box = (shape: NonNullable<typeof rotated>) => new THREE.Box3().setFromPoints(sceneVertices(shape, solidGeometry(shape)))
  const size = (b: THREE.Box3) => b.getSize(new THREE.Vector3())
  // identity: 400 along stored x; rotated a quarter turn about z: 400 along stored y (viewer -z)
  assert.ok(Math.abs(size(box(identity)).x - 0.4) < 1e-9)
  assert.ok(Math.abs(size(box(rotated)).z - 0.4) < 1e-9)
  assert.ok(Math.abs(size(box(rotated)).x - 0.1) < 1e-9)
})

test('proxies without parameters to draw give no shape', () => {
  const frame = proxies.hull.placement
  assert.equal(buildProxyShape({ primitive: 'box', params: { size: [1, 0, 3] }, placement: frame }), null)
  assert.equal(buildProxyShape({ primitive: 'cylinder', params: {}, placement: frame }), null)
  assert.equal(buildProxyShape({ primitive: 'hull', params: { vertices: [], faces: [] }, placement: frame }), null)
  assert.equal(buildProxyShape(null), null)
})
