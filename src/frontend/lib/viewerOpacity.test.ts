/**
 * The viewer's opacity slider (decision 8.165 C): which layers are the body,
 * the material fields for a percentage, the restore at 100 %, and that a
 * viewer fades its own copies only (the cached objects and a second viewer
 * keep their look).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as THREE from 'three'

import {
  BODY_LAYERS,
  OVERLAY_LAYERS,
  applyOpacity,
  applyOpacityToObject,
  clampOpacityPercent,
  copyForViewer,
  disposeViewerCopy,
  isBodyLayer,
  materialSettings,
  visibleBodyLayers,
  type LayerState,
} from '@/lib/viewerOpacity'

const everything: LayerState = {
  showingProxy: false,
  showProxyMesh: true,
  showEdges: true,
  visibleMeshes: [true],
  visiblePointClouds: [true],
}

test('the body is the mesh, its edges, the proxy and the point cloud', () => {
  assert.deepEqual([...BODY_LAYERS], ['mesh', 'mesh-edges', 'proxy', 'proxy-edges', 'point-cloud'])
  for (const layer of BODY_LAYERS) assert.equal(isBodyLayer(layer), true)
})

test('overlays are never body layers', () => {
  for (const layer of OVERLAY_LAYERS) assert.equal(isBodyLayer(layer), false, layer)
  for (const layer of ['reinforcement', 'test-positions', 'marker-points', 'capture-fixtures', 'grid']) {
    assert.ok((OVERLAY_LAYERS as readonly string[]).includes(layer), layer)
  }
  assert.equal(isBodyLayer('unknown'), false)
})

test('visible body layers follow what is on screen', () => {
  assert.deepEqual(visibleBodyLayers(everything), ['mesh', 'mesh-edges', 'point-cloud'])
  assert.deepEqual(visibleBodyLayers({ ...everything, showEdges: false }), ['mesh', 'point-cloud'])
  assert.deepEqual(visibleBodyLayers({ ...everything, visibleMeshes: [false, false] }), ['point-cloud'])
  assert.deepEqual(visibleBodyLayers({ ...everything, visiblePointClouds: [] }), ['mesh', 'mesh-edges'])
})

test('a hidden mesh takes its edges with it', () => {
  const none = visibleBodyLayers({ ...everything, visibleMeshes: [false], visiblePointClouds: [false] })
  assert.deepEqual(none, [])
})

test('the proxy stands in for the mesh and has its own switches', () => {
  const proxy: LayerState = { ...everything, showingProxy: true, visiblePointClouds: [] }
  assert.deepEqual(visibleBodyLayers(proxy), ['proxy', 'proxy-edges'])
  assert.deepEqual(visibleBodyLayers({ ...proxy, showProxyMesh: false }), ['proxy-edges'])
  assert.deepEqual(visibleBodyLayers({ ...proxy, showEdges: false }), ['proxy'])
  assert.deepEqual(visibleBodyLayers({ ...proxy, showProxyMesh: false, showEdges: false }), [])
})

test('the slider value is a whole step from 0 to 100', () => {
  assert.equal(clampOpacityPercent(50), 50)
  assert.equal(clampOpacityPercent(52), 50)
  assert.equal(clampOpacityPercent(53), 55)
  assert.equal(clampOpacityPercent(-10), 0)
  assert.equal(clampOpacityPercent(140), 100)
  assert.equal(clampOpacityPercent(Number.NaN), 100)
  assert.equal(clampOpacityPercent(Number.POSITIVE_INFINITY), 100)
})

test('100 percent is the original opaque state', () => {
  assert.deepEqual(materialSettings(100), { transparent: false, opacity: 1, depthWrite: true })
})

test('below 100 percent the material is transparent and writes no depth', () => {
  assert.deepEqual(materialSettings(95), { transparent: true, opacity: 0.95, depthWrite: false })
  assert.deepEqual(materialSettings(50), { transparent: true, opacity: 0.5, depthWrite: false })
  assert.deepEqual(materialSettings(0), { transparent: true, opacity: 0, depthWrite: false })
})

test('fading and restoring a material gives back the same fields', () => {
  const material = new THREE.MeshBasicMaterial({
    vertexColors: true,
    side: THREE.DoubleSide,
    transparent: false,
    opacity: 1,
  })
  const before = { transparent: material.transparent, opacity: material.opacity, depthWrite: material.depthWrite }
  applyOpacity(material, 40)
  assert.equal(material.transparent, true)
  assert.equal(material.opacity, 0.4)
  assert.equal(material.depthWrite, false)
  applyOpacity(material, 100)
  assert.deepEqual(
    { transparent: material.transparent, opacity: material.opacity, depthWrite: material.depthWrite },
    before,
  )
  assert.equal(material.vertexColors, true)
  assert.equal(material.side, THREE.DoubleSide)
})

test('a change of the transparent flag asks for a rebuild, a plain move does not', () => {
  const material = new THREE.MeshBasicMaterial()
  const version = material.version
  applyOpacity(material, 60)
  assert.equal(material.version, version + 1)
  applyOpacity(material, 30)
  assert.equal(material.version, version + 1)
  applyOpacity(material, 100)
  assert.equal(material.version, version + 2)
})

test('a point cloud keeps its point size, attenuation and colours', () => {
  const sized = new THREE.PointsMaterial({ size: 4, sizeAttenuation: false, vertexColors: true })
  applyOpacity(sized, 50)
  assert.equal(sized.size, 4)
  assert.equal(sized.sizeAttenuation, false)
  assert.equal(sized.vertexColors, true)
  assert.equal(sized.transparent, true)
  assert.equal(sized.depthWrite, false)
  const grey = new THREE.PointsMaterial({ size: 4, sizeAttenuation: false, color: 0x888888 })
  applyOpacity(grey, 50)
  assert.equal(grey.color.getHex(), 0x888888)
})

/** A mesh with its edges and a point cloud, as the loaders build them. */
function cachedGroups() {
  const geometry = new THREE.BoxGeometry(1, 1, 1)
  const body = new THREE.Group()
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: 0x888888 }))
  mesh.name = 'Mesh 1'
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), new THREE.LineBasicMaterial({ color: 0 }))
  edges.name = 'Mesh 1_edges'
  body.add(mesh, edges)
  const cloud = new THREE.Group()
  cloud.add(new THREE.Points(geometry, new THREE.PointsMaterial({ size: 4, sizeAttenuation: false })))
  return { body, cloud }
}

