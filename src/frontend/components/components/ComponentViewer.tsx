'use client'

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type {
  CatalogComponent,
  ComponentSnapshot,
} from '@/generated/CatalogModels'
import type { Geometry, Mesh, PointCloud } from '@/generated/CatalogSharedTypes'
import type { SnapshotMeshRouting } from '@/generated/catalogExtras'
import {
  primarySnapshot,
  snapshotMeshRoutingFromSnapshot,
} from '@/generated/catalogExtras'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Scan, Grid3x3, Rotate3d } from 'lucide-react'
import { Bounds, OrbitControls, Html, useBounds } from '@react-three/drei'
import { cn, rgbToHex } from '@/lib/utils'
import {
  buildPointCloudThreeGroup,
  loadSnapshotPointCloudPlyGroups,
  snapshotPointCloudsFromGeometry,
} from '@/lib/pointCloudGeometry'
import {
  REINFORCEMENT_RADIAL_SEGMENTS,
  buildReinforcementBarMeshes,
  reinforcementSteelMaterial,
  type ReinforcementBar,
} from '@/lib/reinforcementGeometry'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import ProxyOverlay, {
  useDeviationMaps,
  type ProxyDisplay,
} from '@/components/viewer/ProxyOverlay'
import type { ProxyDoc } from '@/lib/proxyOverlay'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ViewerMenu, MenuSection, MenuSubsection, MenuDivider, SegmentedControl, ScrollableCheckboxList, CheckboxControl } from '@/components/viewer/ViewerMenu'

// Scale factor for converting units to meters in THREE
const scale = 0.001
/** Slow Y-axis spin for turntable mode (~25s per revolution). */
const TURNTABLE_RADIANS_PER_SECOND = 0.35

/** Fit camera to scene bounds; registers ref for manual zoom-extents. */
function FitCameraController({
  fitRef,
}: {
  fitRef: React.MutableRefObject<(() => void) | null>
}) {
  const bounds = useBounds()
  const controls = useThree((state) => state.controls)
  const hasFit = useRef(false)

  const fitToScene = useCallback(() => {
    bounds.refresh().clip().fit()
  }, [bounds])

  useEffect(() => {
    fitRef.current = fitToScene
    return () => {
      fitRef.current = null
    }
  }, [fitRef, fitToScene])

  useLayoutEffect(() => {
    if (hasFit.current || !controls) return
    fitToScene()
    hasFit.current = true
  })

  return null
}

/**
 * Rotates the component around world Y. Angle is kept on the Three.js group
 * so mesh/point-cloud visibility toggles (React re-renders) do not reset it.
 */
function Turntable({
  enabled,
  children,
}: {
  enabled: boolean
  children: React.ReactNode
}) {
  const groupRef = useRef<THREE.Group>(null)
  const enabledRef = useRef(enabled)
  useEffect(() => {
    enabledRef.current = enabled
  }, [enabled])

  useFrame((_, delta) => {
    if (!enabledRef.current || !groupRef.current) return
    groupRef.current.rotation.y += delta * TURNTABLE_RADIANS_PER_SECOND
  })

  return <group ref={groupRef}>{children}</group>
}

type FrameDoc = { o: number[]; x: number[]; y: number[]; z: number[] }

/**
 * The snapshot's `frame` as a transform of the scene (decision 7.10): stored
 * coordinates map to the canonical orientation (x longest, z shortest; a
 * standing column has z as its length). The geometry in the scene already
 * has Rhino Z-up turned to three's Y-up, so the transform is conjugated by
 * that turn. Stored geometry is never changed; this only moves the view.
 */
function canonicalSceneMatrix(frame: FrameDoc | null | undefined): THREE.Matrix4 {
  if (!frame) return new THREE.Matrix4()
  const x = new THREE.Vector3(...frame.x)
  const y = new THREE.Vector3(...frame.y)
  const z = new THREE.Vector3(...frame.z)
  const origin = new THREE.Vector3(...frame.o)
  // world -> frame: rows are the axes, translation -R^T o (metres in the scene)
  const toFrame = new THREE.Matrix4().makeBasis(x, y, z).transpose()
  const shift = origin.clone().applyMatrix4(
    new THREE.Matrix4().extractRotation(toFrame),
  ).multiplyScalar(-scale)
  toFrame.setPosition(shift)
  const turn = new THREE.Matrix4().makeRotationX(-Math.PI / 2)
  return turn.clone().multiply(toFrame).multiply(turn.clone().invert())
}

// Simple in-memory cache for external geometry with ETag support
interface CachedMeshGeometry {
  meshes: THREE.Group[] | null
  etag?: string
  timestamp: number
}

interface CachedPointCloudGeometry {
  pointClouds: THREE.Group[] | null
  etag?: string
  timestamp: number
}

const externalMeshCache = new Map<string, CachedMeshGeometry>()
const externalPointCloudCache = new Map<string, CachedPointCloudGeometry>()

// Helpers

/**
 * Detail levels (decision 8.23): the proxy, the preview stored in the
 * snapshot, the reduced mesh file and the original as uploaded (stored on
 * disk as `detailed.ply`).
 */
type GeometryMode = 'proxy' | 'preview' | 'reduced' | 'original'
type MeshFileLevel = Extract<GeometryMode, 'reduced' | 'original'>
type PointCloudGeometryMode = 'preview' | 'original'

const DETAIL_LABELS: Record<GeometryMode, string> = {
  proxy: 'Proxy',
  preview: 'Preview',
  reduced: 'Reduced',
  original: 'Original',
}

/** The file a mesh detail level is stored in (`mesh_ply_resolutions`). */
const MESH_FILE_RESOLUTION: Record<MeshFileLevel, 'reduced' | 'detailed'> = {
  reduced: 'reduced',
  original: 'detailed',
}

const isMeshFileLevel = (mode: GeometryMode): mode is MeshFileLevel =>
  mode === 'reduced' || mode === 'original'

function nextObjectVisibility(
  count: number,
  previous: boolean[],
  defaultVisible: boolean,
  resetToDefault: boolean,
): boolean[] {
  if (count <= 0) return []
  if (resetToDefault || previous.length === 0) {
    return new Array(count).fill(defaultVisible)
  }
  const allVisible = previous.every((v) => v)
  return Array.from({ length: count }, (_, i) => {
    if (i < previous.length) return previous[i]
    return allVisible
  })
}

// External geometry/mtl loading

// Simple debug logging for dev mode only
const isDev = process.env.NODE_ENV === 'development'
const debugLog = (message: string, ...args: unknown[]) => {
  if (isDev) {
    console.log(`[ComponentViewer] ${message}`, ...args)
  }
}

/**
 * Smart color normalization - detects if colors are in 0-255 range and normalizes only if needed
 */
function normalizeColors(colors: number[]): number[] {
  if (colors.length === 0) return colors
  
  // Check if colors are already normalized (all values <= 1.0)
  const allNormalized = colors.every(color => color <= 1.0)
  
  if (allNormalized) {
    debugLog(`Colors already normalized, keeping as-is`)
    return colors
  }
  
  // Check if colors are in 0-255 range (all values >= 0 and <= 255)
  const allInRange = colors.every(color => color >= 0 && color <= 255)
  
  if (allInRange) {
    debugLog(`Converting colors from 0-255 range to 0-1 range`)
    return colors.map(color => color / 255)
  }
  
  // Mixed or invalid range - warn and clamp to 0-1
  debugLog(`Warning: Mixed color ranges detected, clamping to 0-1`)
  return colors.map(color => Math.max(0, Math.min(1, color)))
}

