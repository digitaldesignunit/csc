/**
 * Faces behind their edges (0.6.3.1): the face materials carry a polygon
 * offset, also in the faded copies of the opacity slider; the edge lines keep
 * their depth test and have no offset.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as THREE from 'three'

import {
  FACE_POLYGON_OFFSET,
  NEAR_FLOOR,
  bodyFaceMaterial,
  depthChanged,
  depthRange,
  edgeLineMaterial,
  pushFacesBack,
  sizeChanged,
} from '@/lib/viewerDepth'
import { applyOpacity, applyOpacityToObject, copyForViewer } from '@/lib/viewerOpacity'

function offsetOf(material: THREE.Material) {
  return [material.polygonOffset, material.polygonOffsetFactor, material.polygonOffsetUnits]
}

test('the offset is small and positive: faces go back, not forward', () => {
  assert.equal(FACE_POLYGON_OFFSET.polygonOffset, true)
  assert.ok(FACE_POLYGON_OFFSET.polygonOffsetFactor > 0 && FACE_POLYGON_OFFSET.polygonOffsetFactor <= 2)
  assert.ok(FACE_POLYGON_OFFSET.polygonOffsetUnits > 0 && FACE_POLYGON_OFFSET.polygonOffsetUnits <= 2)
})

test('the face material of a mesh has the offset, with vertex colours or grey', () => {
  for (const hasColors of [true, false]) {
    const material = bodyFaceMaterial(hasColors)
    assert.deepEqual(offsetOf(material), [true, 1, 1])
    assert.equal(material.side, THREE.DoubleSide)
    assert.equal(material.vertexColors, hasColors)
    // opaque and writing depth, as before the offset
    assert.equal(material.transparent, false)
    assert.equal(material.depthWrite, true)
    assert.equal(material.depthTest, true)
  }
  assert.equal(bodyFaceMaterial(false).color.getHex(), 0x888888)
})

test('the edge lines have no offset and keep their depth test', () => {
  const lines = edgeLineMaterial()
  assert.deepEqual(offsetOf(lines), [false, 0, 0])
  assert.equal(lines.depthTest, true)
  assert.equal(lines.color.getHex(), 0)
})

test('an existing material can be pushed back', () => {
  const standard = pushFacesBack(new THREE.MeshStandardMaterial({ color: 0x336699 }))
  assert.deepEqual(offsetOf(standard), [true, 1, 1])
  assert.equal(standard.color.getHex(), 0x336699)
})

test('the faded copy of the opacity slider keeps the offset, the original is not changed', () => {
  const faces = bodyFaceMaterial(true)
  const edges = edgeLineMaterial()
  const group = new THREE.Group()
  group.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), faces))
  group.add(new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)), edges))
  const copy = copyForViewer(group)
  applyOpacityToObject(copy, 40)
  const [copiedFaces, copiedEdges] = copy.children.map(
    (child) => (child as THREE.Mesh).material as THREE.Material)
  assert.deepEqual(offsetOf(copiedFaces), [true, 1, 1])
  assert.deepEqual(offsetOf(copiedEdges), [false, 0, 0])
  assert.equal(copiedFaces.opacity, 0.4)
  assert.deepEqual(offsetOf(faces), [true, 1, 1])
  assert.equal(faces.opacity, 1)
})

test('fading and restoring a face material leaves its offset', () => {
  const faces = bodyFaceMaterial(false)
  applyOpacity(faces, 30)
  applyOpacity(faces, 100)
  assert.deepEqual(offsetOf(faces), [true, 1, 1])
})


// THE CAMERA PLANES (0.6.3.1) -----------------------------------------------------
test('near is a hundredth of the distance and far lies past the piece', () => {
  const { near, far } = depthRange(6, 2.3)          // a 4.6 m beam, seen from the fit distance
  assert.equal(near, 0.06)
  assert.ok(far > 6 + 2.3, 'the far side of the piece and the grid are inside')
  assert.ok(far / near < 5000)
})

test('close to the piece the near plane follows, so a face is not cut away', () => {
  const radius = 2.3
  for (const distance of [1, 0.2, 0.05, 0.01]) {
    const { near } = depthRange(distance, radius)
    assert.ok(near <= distance / 100 + 1e-12 || near === radius * NEAR_FLOOR, String(distance))
    assert.ok(near < distance, 'a face at the target is in front of the near plane: ' + distance)
  }
  // a camera right at the target: still a positive, tiny near plane
  assert.ok(depthRange(0, radius).near > 0)
  assert.equal(depthRange(1e-9, radius).near, radius * NEAR_FLOOR)
})

test('the planes keep the ratio the depth buffer can resolve', () => {
  for (const radius of [0.09, 0.5, 2.3, 40]) {
    for (const distance of [radius * 1e-3, radius * 0.1, radius, radius * 3, radius * 10]) {
      const { near, far } = depthRange(distance, radius)
      assert.ok(near > 0 && far > near)
      assert.ok(far / near <= 1e6, `radius ${radius}, distance ${distance}: ${far / near}`)
    }
  }
})

test('a small piece and a large piece get planes of their own size', () => {
  const small = depthRange(0.3, 0.09)                // 185 mm
  const large = depthRange(6, 2.3)                   // 4.6 m
  assert.ok(small.near < large.near && small.far < large.far)
  assert.ok(small.far > 0.3 + 0.09)
})

test('a distance or radius that is no number falls back to something sane', () => {
  for (const [distance, radius] of [[Number.NaN, 1], [1, Number.NaN], [-3, 1], [1, 0], [Infinity, 1]]) {
    const { near, far } = depthRange(distance, radius)
    assert.ok(Number.isFinite(near) && Number.isFinite(far) && near > 0 && far > near)
  }
})

test('the camera is only touched when a plane moved by more than a hundredth', () => {
  const now = { near: 1, far: 100 }
  assert.equal(depthChanged(now, { near: 1.005, far: 100.4 }), false)
  assert.equal(depthChanged(now, { near: 1.2, far: 100 }), true)
  assert.equal(depthChanged(now, { near: 1, far: 150 }), true)
})

test('the view is fitted again when the piece changes size, not for a small wobble', () => {
  assert.equal(sizeChanged(0, 0.3), true)            // the first size
  assert.equal(sizeChanged(0.3, 0.3), false)
  assert.equal(sizeChanged(0.3, 0.31), false)
  assert.equal(sizeChanged(0.3, 4.6), true)          // a version of another size
  assert.equal(sizeChanged(4.6, 0.3), true)
})

test('a size that is no number never asks for a fit', () => {
  for (const bad of [0, -1, Number.NaN, Infinity]) {
    assert.equal(sizeChanged(0.3, bad), false)
    assert.equal(sizeChanged(0, bad), false)
  }
})