function fields(root: THREE.Object3D) {
  const found: MaterialFields[] = []
  root.traverse((object) => {
    const material = (object as THREE.Mesh).material as THREE.Material | undefined
    if (material) found.push({ transparent: material.transparent, opacity: material.opacity, depthWrite: material.depthWrite })
  })
  return found
}
type MaterialFields = { transparent: boolean; opacity: number; depthWrite: boolean }

test('a viewer copy shares the geometry and owns its materials', () => {
  const { body } = cachedGroups()
  const copy = copyForViewer(body)
  const original = body.children[0] as THREE.Mesh
  const copied = copy.children[0] as THREE.Mesh
  assert.notEqual(copy, body)
  assert.equal(copied.geometry, original.geometry)
  assert.notEqual(copied.material, original.material)
  assert.equal((copy.children[1] as THREE.LineSegments).geometry, (body.children[1] as THREE.LineSegments).geometry)
  assert.notEqual((copy.children[1] as THREE.LineSegments).material, (body.children[1] as THREE.LineSegments).material)
  assert.equal(copied.name, 'Mesh 1')
  assert.equal(copy.children[1].name, 'Mesh 1_edges')
})

test('fading a copy never touches the cached object', () => {
  const { body, cloud } = cachedGroups()
  const before = [...fields(body), ...fields(cloud)]
  const bodyCopy = copyForViewer(body)
  const cloudCopy = copyForViewer(cloud)
  applyOpacityToObject(bodyCopy, 30)
  applyOpacityToObject(cloudCopy, 30)
  assert.deepEqual([...fields(body), ...fields(cloud)], before)
  for (const material of [...fields(bodyCopy), ...fields(cloudCopy)]) {
    assert.deepEqual(material, { transparent: true, opacity: 0.3, depthWrite: false })
  }
  // the mesh and its edges both fade
  assert.equal(fields(bodyCopy).length, 2)
})

test('two viewers on one cached object keep their own opacity', () => {
  const { body } = cachedGroups()
  const detail = copyForViewer(body)
  const preview = copyForViewer(body)
  applyOpacityToObject(detail, 25)
  assert.deepEqual(fields(preview), fields(body))
  applyOpacityToObject(preview, 80)
  for (const material of fields(detail)) assert.equal(material.opacity, 0.25)
  for (const material of fields(preview)) assert.equal(material.opacity, 0.8)
  for (const material of fields(body)) assert.equal(material.opacity, 1)
  applyOpacityToObject(detail, 100)
  for (const material of fields(detail)) assert.deepEqual(material, { transparent: false, opacity: 1, depthWrite: true })
  for (const material of fields(preview)) assert.equal(material.opacity, 0.8)
})

test('a copy made while faded can be restored to the original state', () => {
  const { body } = cachedGroups()
  const first = copyForViewer(body)
  applyOpacityToObject(first, 40)
  const second = copyForViewer(body)
  applyOpacityToObject(second, 40)
  applyOpacityToObject(second, 100)
  assert.deepEqual(fields(second), fields(body))
})

test('freeing a copy leaves the cached materials usable', () => {
  const { body } = cachedGroups()
  let disposed = 0
  const original = (body.children[0] as THREE.Mesh).material as THREE.Material
  original.addEventListener('dispose', () => { disposed += 1 })
  const copy = copyForViewer(body)
  disposeViewerCopy(copy)
  assert.equal(disposed, 0)
})