type MeshLoadResult = {
  success: true
  meshes: THREE.Group[]
} | {
  success: false
  error: 'not_found' | 'network_error' | 'parse_error'
  message: string
}

type PointCloudLoadResult = {
  success: true
  pointClouds: THREE.Group[]
} | {
  success: false
  error: 'not_found' | 'network_error' | 'parse_error'
  message: string
}

/** Flat buffers for one preview mesh (stored in the snapshot, 8.23). */
type PrimitiveDrawBuffers = {
  positionsFlat: number[]
  indices: number[]
  rawColors?: number[][]
}

function snapshotMeshesFromGeometry(geometry: Geometry): Mesh[] {
  const meshes = geometry.meshes
  return Array.isArray(meshes) ? (meshes as Mesh[]) : []
}

/** A prism proxy's shape: profile in xy, extruded along z, centred on z = 0. */
type PrismShape = { profile: number[][]; height: number }

/** A box proxy as the prism of its xy rectangle (App. B: centred, z up). */
function boxAsPrism(params: { size?: number[] }): PrismShape | null {
  const [sx, sy, sz] = params?.size ?? []
  if (![sx, sy, sz].every((v) => typeof v === 'number' && v > 0)) return null
  const hx = sx / 2
  const hy = sy / 2
  return { profile: [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]], height: sz }
}

/** Prism and box proxies of a snapshot (an authored L x W x H box or a GH extrusion). */
function snapshotPrismsFromGeometry(geometry: Geometry): PrismShape[] {
  return (geometry.proxies ?? [])
    .map((proxy) =>
      proxy.primitive === 'box'
        ? boxAsPrism(proxy.params as { size?: number[] })
        : proxy.primitive === 'prism'
          ? (proxy.params as PrismShape)
          : null,
    )
    .filter((prism): prism is PrismShape =>
      !!prism && Array.isArray(prism.profile) && typeof prism.height === 'number')
}

function vertexColorsFromSnapshot(
  colors: number[][] | unknown | undefined,
): number[][] | undefined {
  if (colors == null || !Array.isArray(colors) || colors.length === 0) {
    return undefined
  }
  if (!colors.every(c => Array.isArray(c))) {
    return undefined
  }
  return colors as number[][]
}

function snapshotMeshesToDrawBuffers(
  meshes: Mesh[],
): PrimitiveDrawBuffers[] {
  return meshes.map((m) => ({
    positionsFlat: m.vertices.flat(),
    indices: m.faces.flat(),
    rawColors: vertexColorsFromSnapshot(m.colors),
  }))
}

function meshHintForCache(snapshotMesh: SnapshotMeshRouting | null): string {
  if (!snapshotMesh?.snapshot_id) return 'no-snapshot'
  return `${snapshotMesh.snapshot_id}:${JSON.stringify(snapshotMesh.mesh_ply_resolutions ?? null)}`
}

function plyPrimitiveIndicesForMode(
  manifest: Record<string, string[]> | null | undefined,
  mode: 'reduced' | 'detailed',
): number[] {
  if (!manifest || typeof manifest !== 'object') return []
  const role = mode === 'reduced' ? 'reduced' : 'detailed'
  return Object.keys(manifest)
    .map((k) => Number.parseInt(k, 10))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => a - b)
    .filter((idx) => {
      const roles = manifest[String(idx)]
      return Array.isArray(roles) && roles.includes(role)
    })
}

function applyNormalizedVertexColors(geometry: THREE.BufferGeometry): void {
  const colorAttr = geometry.getAttribute('color') as THREE.BufferAttribute | undefined
  if (!colorAttr || colorAttr.array.length === 0) return

  const raw = Array.from(colorAttr.array as ArrayLike<number>)
  const normalized = normalizeColors(raw)
  geometry.setAttribute(
    'color',
    new THREE.Float32BufferAttribute(normalized, colorAttr.itemSize),
  )
}

function buildThreeGroupFromPLYGeometry(
  geometry: THREE.BufferGeometry,
  meshLabel: string,
): THREE.Group {
  applyNormalizedVertexColors(geometry)

  geometry.computeVertexNormals()
  geometry.normalizeNormals()
  geometry.rotateX(-Math.PI / 2)

  const hasColors = !!geometry.getAttribute('color')

  const material = hasColors
    ? new THREE.MeshBasicMaterial({
        vertexColors: true,
        side: THREE.DoubleSide,
        transparent: false,
        opacity: 1.0,
      })
    : new THREE.MeshBasicMaterial({
        color: 0x888888,
        side: THREE.DoubleSide,
        transparent: false,
        opacity: 1.0,
      })

  const mesh = new THREE.Mesh(geometry, material)
  mesh.name = meshLabel

  const object = new THREE.Group()
  object.add(mesh)
  {
    const edgeGeometry = new THREE.EdgesGeometry(geometry)
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })
    const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial)
    edges.name = `${meshLabel}_edges`
    object.add(edges)
  }
  object.scale.set(scale, scale, scale)
  return object
}

async function loadSnapshotPlyMeshes(
  snapshotId: string,
  mode: MeshFileLevel,
  manifest: Record<string, string[]> | null | undefined,
): Promise<{ ok: true; meshes: THREE.Group[]; etag?: string } | { ok: false }> {
  const resolution = MESH_FILE_RESOLUTION[mode]
  const indices = plyPrimitiveIndicesForMode(manifest, resolution)
  if (indices.length === 0) {
    return { ok: false }
  }

  const loader = new PLYLoader()
  const groups: THREE.Group[] = []
  const etags: string[] = []

  const headersBase: HeadersInit = { credentials: 'include' }

  for (const primitiveIndex of indices) {
    const url = `/api/backend/snapshots/${encodeURIComponent(snapshotId)}/meshes/${primitiveIndex}/${resolution}`
    const headers: HeadersInit = { ...headersBase }

    try {
      const response = await fetch(url, { headers })
      const etag = response.headers.get('ETag')
      if (etag) etags.push(etag)

      if (!response.ok) {
        debugLog(`PLY fetch failed ${url}: ${response.status}`)
        return { ok: false }
      }

      const buffer = await response.arrayBuffer()
      const geom = loader.parse(buffer)
      const label = `Mesh ${primitiveIndex + 1}`
      groups.push(buildThreeGroupFromPLYGeometry(geom, label))
    } catch (err) {
      debugLog(`PLY load error primitive ${primitiveIndex}:`, err)
      return { ok: false }
    }
  }

  if (groups.length === 0) {
    return { ok: false }
  }

  const combinedEtag = etags.length > 0 ? etags.sort().join('|') : undefined

  return {
    ok: true,
    meshes: groups,
    etag: combinedEtag,
  }
}

async function loadExternalMeshes(
  identityId: string,
  mode: MeshFileLevel,
  snapshotRouting: SnapshotMeshRouting | null,
): Promise<MeshLoadResult> {
  debugLog(`Loading ${mode} meshes for identity ${identityId}`)

  const hint = meshHintForCache(snapshotRouting)
  const cacheKey = `${identityId}:mesh:${mode}:${hint}`
  const cached = externalMeshCache.get(cacheKey)

  if (cached?.meshes) {
    debugLog(`Using cached meshes for ${identityId}: ${cached.meshes.length} mesh(es)`)
    return { success: true, meshes: cached.meshes }
  }

  if (cached && cached.meshes === null) {
    return {
      success: false,
      error: 'not_found',
      message: `No ${mode} mesh stored for this snapshot`,
    }
  }

  if (!snapshotRouting?.snapshot_id) {
    const msg = `No snapshot routing for ${mode} mode (passport payload missing current snapshot _id)`
    externalMeshCache.set(cacheKey, {
      meshes: null,
      etag: undefined,
      timestamp: Date.now(),
    })
    return { success: false, error: 'not_found', message: msg }
  }

  try {
    const plyResult = await loadSnapshotPlyMeshes(
      snapshotRouting.snapshot_id,
      mode,
      snapshotRouting.mesh_ply_resolutions ?? null,
    )

    if (plyResult.ok && plyResult.meshes.length > 0) {
      externalMeshCache.set(cacheKey, {
        meshes: plyResult.meshes,
        etag: plyResult.etag,
        timestamp: Date.now(),
      })
      debugLog(`Loaded ${plyResult.meshes.length} mesh(es) from PLY`)
      return { success: true, meshes: plyResult.meshes }
    }
  } catch (err) {
    debugLog('Mesh PLY pipeline failed:', err)
  }

  externalMeshCache.set(cacheKey, {
    meshes: null,
    etag: undefined,
    timestamp: Date.now(),
  })
  return {
    success: false,
    error: 'not_found',
    message: `No ${mode} mesh stored for this snapshot`,
  }
}

async function loadExternalPointClouds(
  identityId: string,
  snapshotRouting: SnapshotMeshRouting | null,
  pointCloudCount: number,
): Promise<PointCloudLoadResult> {
  debugLog(`Loading original point clouds for identity ${identityId}`)

  const hint = meshHintForCache(snapshotRouting)
  const cacheKey = `${identityId}:pc:${hint}:count${pointCloudCount}`
  const cached = externalPointCloudCache.get(cacheKey)

  if (cached?.pointClouds) {
    debugLog(
      `Using cached point clouds for ${identityId}: `
      + `${cached.pointClouds.length} point cloud(s)`,
    )
    return { success: true, pointClouds: cached.pointClouds }
  }

  if (cached && cached.pointClouds === null) {
    return {
      success: false,
      error: 'not_found',
      message: 'No original point cloud stored for this snapshot',
    }
  }

  if (!snapshotRouting?.snapshot_id) {
    const msg = 'No snapshot routing for the original point cloud (passport payload missing current snapshot _id)'
    externalPointCloudCache.set(cacheKey, {
      pointClouds: null,
      etag: undefined,
      timestamp: Date.now(),
    })
    return { success: false, error: 'not_found', message: msg }
  }

  try {
    const pointCloudResult = await loadSnapshotPointCloudPlyGroups(
      snapshotRouting.snapshot_id,
      pointCloudCount,
      { applyComponentViewerFrame: true, scale },
    )

    if (pointCloudResult.ok && pointCloudResult.groups.length > 0) {
      externalPointCloudCache.set(cacheKey, {
        pointClouds: pointCloudResult.groups,
        etag: pointCloudResult.etag,
        timestamp: Date.now(),
      })
      debugLog(`Loaded ${pointCloudResult.groups.length} point cloud(s) from PLY`)
      return { success: true, pointClouds: pointCloudResult.groups }
    }
  } catch (err) {
    debugLog('Point cloud PLY pipeline failed:', err)
  }

  externalPointCloudCache.set(cacheKey, {
    pointClouds: null,
    etag: undefined,
    timestamp: Date.now(),
  })
  return {
    success: false,
    error: 'not_found',
    message: 'No original point cloud stored for this snapshot',
  }
}

/**
 * Extrusion from API `{ profile: [x,y][], height }` (+ material RGB).
 */
const ExtrusionVisualization = React.memo(
  ({
    profile,
    height,
    colorRgb,
  }: {
    profile: number[][]
    height: number
    colorRgb: [number, number, number]
  }) => {
    const pline_shape = useMemo(() => {
      const shape = new THREE.Shape()
      if (!profile?.length) return shape
      shape.moveTo(profile[0][0] * scale, profile[0][1] * scale)
      profile.forEach((p, i) => {
        if (i > 0) shape.lineTo(p[0] * scale, p[1] * scale)
      })
      return shape
    }, [profile])

    const extrude_geometry = useMemo(() => {
      if (!profile?.length || !height) {
        return new THREE.ExtrudeGeometry(new THREE.Shape())
      }
      const extrudeSettings = { steps: 2, depth: height * scale, bevelEnabled: false }
      const g = new THREE.ExtrudeGeometry(pline_shape, extrudeSettings)
      g.translate(0, 0, -height * scale * 0.5)
      g.rotateX(-Math.PI / 2)
      // Indexed extrusion + shared vertices smear normals at cap/side edges.
      const geom = g.index !== null ? g.toNonIndexed() : g
      geom.computeVertexNormals()
      return geom
    }, [pline_shape, profile, height])

    const colorHex = rgbToHex(colorRgb[0], colorRgb[1], colorRgb[2])
    const edge_geometry = useMemo(() => new THREE.EdgesGeometry(extrude_geometry), [extrude_geometry])
    const edge_material = useMemo(() => new THREE.LineBasicMaterial({ color: 0x000000 }), [])

    return (
      <>
        <mesh visible geometry={extrude_geometry}>
          <meshStandardMaterial color={new THREE.Color(colorHex)} />
        </mesh>
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </>
    )
  },
)
ExtrusionVisualization.displayName = 'ExtrusionVisualization'

/**
 * MarkerPoints - renders marker points as red dots
 */
const MarkerPoints = React.memo(({
  markerPoints,
  visible
}: {
  markerPoints: number[][]
  visible: boolean
}) => {
  if (!visible || markerPoints.length === 0) return null

  return (
    <group scale={[scale, scale, scale]} rotation={[-Math.PI / 2, 0, 0]}>
      {markerPoints.map((point, index) => {
        const [x, y, z] = point
        return (
          <mesh key={index} position={[x, y, z]}>
            <sphereGeometry args={[5.0, 16, 12]} />
            <meshBasicMaterial color={0xff0000} />
          </mesh>
        )
      })}
    </group>
  )
})
MarkerPoints.displayName = 'MarkerPoints'

/**
 * Capture fixtures (decision 7.7): meshes captured with the piece that are
 * not part of it, e.g. the robot gripper. Drawn translucent, never measured.
 */
async function loadCaptureFixtures(
  snapshotId: string,
  count: number,
): Promise<THREE.Group[]> {
  const loader = new PLYLoader()
  const groups: THREE.Group[] = []
  for (let index = 0; index < count; index += 1) {
    const url = `/api/backend/snapshots/${encodeURIComponent(snapshotId)}/capture/fixtures/${index}.ply`
    const response = await fetch(url, { credentials: 'include' })
    if (!response.ok) continue
    const geometry = loader.parse(await response.arrayBuffer())
    geometry.computeVertexNormals()
    geometry.rotateX(-Math.PI / 2)
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({
        color: 0x9ca3af,
        transparent: true,
        opacity: 0.35,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    )
    mesh.name = `fixture_${index}`
    const group = new THREE.Group()
    group.add(mesh)
    group.scale.set(scale, scale, scale)
    groups.push(group)
  }
  return groups
}

const CaptureFixtures = React.memo(({
  fixtures,
  visible,
}: {
  fixtures: THREE.Group[]
  visible: boolean
}) => {
  if (!visible || fixtures.length === 0) return null
  return (
    <>
      {fixtures.map((group, index) => (
        <primitive key={`fixture-${index}`} object={group} />
      ))}
    </>
  )
})
CaptureFixtures.displayName = 'CaptureFixtures'

const ReinforcementBarMesh = React.memo(({ bar }: { bar: ReinforcementBar }) => {
  const { segments, cornerJoints } = useMemo(
    () => buildReinforcementBarMeshes(bar.points),
    [bar.points],
  )
  const radius = bar.diameter_mm / 2
  if (segments.length === 0) return null
  return (
    <group>
      {segments.map((segment, index) => (
        <mesh
          key={`segment-${index}`}
          position={segment.position}
          quaternion={segment.quaternion}
          material={reinforcementSteelMaterial}
        >
          <cylinderGeometry
            args={[radius, radius, segment.height, REINFORCEMENT_RADIAL_SEGMENTS]}
          />
        </mesh>
      ))}
      {cornerJoints.map((joint, index) => (
        <mesh key={`joint-${index}`} position={joint} material={reinforcementSteelMaterial}>
          <sphereGeometry args={[radius, REINFORCEMENT_RADIAL_SEGMENTS, 12]} />
        </mesh>
      ))}
    </group>
  )
})
ReinforcementBarMesh.displayName = 'ReinforcementBarMesh'

/** Bars of the `reinforcement_layout` evidence positioned on this snapshot. */
const ReinforcementBars = React.memo(({
  bars,
  visible,
}: {
  bars: ReinforcementBar[]
  visible: boolean
}) => {
  if (!visible || bars.length === 0) return null
  return (
    <group scale={[scale, scale, scale]} rotation={[-Math.PI / 2, 0, 0]}>
      {bars.map((bar, index) => (
        <ReinforcementBarMesh key={`${bar.spec}-${index}`} bar={bar} />
      ))}
    </group>
  )
})
ReinforcementBars.displayName = 'ReinforcementBars'

const PointCloudVisualization = React.memo(({
  pointClouds,
  visiblePointClouds,
  externalPointClouds,
  pointCloudGeometryMode,
  isLoadingExternal,
}: {
  pointClouds: PointCloud[]
  visiblePointClouds: boolean[]
  externalPointClouds: THREE.Group[]
  pointCloudGeometryMode: PointCloudGeometryMode
  isLoadingExternal: boolean
}) => {
  const isExternalMode = pointCloudGeometryMode === 'original'

  const inlineGroups = useMemo(
    () => pointClouds
      .map((pc, index) => buildPointCloudThreeGroup(
        pc,
        `inline_point_cloud_${index}`,
      ))
      .filter((group): group is THREE.Group => group !== null),
    [pointClouds],
  )

  if (isExternalMode) {
    if (isLoadingExternal || externalPointClouds.length === 0) return null
    return (
      <>
        {externalPointClouds.map((group, index) => {
          if (!visiblePointClouds[index]) return null
          return <primitive key={`external-pc-${index}`} object={group} />
        })}
      </>
    )
  }

  if (inlineGroups.length === 0) return null

  return (
    <group scale={[scale, scale, scale]} rotation={[-Math.PI / 2, 0, 0]}>
      {inlineGroups.map((group, index) => {
        if (!visiblePointClouds[index]) return null
        return <primitive key={`inline-pc-${index}`} object={group} />
      })}
    </group>
  )
})
PointCloudVisualization.displayName = 'PointCloudVisualization'

const VisualizeMultipleMeshes = React.memo(({
  primitiveDraws,
  meshGeometryMode,
  visibleMeshes = [],
  externalMeshes = [],
  isLoadingExternal = false,
  geometryError = null,
  showEdges
}: {
  primitiveDraws: PrimitiveDrawBuffers[]
  meshGeometryMode: GeometryMode
  visibleMeshes?: boolean[]
  externalMeshes?: THREE.Group[]
  isLoadingExternal?: boolean
  geometryError?: string | null
  showEdges: boolean
}) => {
  const isExternalMode = isMeshFileLevel(meshGeometryMode)

  if (isLoadingExternal) {
    return (
      <mesh>
        <Html center>
          <LoadingSpinner />
        </Html>
      </mesh>
    )
  }

  if (geometryError) {
    return (
      <mesh>
        <Html center>
          <div
            style={{
              minWidth: '200px',
              padding: '12px',
              background: 'rgba(255,255,255,0.9)',
              borderRadius: '4px',
              textAlign: 'center',
              border: '1px solid #e5e7eb',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <div style={{ color: '#6b7280', fontSize: '14px', marginBottom: '8px' }}>
              <strong>{geometryError}</strong>
            </div>
          </div>
        </Html>
      </mesh>
    )
  }

  if (isExternalMode && externalMeshes.length > 0) {
    return (
      <>
        {externalMeshes.map((mesh, index) => {
          if (!visibleMeshes[index]) return null
          return <primitive key={index} object={mesh} />
        })}
      </>
    )
  }

  return (
    <group scale={[scale, scale, scale]}>
      {primitiveDraws.map((mesh, index: number) => {
        if (!visibleMeshes[index]) return null

        const positions = mesh.positionsFlat
        const indices = mesh.indices
        const rawColors = mesh.rawColors

        const geom = new THREE.BufferGeometry()
        geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
        geom.setIndex(indices)

        if (rawColors && rawColors.length > 0) {
          const flatColors = rawColors.flat()
          const normalizedColors = normalizeColors(flatColors)
          geom.setAttribute('color', new THREE.Float32BufferAttribute(normalizedColors, 3))
          debugLog(`Applied ${normalizedColors.length / 3} vertex colors to primitive mesh ${index + 1}`)
        }

        geom.rotateX(-Math.PI / 2)
        geom.computeVertexNormals()
        geom.normalizeNormals()

        const material = rawColors && rawColors.length > 0
          ? new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })
          : new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.DoubleSide })

        const edgeGeometry = new THREE.EdgesGeometry(geom)
        const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })

        return (
          <group key={index}>
            <mesh geometry={geom} material={material} />
            {showEdges && (
              <lineSegments geometry={edgeGeometry} material={edgeMaterial} />
            )}
          </group>
        )
      })}
    </group>
  )
})
VisualizeMultipleMeshes.displayName = 'VisualizeMultipleMeshes'

type VisualizeProps = {
  catalog: CatalogComponent
  meshGeometryMode: GeometryMode
  pointCloudGeometryMode: PointCloudGeometryMode
  visibleMeshes?: boolean[]
  visiblePointClouds?: boolean[]
  externalMeshes?: THREE.Group[]
  externalPointClouds?: THREE.Group[]
  isLoadingExternalMeshes?: boolean
  isLoadingExternalPointClouds?: boolean
  meshGeometryError?: string | null
  showEdges: boolean
}

function snapshotPrismRgb(snap: ComponentSnapshot): [number, number, number] {
  const c = snap.color
  return [
    Array.isArray(c) ? (c[0] as number) : 110,
    Array.isArray(c) ? (c[1] as number) : 110,
    Array.isArray(c) ? (c[2] as number) : 110,
  ]
}

function VisualizeComponent(props: VisualizeProps) {
  const snapshot = primarySnapshot(props.catalog)
  const sg = snapshot.geometry
  const ext = snapshotPrismsFromGeometry(sg)[0]
  const primitiveDraws = snapshotMeshesToDrawBuffers(snapshotMeshesFromGeometry(sg))
  const pointClouds = snapshotPointCloudsFromGeometry(sg)

  const hasExtrusion =
    !!ext?.profile?.length && typeof ext.height === 'number' && Number.isFinite(ext.height)
  const hasMeshes = primitiveDraws.length > 0
  const hasPointClouds = pointClouds.length > 0

  // the proxy stands in when there is nothing else, or when chosen (8.23)
  if (hasExtrusion && (props.meshGeometryMode === 'proxy' || !hasMeshes)) {
    return (
      <>
        <ExtrusionVisualization
          profile={ext!.profile}
          height={ext!.height}
          colorRgb={snapshotPrismRgb(snapshot)}
        />
        <PointCloudVisualization
          pointClouds={pointClouds}
          visiblePointClouds={props.visiblePointClouds ?? []}
          externalPointClouds={props.externalPointClouds ?? []}
          pointCloudGeometryMode={props.pointCloudGeometryMode}
          isLoadingExternal={props.isLoadingExternalPointClouds ?? false}
        />
      </>
    )
  }
  if (hasMeshes || hasPointClouds) {
    return (
      <>
        <VisualizeMultipleMeshes
          primitiveDraws={primitiveDraws}
          meshGeometryMode={props.meshGeometryMode}
          visibleMeshes={props.visibleMeshes}
          externalMeshes={props.externalMeshes}
          isLoadingExternal={props.isLoadingExternalMeshes}
          geometryError={props.meshGeometryError}
          showEdges={props.showEdges}
        />
        <PointCloudVisualization
          pointClouds={pointClouds}
          visiblePointClouds={props.visiblePointClouds ?? []}
          externalPointClouds={props.externalPointClouds ?? []}
          pointCloudGeometryMode={props.pointCloudGeometryMode}
          isLoadingExternal={props.isLoadingExternalPointClouds ?? false}
        />
      </>
    )
  }
  return (
    <>
      <VisualizeMultipleMeshes
        primitiveDraws={primitiveDraws}
        meshGeometryMode={props.meshGeometryMode}
        visibleMeshes={props.visibleMeshes}
        externalMeshes={props.externalMeshes}
        isLoadingExternal={props.isLoadingExternalMeshes}
        geometryError={props.meshGeometryError}
        showEdges={props.showEdges}
      />
      <PointCloudVisualization
        pointClouds={pointClouds}
        visiblePointClouds={props.visiblePointClouds ?? []}
        externalPointClouds={props.externalPointClouds ?? []}
        pointCloudGeometryMode={props.pointCloudGeometryMode}
        isLoadingExternal={props.isLoadingExternalPointClouds ?? false}
      />
    </>
  )
}

/**
 * Catalog 3D viewer: **`GET /identities/{id}/compose`** payload (`identity` + `snapshots[]`).
 * Detail levels (decision 8.23): Proxy and Preview come from the snapshot
 * itself; Reduced / Original meshes load **`GET /snapshots/{snapshot_id}/meshes/{i}/{reduced|detailed}`**,
 * the original point cloud **`GET /snapshots/{snapshot_id}/point_clouds/{i}.ply`**.
 */
export type ComponentViewerProps = {
  catalog: CatalogComponent
  /** Shorter laptop+ viewport for the component detail L-layout. Other pages keep 50dvh. */
  compactDesktop?: boolean
}

export default function ComponentViewer({ catalog, compactDesktop = false }: ComponentViewerProps) {
  const snapshot = primarySnapshot(catalog)
  const identityId = catalog.identity._id

  const snapshotRouting = useMemo(
    () => snapshotMeshRoutingFromSnapshot(snapshot),
    [snapshot],
  )

  const snapshotGeometry = snapshot.geometry
  const snapshotMeshes = useMemo(
    () => snapshotMeshesFromGeometry(snapshotGeometry),
    [snapshotGeometry],
  )
  const snapshotPrisms = useMemo(
    () => snapshotPrismsFromGeometry(snapshotGeometry),
    [snapshotGeometry],
  )
  const snapshotPointClouds = useMemo(
    () => snapshotPointCloudsFromGeometry(snapshotGeometry),
    [snapshotGeometry],
  )

  const [orientation, setOrientation] = useState<'stored' | 'canonical'>('stored')
  const [proxyDisplay, setProxyDisplay] = useState<ProxyDisplay>('off')
  const [proxyRange, setProxyRange] = useState<number | null>(null)
  const snapshotFrame = (snapshot as { frame?: FrameDoc | null }).frame ?? null
  const orientationMatrix = useMemo(
    () => (orientation === 'canonical' ? canonicalSceneMatrix(snapshotFrame) : new THREE.Matrix4()),
    [orientation, snapshotFrame],
  )
  const primaryProxyIndex = useMemo(() => {
    const proxies = snapshotGeometry.proxies ?? []
    const primary = proxies.findIndex((proxy) => proxy.role === 'primary')
    return primary >= 0 ? primary : proxies.length > 0 ? 0 : -1
  }, [snapshotGeometry])
  const overlayProxy = primaryProxyIndex >= 0
    ? (snapshotGeometry.proxies ?? [])[primaryProxyIndex]
    : null
  const deviationFaces = (overlayProxy?.deviation_maps as
    | { faces?: Record<string, { distance: { scale_mm: number; offset_mm: number } }> }
    | null
    | undefined)?.faces
  const { maps: deviationMaps, error: deviationError } = useDeviationMaps(
    snapshot._id,
    primaryProxyIndex,
    deviationFaces,
    proxyDisplay !== 'off' && proxyDisplay !== 'outline',
  )

  const canRenderViewport =
    snapshotMeshes.length > 0
    || snapshotPrisms.length > 0
    || snapshotPointClouds.length > 0

  const [meshGeometryMode, setMeshGeometryMode] = useState<GeometryMode>('preview')
  const [pointCloudGeometryMode, setPointCloudGeometryMode] = useState<PointCloudGeometryMode>('preview')
  const [visibleMeshes, setVisibleMeshes] = useState<boolean[]>([])
  const [visiblePointClouds, setVisiblePointClouds] = useState<boolean[]>([])
  const [externalMeshes, setExternalMeshes] = useState<THREE.Group[]>([])
  const [externalPointClouds, setExternalPointClouds] = useState<THREE.Group[]>([])
  const [isLoadingExternalMeshes, setIsLoadingExternalMeshes] = useState(false)
  const [isLoadingExternalPointClouds, setIsLoadingExternalPointClouds] = useState(false)
  const [meshGeometryError, setMeshGeometryError] = useState<string | null>(null)
  const [showMarkerPoints, setShowMarkerPoints] = useState<boolean>(true)
  const [showEdges, setShowEdges] = useState<boolean>(true)
  const [showGrid, setShowGrid] = useState<boolean>(true)
  const [turntableEnabled, setTurntableEnabled] = useState<boolean>(false)
  const fitCameraRef = useRef<(() => void) | null>(null)

  const primitiveMeshCount = snapshotMeshes.length
  const primitivePointCloudCount = snapshotPointClouds.length
  const hasPointClouds = primitivePointCloudCount > 0
  const meshVisibilitySeedRef = useRef(
    `${identityId?.toString() ?? ''}:${primitiveMeshCount}`,
  )
  const pointCloudVisibilitySeedRef = useRef(
    `${identityId?.toString() ?? ''}:${primitivePointCloudCount}`,
  )

  const snapshotMeshCacheKey = useMemo(() => {
    if (!snapshotRouting?.snapshot_id) return ''
    return `${snapshotRouting.snapshot_id}:${JSON.stringify(snapshotRouting.mesh_ply_resolutions ?? null)}`
  }, [snapshotRouting])

  // a proxy only: no preview and no files to switch to
  const isProxyOnly = snapshotMeshes.length === 0 && snapshotPointClouds.length === 0
  const hasMultipleMeshes = primitiveMeshCount > 0
  const pointCloudVisibleByDefault = !hasMultipleMeshes
  const isMeshExternalMode = isMeshFileLevel(meshGeometryMode)
  const isPointCloudExternalMode = pointCloudGeometryMode === 'original'

  // capture markers (robot scans, decision 7.7): context, not the component
  const markerPoints = useMemo(
    () => (snapshot.capture?.markers ?? []).map((marker) => marker.point),
    [snapshot.capture],
  )

  const hasMarkerPoints = markerPoints.length > 0

  // capture fixtures (e.g. the robot gripper) of this snapshot
  const fixtureCount = snapshot.capture?.fixtures?.length ?? 0
  const snapshotIdForOverlays = String(snapshot._id ?? '')
  const [fixtureGroups, setFixtureGroups] = useState<THREE.Group[]>([])
  const [showFixtures, setShowFixtures] = useState<boolean>(true)
  useEffect(() => {
    let cancelled = false
    setFixtureGroups([])
    if (fixtureCount > 0 && snapshotIdForOverlays) {
      loadCaptureFixtures(snapshotIdForOverlays, fixtureCount)
        .then((groups) => { if (!cancelled) setFixtureGroups(groups) })
        .catch(() => { if (!cancelled) setFixtureGroups([]) })
    }
    return () => { cancelled = true }
  }, [fixtureCount, snapshotIdForOverlays])
  const hasFixtures = fixtureGroups.length > 0

  // reinforcement layouts are evidence positioned on one snapshot (7.8)
  const [reinforcementBars, setReinforcementBars] = useState<ReinforcementBar[]>([])
  const [showReinforcement, setShowReinforcement] = useState<boolean>(true)
  useEffect(() => {
    let cancelled = false
    setReinforcementBars([])
    if (!identityId || !snapshotIdForOverlays) return
    const params = new URLSearchParams({ method: 'reinforcement_layout' })
    fetch(`/api/backend/identities/${encodeURIComponent(String(identityId))}/evidence?${params}`, {
      credentials: 'include',
    })
      .then((response) => (response.ok ? response.json() : []))
      .then((records: { position?: { snapshot_id?: string | null }; payload?: { bars?: ReinforcementBar[] } }[]) => {
        if (cancelled) return
        const bars = records
          .filter((record) => record.position?.snapshot_id === snapshotIdForOverlays)
          .flatMap((record) => record.payload?.bars ?? [])
          .filter((bar) => Array.isArray(bar.points) && bar.points.length >= 2 && bar.diameter_mm > 0)
        setReinforcementBars(bars)
      })
      .catch(() => { if (!cancelled) setReinforcementBars([]) })
    return () => { cancelled = true }
  }, [identityId, snapshotIdForOverlays])
  const hasReinforcement = reinforcementBars.length > 0


  useEffect(() => {
    let isMounted = true
    const visibilitySeed = `${identityId?.toString() ?? ''}:${primitiveMeshCount}`
    const resetVisibilityToDefault =
      meshVisibilitySeedRef.current !== visibilitySeed
    meshVisibilitySeedRef.current = visibilitySeed

    if (isMeshExternalMode && !isProxyOnly && identityId) {
      setIsLoadingExternalMeshes(true)
      setMeshGeometryError(null)
      setShowEdges(false)
      loadExternalMeshes(
        identityId.toString(),
        meshGeometryMode,
        snapshotRouting,
      )
        .then((result) => {
          if (isMounted) {
            if (result.success) {
              setExternalMeshes(result.meshes)
              setMeshGeometryError(null)
              setVisibleMeshes((prev) => nextObjectVisibility(
                result.meshes.length,
                prev,
                true,
                resetVisibilityToDefault,
              ))
            } else {
              setExternalMeshes([])
              setMeshGeometryError(result.message)
              setVisibleMeshes([])
            }
            setIsLoadingExternalMeshes(false)
          }
        })
        .catch(() => {
          if (isMounted) {
            setExternalMeshes([])
            setMeshGeometryError(`Failed to load ${meshGeometryMode} geometry`)
            setVisibleMeshes([])
            setIsLoadingExternalMeshes(false)
          }
        })
    } else {
      setExternalMeshes([])
      setIsLoadingExternalMeshes(false)
      setMeshGeometryError(null)
      setShowEdges(true)
      if (hasMultipleMeshes) {
        setVisibleMeshes((prev) => nextObjectVisibility(
          primitiveMeshCount,
          prev,
          true,
          resetVisibilityToDefault,
        ))
      } else {
        setVisibleMeshes([])
      }
    }
    return () => {
      isMounted = false
    }
  }, [
    meshGeometryMode,
    isProxyOnly,
    identityId,
    isMeshExternalMode,
    primitiveMeshCount,
    hasMultipleMeshes,
    snapshotRouting,
    snapshotMeshCacheKey,
  ])

  useEffect(() => {
    let isMounted = true
    const visibilitySeed = `${identityId?.toString() ?? ''}:${primitivePointCloudCount}`
    const resetVisibilityToDefault =
      pointCloudVisibilitySeedRef.current !== visibilitySeed
    pointCloudVisibilitySeedRef.current = visibilitySeed

    if (isPointCloudExternalMode && !isProxyOnly && identityId) {
      setIsLoadingExternalPointClouds(true)
      loadExternalPointClouds(
        identityId.toString(),
        snapshotRouting,
        primitivePointCloudCount,
      )
        .then((result) => {
          if (isMounted) {
            if (result.success) {
              setExternalPointClouds(result.pointClouds)
              setVisiblePointClouds((prev) => nextObjectVisibility(
                result.pointClouds.length,
                prev,
                pointCloudVisibleByDefault,
                resetVisibilityToDefault,
              ))
            } else {
              setExternalPointClouds([])
              setVisiblePointClouds([])
            }
            setIsLoadingExternalPointClouds(false)
          }
        })
        .catch(() => {
          if (isMounted) {
            setExternalPointClouds([])
            setVisiblePointClouds([])
            setIsLoadingExternalPointClouds(false)
          }
        })
    } else {
      setExternalPointClouds([])
      setIsLoadingExternalPointClouds(false)
      if (hasPointClouds) {
        setVisiblePointClouds((prev) => nextObjectVisibility(
          primitivePointCloudCount,
          prev,
          pointCloudVisibleByDefault,
          resetVisibilityToDefault,
        ))
      } else {
        setVisiblePointClouds([])
      }
    }
    return () => {
      isMounted = false
    }
  }, [
    pointCloudGeometryMode,
    isProxyOnly,
    identityId,
    isPointCloudExternalMode,
    primitivePointCloudCount,
    hasPointClouds,
    pointCloudVisibleByDefault,
    snapshotRouting,
    snapshotMeshCacheKey,
  ])

  const onMeshModeChange = (value: string) => {
    setMeshGeometryMode(value as GeometryMode)
  }

  const onPointCloudModeChange = (value: string) => {
    setPointCloudGeometryMode(value as PointCloudGeometryMode)
  }

  const toggleMeshVisibility = (index: number) => {
    setVisibleMeshes((prev) => {
      const next = [...prev]
      next[index] = !next[index]
      return next
    })
  }

  const toggleAllMeshes = () => {
    const allVisible = visibleMeshes.every((v) => v)
    setVisibleMeshes((prev) => prev.map(() => !allVisible))
  }

  const togglePointCloudVisibility = (index: number) => {
    setVisiblePointClouds((prev) => {
      const next = [...prev]
      next[index] = !next[index]
      return next
    })
  }

  const toggleAllPointClouds = () => {
    const allVisible = visiblePointClouds.every((v) => v)
    setVisiblePointClouds((prev) => prev.map(() => !allVisible))
  }

  const allMeshesVisible = useMemo(
    () => visibleMeshes.length > 0 && visibleMeshes.every((v) => v),
    [visibleMeshes],
  )

  const allPointCloudsVisible = useMemo(
    () => visiblePointClouds.length > 0 && visiblePointClouds.every((v) => v),
    [visiblePointClouds],
  )

  const activePointCloudCount = isPointCloudExternalMode
    ? externalPointClouds.length
    : primitivePointCloudCount

  const activeMeshCount = isMeshExternalMode
    ? externalMeshes.length
    : primitiveMeshCount

  useEffect(() => {
    if (!isMeshExternalMode) return
    externalMeshes.forEach((group) => {
      group.traverse((obj) => {
        if ((obj as THREE.LineSegments).isLineSegments && obj.name.endsWith('_edges')) {
          obj.visible = showEdges
        }
      })
    })
  }, [showEdges, isMeshExternalMode, externalMeshes])

  if (!canRenderViewport) {
    return <ComponentViewerSkeleton message="No Geometry Available" />
  }

  // only the levels this snapshot has (decision 8.23)
  const storedMeshFiles = new Set(
    Object.values(snapshotRouting?.mesh_ply_resolutions ?? {}).flat(),
  )
  const meshDetailLevels: GeometryMode[] = [
    ...(snapshotPrisms.length > 0 ? ['proxy' as const] : []),
    'preview',
    ...(storedMeshFiles.has('reduced') ? ['reduced' as const] : []),
    ...(storedMeshFiles.has('detailed') ? ['original' as const] : []),
  ]
  const meshDetailOptions = meshDetailLevels.map((value) => ({
    value,
    label: DETAIL_LABELS[value],
  }))

  const pointCloudDetailOptions = (['preview', 'original'] as const).map((value) => ({
    value,
    label: DETAIL_LABELS[value],
  }))

  const primaryProxy = (snapshotGeometry.proxies ?? []).find((proxy) => proxy.role === 'primary')
    ?? snapshotGeometry.proxies?.[0]

  const meshCount = activeMeshCount || primitiveMeshCount
  const pointCloudCount = activePointCloudCount || primitivePointCloudCount
  const hasOverlays = hasMarkerPoints || hasFixtures || hasReinforcement

  // items are numbered only when there is more than one (8.23)
  const meshLabel = (index: number) => `Mesh ${index + 1}`
  const pointCloudLabel = (index: number) => `Point cloud ${index + 1}`

  const displayBlocks: React.ReactNode[] = []

  if (isProxyOnly && primaryProxy) {
    displayBlocks.push(
      <MenuSubsection key="proxy" title="Proxy">
        <p className="text-xs text-muted-foreground">
          Showing: {primaryProxy.primitive} proxy ({primaryProxy.fit.method})
        </p>
      </MenuSubsection>,
    )
  }

  if (hasMultipleMeshes) {
    displayBlocks.push(
      <MenuSubsection key="meshes" title={meshCount > 1 ? `Meshes (${meshCount})` : 'Mesh'}>
        {meshDetailOptions.length > 1 ? (
          <SegmentedControl
            id="meshGeometryModeSelect"
            label="Detail"
            value={meshGeometryMode}
            onValueChange={onMeshModeChange}
            options={meshDetailOptions}
          />
        ) : (
          <p className="text-xs text-muted-foreground">Detail: Preview</p>
        )}
        <CheckboxControl
          id="toggle-edges"
          label="Show edges"
          checked={showEdges}
          onChange={(checked) => setShowEdges(checked)}
        />
        {meshCount > 1 ? (
          <>
            <CheckboxControl
              id="toggle-all-meshes"
              label="Show all"
              checked={allMeshesVisible}
              onChange={toggleAllMeshes}
            />
            <ScrollableCheckboxList
              items={Array.from({ length: meshCount }, (_, i) => i).map((index: number) => ({
                id: String(index),
                label: meshLabel(index),
                checked: visibleMeshes[index] || false,
              }))}
              onToggle={(id) => toggleMeshVisibility(Number(id))}
            />
          </>
        ) : (
          <CheckboxControl
            id="toggle-mesh-0"
            label="Show mesh"
            checked={visibleMeshes[0] ?? false}
            onChange={(checked) => {
              setVisibleMeshes((prev) => {
                const next = [...prev]
                next[0] = checked
                return next
              })
            }}
          />
        )}
      </MenuSubsection>,
    )
  }

  if (hasPointClouds) {
    if (displayBlocks.length > 0) {
      displayBlocks.push(<MenuDivider key="divider-pc" />)
    }
    displayBlocks.push(
      <MenuSubsection
        key="point-clouds"
        title={pointCloudCount > 1 ? `Point clouds (${pointCloudCount})` : 'Point cloud'}
      >
        <SegmentedControl
          id="pointCloudGeometryModeSelect"
          label="Detail"
          value={pointCloudGeometryMode}
          onValueChange={onPointCloudModeChange}
          disabled={isProxyOnly}
          options={pointCloudDetailOptions}
        />
        {pointCloudCount > 1 ? (
          <>
            <CheckboxControl
              id="toggle-all-point-clouds"
              label="Show all"
              checked={allPointCloudsVisible}
              onChange={toggleAllPointClouds}
            />
            <ScrollableCheckboxList
              items={Array.from({ length: pointCloudCount }, (_, index) => ({
                id: String(index),
                label: pointCloudLabel(index),
                checked: visiblePointClouds[index] || false,
              }))}
              onToggle={(id) => togglePointCloudVisibility(Number(id))}
            />
          </>
        ) : (
          <CheckboxControl
            id="toggle-point-cloud-0"
            label="Show point cloud"
            checked={visiblePointClouds[0] ?? false}
            onChange={(checked) => {
              setVisiblePointClouds((prev) => {
                const next = [...prev]
                next[0] = checked
                return next
              })
            }}
          />
        )}
      </MenuSubsection>,
    )
  }

  if (snapshotFrame) {
    if (displayBlocks.length > 0) {
      displayBlocks.push(<MenuDivider key="divider-orientation" />)
    }
    displayBlocks.push(
      <MenuSubsection key="orientation" title="Orientation">
        <SegmentedControl
          id="orientationSelect"
          label="Show"
          value={orientation}
          onValueChange={(value) => setOrientation(value as 'stored' | 'canonical')}
          options={[
            { value: 'stored', label: 'As stored' },
            { value: 'canonical', label: 'Canonical' },
          ]}
        />
        <p className="text-xs text-muted-foreground">
          {snapshot.bbx && snapshot.bbx[2] > snapshot.bbx[0]
            ? 'Canonical: a standing column, its length along z'
            : 'Canonical: longest side along x, shortest along z'}
          {snapshot.bbx
            ? ` (${snapshot.bbx.map((v: number) => Math.round(v)).join(' x ')} mm)`
            : ''}
          . The stored geometry is never turned.
        </p>
      </MenuSubsection>,
    )
  }

  if (overlayProxy) {
    const fit = overlayProxy.fit
    const hasMaps = !!deviationFaces && Object.keys(deviationFaces).length > 0
    const options: { value: ProxyDisplay; label: string }[] = [
      { value: 'off', label: 'Off' },
      { value: 'outline', label: 'Outline' },
      ...(hasMaps
        ? [
            { value: 'distance' as const, label: 'Distance' },
            { value: 'normal_deviation' as const, label: 'Normal' },
            { value: 'occupancy' as const, label: 'Points' },
          ]
        : []),
    ]
    const unit = proxyDisplay === 'distance' ? 'mm' : proxyDisplay === 'normal_deviation' ? 'deg' : 'points'
    if (displayBlocks.length > 0) {
      displayBlocks.push(<MenuDivider key="divider-proxy" />)
    }
    displayBlocks.push(
      <MenuSubsection key="proxy-overlay" title="Proxy overlay">
        <SegmentedControl
          id="proxyDisplaySelect"
          label="Overlay"
          value={proxyDisplay}
          onValueChange={(value) => setProxyDisplay(value as ProxyDisplay)}
          options={options}
        />
        <p className="text-xs text-muted-foreground">
          {overlayProxy.primitive} ({fit.method})
          {fit.p95_mm != null
            ? `: p95 ${fit.p95_mm.toFixed(1)} mm, max ${(fit.max_mm ?? 0).toFixed(1)} mm`
            : ''}
        </p>
        {proxyRange != null && proxyDisplay !== 'off' && proxyDisplay !== 'outline' && (
          <p className="text-xs text-muted-foreground">
            {proxyDisplay === 'distance'
              ? `Blue inside the proxy, red outside, white on it; full colour at +/-${proxyRange.toFixed(1)} ${unit}.`
              : `Scale 0 to ${proxyRange.toFixed(proxyDisplay === 'occupancy' ? 0 : 1)} ${unit}.`}
          </p>
        )}
        {deviationError && (
          <p className="text-xs text-destructive">Deviation maps unavailable ({deviationError}).</p>
        )}
      </MenuSubsection>,
    )
  }

  if (hasOverlays) {
    if (displayBlocks.length > 0) {
      displayBlocks.push(<MenuDivider key="divider-overlays" />)
    }
    displayBlocks.push(
      <MenuSubsection key="overlays" title="Overlays">
        {hasMarkerPoints && (
          <CheckboxControl
            id="toggle-marker-points"
            label={`Marker points (${markerPoints.length})`}
            checked={showMarkerPoints}
            onChange={(checked) => setShowMarkerPoints(checked)}
          />
        )}
        {hasFixtures && (
          <CheckboxControl
            id="toggle-capture-fixtures"
            label={`Capture fixtures (${fixtureGroups.length})`}
            checked={showFixtures}
            onChange={(checked) => setShowFixtures(checked)}
          />
        )}
        {hasReinforcement && (
          <CheckboxControl
            id="toggle-reinforcement"
            label={`Reinforcement (${reinforcementBars.length} bars)`}
            checked={showReinforcement}
            onChange={(checked) => setShowReinforcement(checked)}
          />
        )}
      </MenuSubsection>,
    )
  }

  const hasDisplayOptions = displayBlocks.length > 0

  const menuSections: MenuSection[] = hasDisplayOptions
    ? [{
        id: 'display',
        title: 'Display Settings',
        content: <div className="flex flex-col gap-3">{displayBlocks}</div>,
      }]
    : []

  const desktopViewportClass = compactDesktop
    ? 'h-[30dvh] sm:h-[40dvh] md:h-[50dvh] 2xl:h-[56vh]'
    : 'h-[30dvh] sm:h-[40dvh] md:h-[50dvh]'

  return (
    <div className="flex flex-col md:flex-row gap-2 w-full">
      {hasDisplayOptions && (
        <div
          className={cn(
            'w-full md:w-64 md:flex-shrink-0 order-2 md:order-1 md:h-[50dvh]',
            compactDesktop && '2xl:h-[56vh]',
          )}
        >
          <ViewerMenu sections={menuSections} className="h-full" />
        </div>
      )}

      <Card className={cn('flex-1 overflow-hidden order-1 md:order-2 p-0', desktopViewportClass)}>
        <div className="relative w-full h-full">
          <div className="absolute top-2 right-2 z-10 flex flex-col gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="secondary"
                  size="icon-xs"
                  className="h-7 w-7 bg-background/85 text-black shadow-sm backdrop-blur-sm dark:text-white"
                  onClick={() => fitCameraRef.current?.()}
                  aria-label="Zoom extents"
                >
                  <Scan className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left">Zoom extents</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant={showGrid ? 'secondary' : 'ghost'}
                  size="icon-xs"
                  className={`h-7 w-7 text-black shadow-sm backdrop-blur-sm dark:text-white ${
                    showGrid ? 'bg-background/85' : 'bg-background/60'
                  }`}
                  onClick={() => setShowGrid((prev) => !prev)}
                  aria-label={showGrid ? 'Hide grid' : 'Show grid'}
                  aria-pressed={showGrid}
                >
                  <Grid3x3 className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left">{showGrid ? 'Hide grid' : 'Show grid'}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant={turntableEnabled ? 'secondary' : 'ghost'}
                  size="icon-xs"
                  className={`h-7 w-7 text-black shadow-sm backdrop-blur-sm dark:text-white ${
                    turntableEnabled ? 'bg-background/85' : 'bg-background/60'
                  }`}
                  onClick={() => setTurntableEnabled((prev) => !prev)}
                  aria-label={turntableEnabled ? 'Stop turntable' : 'Start turntable'}
                  aria-pressed={turntableEnabled}
                >
                  <Rotate3d className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left">
                {turntableEnabled ? 'Stop turntable' : 'Start turntable'}
              </TooltipContent>
            </Tooltip>
          </div>
          <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds
            key={identityId?.toString() ?? 'component-viewer'}
            clip
            margin={1.2}
            maxDuration={1}
          >
            <FitCameraController fitRef={fitCameraRef} />
            <Turntable enabled={turntableEnabled}>
              <group matrixAutoUpdate={false} matrix={orientationMatrix}>
              <VisualizeComponent
                catalog={catalog}
                meshGeometryMode={meshGeometryMode}
                pointCloudGeometryMode={pointCloudGeometryMode}
                visibleMeshes={visibleMeshes}
                visiblePointClouds={visiblePointClouds}
                externalMeshes={isMeshExternalMode ? externalMeshes : []}
                externalPointClouds={isPointCloudExternalMode ? externalPointClouds : []}
                isLoadingExternalMeshes={isLoadingExternalMeshes}
                isLoadingExternalPointClouds={isLoadingExternalPointClouds}
                meshGeometryError={meshGeometryError}
                showEdges={showEdges}
              />
              <MarkerPoints markerPoints={markerPoints} visible={showMarkerPoints} />
              <CaptureFixtures fixtures={fixtureGroups} visible={showFixtures} />
              <ReinforcementBars bars={reinforcementBars} visible={showReinforcement} />
              {overlayProxy && (
                <ProxyOverlay
                  proxy={overlayProxy as unknown as ProxyDoc}
                  display={proxyDisplay}
                  maps={deviationMaps}
                  onRange={setProxyRange}
                />
              )}
              </group>
            </Turntable>
          </Bounds>

          <axesHelper args={[0.1]} />
          {showGrid && <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />}
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </Card>
    </div>
  )
}
