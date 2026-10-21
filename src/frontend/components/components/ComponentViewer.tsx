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
import { Scan, Grid3x3, Rotate3d, SlidersHorizontal } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
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
  reinforcementMaterial,
  type ReinforcementBar,
} from '@/lib/reinforcementGeometry'
import {
  BAR_COLOUR_OPTIONS,
  barColour,
  barLegend,
  defaultColourMode,
  diameterRange,
  layoutsOnSnapshot,
  type BarColourMode,
  type BarLayout,
} from '@/lib/reinforcementColors'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import ProxyOverlay, {
  useDeviationMaps,
  type ProxyDisplay,
} from '@/components/viewer/ProxyOverlay'
import EvidenceMarks, { type ViewerMark } from '@/components/viewer/EvidenceMarks'
import PickLayer from '@/components/viewer/PickLayer'
import type { PickHit } from '@/lib/evidence/pick'
import { publishedMarks } from '@/lib/evidence/marks'
import type { ProxyDoc } from '@/lib/proxyOverlay'
import type { ProxyShape } from '@/lib/proxyShape'
import ProxySolid from '@/components/viewer/ProxySolid'
import { useProxyShape } from '@/components/viewer/useProxyShape'
import OpacitySlider from '@/components/viewer/OpacitySlider'
import { useViewerCopies } from '@/components/viewer/useViewerCopies'
import {
  OPACITY_DEFAULT,
  applyOpacity,
  visibleBodyLayers,
} from '@/lib/viewerOpacity'
import {
  bodyFaceMaterial,
  depthChanged,
  depthRange,
  edgeLineMaterial,
  sizeChanged,
} from '@/lib/viewerDepth'
import {
  chooseSwitch,
  edgesControl,
  hasMeshSwitch,
  pointCloudStartsOff,
  shouldLoadLevel,
  shownFlags,
  switchValue,
  withOff,
} from '@/lib/viewerSwitches'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import Help from '@/components/ui/help'
import { ViewerMenu, MenuSection, MenuSubsection, MenuDivider, InfoLine, SegmentedControl, ScrollableCheckboxList, CheckboxControl } from '@/components/viewer/ViewerMenu'

// Scale factor for converting units to meters in THREE
const scale = 0.001
/** Slow Y-axis spin for turntable mode (~25s per revolution). */
const TURNTABLE_RADIANS_PER_SECOND = 0.35

/**
 * A detail switch of the toolbar with its name in front of it (on a phone the
 * name sits above). The switch carries the name for assistive technology too.
 */
function ToolbarSwitch({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex w-full flex-col gap-0.5 sm:w-auto sm:flex-row sm:items-center sm:gap-1.5">
      <span className="text-[11px] leading-none text-muted-foreground sm:w-16 sm:shrink-0" aria-hidden>
        {label}
      </span>
      {children}
    </div>
  )
}

/** Frames between two measurements of the piece (it changes with a load, not with a frame). */
const MEASURE_EVERY_FRAMES = 15

/**
 * Fit camera to scene bounds; registers ref for manual zoom-extents. Also
 * owns two things that depend on the size of the piece (0.6.3.1), measured
 * together with one reused box, at the first frame that has content and then
 * every `MEASURE_EVERY_FRAMES` frames:
 *  - the first fit can come before the piece is in the scene (it is attached a
 *    moment later, and drei measures a made-up box of the camera's distance
 *    for an empty scene), so a small piece was left as a dot. Until the user
 *    moves the camera, the view is fitted again whenever the size of the piece
 *    changes (`sizeChanged`);
 *  - the camera planes follow the camera: drei's `clip` sets them once, for the
 *    distance of the fit, so zooming close to a face cut it away. Each frame
 *    they are a function of the distance to the orbit target and the radius of
 *    the piece (`depthRange`; no measuring in the frame, only that distance).
 */
function FitCameraController({
  fitRef,
  contentRef,
}: {
  fitRef: React.MutableRefObject<(() => void) | null>
  /** The group of the piece: its box is the size of the piece. */
  contentRef: React.RefObject<THREE.Group | null>
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

  const box = useMemo(() => new THREE.Box3(), [])
  const extent = useMemo(() => new THREE.Vector3(), [])
  const radius = useRef(0)
  const fittedSize = useRef(0)
  const touched = useRef(false)
  const frames = useRef(0)
  useEffect(() => {
    const events = controls as unknown as {
      addEventListener: (type: string, listener: () => void) => void
      removeEventListener: (type: string, listener: () => void) => void
    } | null
    if (!events) return
    const touch = () => { touched.current = true }
    events.addEventListener('start', touch)
    return () => events.removeEventListener('start', touch)
  }, [controls])
  useFrame((state) => {
    const content = contentRef.current
    if (hasFit.current && content
        && (radius.current === 0 || frames.current % MEASURE_EVERY_FRAMES === 0)) {
      box.setFromObject(content)
      if (!box.isEmpty()) {
        const diagonal = box.getSize(extent).length()
        if (Number.isFinite(diagonal) && diagonal > 0) radius.current = diagonal / 2
        if (!touched.current && sizeChanged(fittedSize.current, diagonal)) {
          fittedSize.current = diagonal
          fitToScene()
        }
      }
    }
    frames.current += 1
    const target = (state.controls as { target?: THREE.Vector3 } | null)?.target
    if (!target || radius.current === 0) return
    const { camera } = state
    const wanted = depthRange(camera.position.distanceTo(target), radius.current)
    if (depthChanged({ near: camera.near, far: camera.far }, wanted)) {
      camera.near = wanted.near
      camera.far = wanted.far
      camera.updateProjectionMatrix()
    }
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

/** What each deviation overlay shows (explained behind a "?", not in the panel). */
const OVERLAY_HELP: Record<Exclude<ProxyDisplay, 'off' | 'outline'>, string> = {
  distance: 'Signed distance from the scan to the proxy surface. Blue: the scan lies inside the proxy. '
    + 'Red: outside. White: on the surface. Full colour at the scale value shown.',
  normal_deviation: 'Mean angle between the scan surface direction and the proxy face. '
    + 'Light: parallel to the face. Dark: turned away from it, up to the scale value shown.',
  occupancy: 'Number of scan points in each cell of the face. Light: few. Dark: many, '
    + 'on a log scale up to the value shown.',
}

/** A hull measures the depth of the scan below its surface, never negative. */
const HULL_DISTANCE_HELP = 'Depth of the scan below the hull surface (the concavity), never negative, '
  + 'so the map shows red only. White: on the hull. Full colour at the scale value shown.'

function overlayHelp(display: keyof typeof OVERLAY_HELP, primitive: string): string {
  return display === 'distance' && primitive === 'hull' ? HULL_DISTANCE_HELP : OVERLAY_HELP[display]
}

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

  // the faces sit a hair behind their edges (0.6.3.1)
  const material = bodyFaceMaterial(hasColors)

  const mesh = new THREE.Mesh(geometry, material)
  mesh.name = meshLabel

  const object = new THREE.Group()
  object.add(mesh)
  {
    const edgeGeometry = new THREE.EdgesGeometry(geometry)
    const edgeMaterial = edgeLineMaterial()
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

/** A bar with the index of the layout record it comes from (RL3). */
type ViewerBar = ReinforcementBar & { layout: number }

const ReinforcementBarMesh = React.memo(({ bar, colour }: { bar: ReinforcementBar; colour: string | null }) => {
  const material = reinforcementMaterial(colour)
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
          material={material}
        >
          <cylinderGeometry
            args={[radius, radius, segment.height, REINFORCEMENT_RADIAL_SEGMENTS]}
          />
        </mesh>
      ))}
      {cornerJoints.map((joint, index) => (
        <mesh key={`joint-${index}`} position={joint} material={material}>
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
  mode,
}: {
  bars: ViewerBar[]
  visible: boolean
  mode: BarColourMode
}) => {
  const range = useMemo(() => diameterRange(bars), [bars])
  if (!visible || bars.length === 0) return null
  return (
    <group scale={[scale, scale, scale]} rotation={[-Math.PI / 2, 0, 0]}>
      {bars.map((bar, index) => (
        <ReinforcementBarMesh key={`${bar.spec}-${index}`} bar={bar} colour={barColour(mode, bar, range)} />
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
  opacity,
}: {
  pointClouds: PointCloud[]
  visiblePointClouds: boolean[]
  /** This viewer's copies of the cached clouds (they are faded already). */
  externalPointClouds: THREE.Group[]
  pointCloudGeometryMode: PointCloudGeometryMode
  isLoadingExternal: boolean
  opacity: number
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
  // the inline groups are this viewer's own: fade them in place
  useLayoutEffect(() => {
    inlineGroups.forEach((group) => group.traverse((object) => {
      const material = (object as THREE.Points).material as THREE.Material | undefined
      if (material) applyOpacity(material, opacity)
    }))
  }, [inlineGroups, opacity])

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
  showEdges,
  opacity,
}: {
  primitiveDraws: PrimitiveDrawBuffers[]
  meshGeometryMode: GeometryMode
  visibleMeshes?: boolean[]
  externalMeshes?: THREE.Group[]
  isLoadingExternal?: boolean
  geometryError?: string | null
  showEdges: boolean
  opacity: number
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

        const material = bodyFaceMaterial(!!rawColors && rawColors.length > 0)

        const edgeGeometry = new THREE.EdgesGeometry(geom)
        const edgeMaterial = edgeLineMaterial()
        // both are built here for this viewer alone: fade them in place
        applyOpacity(material, opacity)
        applyOpacity(edgeMaterial, opacity)

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
  /** The primary proxy, as the solid and the overlay draw it (8.85). */
  proxyShape: ProxyShape | null
  /** The mesh switch is Off: no proxy solid, no edges. */
  meshOff: boolean
  /** Opacity of the piece in percent (8.165 C). */
  opacity: number
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
  const primitiveDraws = snapshotMeshesToDrawBuffers(snapshotMeshesFromGeometry(sg))
  const pointClouds = snapshotPointCloudsFromGeometry(sg)

  const hasMeshes = primitiveDraws.length > 0
  const hasPointClouds = pointClouds.length > 0

  // the proxy stands in when there is nothing else, or when chosen (8.23)
  if (props.proxyShape && (props.meshGeometryMode === 'proxy' || !hasMeshes)) {
    const [r, g, b] = snapshotPrismRgb(snapshot)
    return (
      <>
        <ProxySolid
          shape={props.proxyShape}
          color={rgbToHex(r, g, b)}
          showMesh={!props.meshOff}
          showEdges={props.showEdges && !props.meshOff}
          opacity={props.opacity}
        />
        <PointCloudVisualization
          pointClouds={pointClouds}
          visiblePointClouds={props.visiblePointClouds ?? []}
          externalPointClouds={props.externalPointClouds ?? []}
          pointCloudGeometryMode={props.pointCloudGeometryMode}
          isLoadingExternal={props.isLoadingExternalPointClouds ?? false}
          opacity={props.opacity}
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
          opacity={props.opacity}
        />
        <PointCloudVisualization
          pointClouds={pointClouds}
          visiblePointClouds={props.visiblePointClouds ?? []}
          externalPointClouds={props.externalPointClouds ?? []}
          pointCloudGeometryMode={props.pointCloudGeometryMode}
          isLoadingExternal={props.isLoadingExternalPointClouds ?? false}
          opacity={props.opacity}
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
        opacity={props.opacity}
      />
      <PointCloudVisualization
        pointClouds={pointClouds}
        visiblePointClouds={props.visiblePointClouds ?? []}
        externalPointClouds={props.externalPointClouds ?? []}
        pointCloudGeometryMode={props.pointCloudGeometryMode}
        isLoadingExternal={props.isLoadingExternalPointClouds ?? false}
        opacity={props.opacity}
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
  /**
   * Position picking (decision 8.43): a click or tap that is not a drag
   * reports the hit in the stored coordinates of the snapshot on screen.
   */
  picking?: { enabled: boolean; onPick: (hit: PickHit | null) => void }
  /** Positions drawn for the snapshot they name (stored coordinates). */
  marks?: ViewerMark[]
  /** Fill the parent's height (the picker dialog) instead of the page heights. */
  fill?: boolean
  /**
   * The component page (decision 8.118): the viewer carries a toolbar (detail
   * level, orientation, an Overlay menu) instead of the settings panel beside it.
   */
  toolbar?: boolean
  /**
   * The compact preview (decision 8.141 a): the viewport alone, rotate and
   * zoom, without a toolbar or the settings panel.
   */
  bare?: boolean
}

export default function ComponentViewer({
  catalog,
  compactDesktop = false,
  picking,
  marks = [],
  fill = false,
  toolbar = false,
  bare = false,
}: ComponentViewerProps) {
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
  const proxyShape = useProxyShape(overlayProxy as unknown as ProxyDoc | null)
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
    || proxyShape !== null
    || snapshotPointClouds.length > 0

  // picking starts on the reduced mesh where one exists: cleaner faces than the
  // preview and far lighter than the original (decision 8.83 d)
  const hasReducedMesh = plyPrimitiveIndicesForMode(snapshotRouting?.mesh_ply_resolutions, 'reduced').length > 0
  const [meshGeometryMode, setMeshGeometryMode] = useState<GeometryMode>(
    picking && hasReducedMesh ? 'reduced' : 'preview',
  )
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
  // Off of the detail switches: a display state, the level chosen stays (8.165 C);
  // a piece with a mesh starts with its point cloud hidden, as it always did
  const [meshOff, setMeshOff] = useState<boolean>(false)
  const [pointCloudOff, setPointCloudOff] = useState<boolean>(
    () => pointCloudStartsOff(snapshotMeshes.length),
  )
  const [showGrid, setShowGrid] = useState<boolean>(true)
  const [turntableEnabled, setTurntableEnabled] = useState<boolean>(false)
  // opacity of the piece in percent (8.165 C): body layers only, per viewer
  const [opacity, setOpacity] = useState<number>(OPACITY_DEFAULT)
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
  const pointCloudOffSeedRef = useRef(
    `${identityId?.toString() ?? ''}:${primitivePointCloudCount}`,
  )

  const snapshotMeshCacheKey = useMemo(() => {
    if (!snapshotRouting?.snapshot_id) return ''
    return `${snapshotRouting.snapshot_id}:${JSON.stringify(snapshotRouting.mesh_ply_resolutions ?? null)}`
  }, [snapshotRouting])

  // a proxy only: no preview and no files to switch to
  const isProxyOnly = snapshotMeshes.length === 0 && snapshotPointClouds.length === 0
  const hasMultipleMeshes = primitiveMeshCount > 0
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
  const [reinforcementBars, setReinforcementBars] = useState<ViewerBar[]>([])
  const [barLayouts, setBarLayouts] = useState<BarLayout[]>([])
  const [barColourMode, setBarColourMode] = useState<BarColourMode>('steel')
  const [showReinforcement, setShowReinforcement] = useState<boolean>(true)
  // positions of the published evidence on this snapshot (8.43)
  const [evidenceMarks, setEvidenceMarks] = useState<ViewerMark[]>([])
  const [showEvidenceMarks, setShowEvidenceMarks] = useState<boolean>(true)
  const pickRootRef = useRef<THREE.Group>(null)
  useEffect(() => {
    let cancelled = false
    setEvidenceMarks([])
    if (!identityId || !snapshotIdForOverlays) return
    fetch(`/api/backend/identities/${encodeURIComponent(String(identityId))}/evidence`, {
      credentials: 'include',
    })
      .then((response) => (response.ok ? response.json() : []))
      .then((records: unknown) => {
        if (!cancelled) setEvidenceMarks(publishedMarks(records, snapshotIdForOverlays))
      })
      .catch(() => { if (!cancelled) setEvidenceMarks([]) })
    return () => { cancelled = true }
  }, [identityId, snapshotIdForOverlays])
  useEffect(() => {
    let cancelled = false
    setReinforcementBars([])
    setBarLayouts([])
    if (!identityId || !snapshotIdForOverlays) return
    const params = new URLSearchParams({ method: 'reinforcement_layout' })
    fetch(`/api/backend/identities/${encodeURIComponent(String(identityId))}/evidence?${params}`, {
      credentials: 'include',
    })
      .then((response) => (response.ok ? response.json() : []))
      .then((records: {
        _id?: string
        observed_at?: string | null
        observed_at_precision?: string | null
        position?: { snapshot_id?: string | null }
        payload?: { bars?: ReinforcementBar[]; document?: { title?: string | null } | null }
      }[]) => {
        if (cancelled) return
        // one layout per record (RL3); a record without drawable bars is no layout
        // one layout per record (RL1), every bar of every layout drawn
        const { bars, layouts } = layoutsOnSnapshot<ReinforcementBar>(records, snapshotIdForOverlays)
        setReinforcementBars(bars)
        setBarLayouts(layouts)
        setBarColourMode(defaultColourMode(layouts.length))
      })
      .catch(() => { if (!cancelled) { setReinforcementBars([]); setBarLayouts([]) } })
    return () => { cancelled = true }
  }, [identityId, snapshotIdForOverlays])
  const hasReinforcement = reinforcementBars.length > 0
  const legend = hasReinforcement && showReinforcement
    ? barLegend(barColourMode, barLayouts, reinforcementBars)
    : null


  useEffect(() => {
    let isMounted = true
    const visibilitySeed = `${identityId?.toString() ?? ''}:${primitiveMeshCount}`
    const resetVisibilityToDefault =
      meshVisibilitySeedRef.current !== visibilitySeed
    // an Off layer loads nothing and leaves its visibility alone: it must not
    // use up the reset either, so that after a version switch while Off the
    // new version's default visibility applies when the mesh is switched back
    // on (0.6.3.1)
    const meshHeldByOff = isMeshExternalMode && meshOff && !isProxyOnly && !!identityId
    if (!meshHeldByOff) meshVisibilitySeedRef.current = visibilitySeed

    if (meshHeldByOff) {
      // Off hides and loads nothing, also not after a version switch; the
      // level is fetched when the mesh is switched back on (0.6.3.1)
      setIsLoadingExternalMeshes(false)
    } else if (isMeshExternalMode && shouldLoadLevel({
      external: isMeshExternalMode, off: meshOff, proxyOnly: isProxyOnly, hasIdentity: !!identityId,
    })) {
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
    meshOff,
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
    // as for the mesh, an Off cloud holding a stored level does not use up the
    // reset of its visibility (0.6.3.1); the Off switch itself starts again
    // for another piece at once (a seed of its own)
    const cloudHeldByOff = isPointCloudExternalMode && pointCloudOff && !isProxyOnly && !!identityId
    if (!cloudHeldByOff) pointCloudVisibilitySeedRef.current = visibilitySeed
    if (pointCloudOffSeedRef.current !== visibilitySeed) {
      pointCloudOffSeedRef.current = visibilitySeed
      setPointCloudOff(pointCloudStartsOff(primitiveMeshCount))
    }

    if (cloudHeldByOff) {
      // as for the mesh: Off loads nothing (0.6.3.1)
      setIsLoadingExternalPointClouds(false)
    } else if (shouldLoadLevel({
      external: isPointCloudExternalMode, off: pointCloudOff, proxyOnly: isProxyOnly, hasIdentity: !!identityId,
    })) {
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
                true,
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
          true,
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
    pointCloudOff,
    isProxyOnly,
    identityId,
    isPointCloudExternalMode,
    primitivePointCloudCount,
    hasPointClouds,
    primitiveMeshCount,
    snapshotRouting,
    snapshotMeshCacheKey,
  ])

  // Off hides the layer and loads nothing; the level chosen before stays
  const onMeshSwitch = (value: string) => {
    const next = chooseSwitch<GeometryMode>({ level: meshGeometryMode, off: meshOff }, value)
    setMeshOff(next.off)
    setMeshGeometryMode(next.level)
  }

  const onPointCloudSwitch = (value: string) => {
    const next = chooseSwitch<PointCloudGeometryMode>(
      { level: pointCloudGeometryMode, off: pointCloudOff },
      value,
    )
    setPointCloudOff(next.off)
    setPointCloudGeometryMode(next.level)
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

  const shownMeshes = useMemo(() => shownFlags(visibleMeshes, meshOff), [visibleMeshes, meshOff])
  const shownPointClouds = useMemo(
    () => shownFlags(visiblePointClouds, pointCloudOff),
    [visiblePointClouds, pointCloudOff],
  )

  const activePointCloudCount = isPointCloudExternalMode
    ? externalPointClouds.length
    : primitivePointCloudCount

  const activeMeshCount = isMeshExternalMode
    ? externalMeshes.length
    : primitiveMeshCount

  // the loaders cache these across viewers: draw (and fade) this viewer's copies
  const meshCopies = useViewerCopies(externalMeshes, opacity)
  const pointCloudCopies = useViewerCopies(externalPointClouds, opacity)

  useEffect(() => {
    if (!isMeshExternalMode) return
    meshCopies.forEach((group) => {
      group.traverse((obj) => {
        if ((obj as THREE.LineSegments).isLineSegments && obj.name.endsWith('_edges')) {
          obj.visible = showEdges
        }
      })
    })
  }, [showEdges, isMeshExternalMode, meshCopies])

  if (!canRenderViewport) {
    return <ComponentViewerSkeleton message="No Geometry Available" />
  }

  // only the levels this snapshot has (decision 8.23)
  const storedMeshFiles = new Set(
    Object.values(snapshotRouting?.mesh_ply_resolutions ?? {}).flat(),
  )
  const meshDetailLevels: GeometryMode[] = [
    ...(proxyShape ? ['proxy' as const] : []),
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

  const meshSwitchOptions = withOff(meshDetailOptions)
  const meshSwitchValue = switchValue({ level: meshGeometryMode, off: meshOff })
  const pointCloudSwitchOptions = withOff(pointCloudDetailOptions)
  const pointCloudSwitchValue = switchValue({ level: pointCloudGeometryMode, off: pointCloudOff })
  const hasMeshOrProxy = hasMeshSwitch(primitiveMeshCount, proxyShape !== null)

  const primaryProxy = (snapshotGeometry.proxies ?? []).find((proxy) => proxy.role === 'primary')
    ?? snapshotGeometry.proxies?.[0]

  const meshCount = activeMeshCount || primitiveMeshCount
  const pointCloudCount = activePointCloudCount || primitivePointCloudCount
  const hasEvidenceMarks = evidenceMarks.length > 0
  const hasOverlays = hasMarkerPoints || hasFixtures || hasReinforcement || hasEvidenceMarks

  // items are numbered only when there is more than one (8.23)
  const meshLabel = (index: number) => `Mesh ${index + 1}`
  const pointCloudLabel = (index: number) => `Point cloud ${index + 1}`

  const displayBlocks: React.ReactNode[] = []

  // the proxy is the mesh shown when it is chosen, or when nothing else is stored
  const showingProxy = proxyShape !== null && (meshGeometryMode === 'proxy' || !hasMultipleMeshes)
  // the switch of the mesh: levels and Off (in the panel a title above it names it)
  const meshSwitchControl = (label?: string) => (
    <SegmentedControl
      id="meshGeometryModeSelect"
      label={label}
      accessibleName="Mesh"
      value={meshSwitchValue}
      onValueChange={onMeshSwitch}
      options={meshSwitchOptions}
    />
  )

  if (showingProxy && !hasMultipleMeshes && primaryProxy) {
    displayBlocks.push(
      <MenuSubsection key="proxy" title="Proxy">
        <p className="text-xs text-muted-foreground">
          Showing: {primaryProxy.primitive} proxy ({primaryProxy.fit.method})
        </p>
        {!toolbar && meshSwitchControl('Mesh')}
      </MenuSubsection>,
    )
  }

  const listsMeshes = !showingProxy && meshCount > 1
  if (hasMultipleMeshes && (!toolbar || listsMeshes)) {
    displayBlocks.push(
      <MenuSubsection key="meshes" title={listsMeshes ? `Meshes (${meshCount})` : 'Mesh'}>
        {!toolbar && meshSwitchControl()}
        {listsMeshes && (
          <>
            <CheckboxControl
              id="toggle-all-meshes"
              label="Show all"
              checked={allMeshesVisible}
              onChange={toggleAllMeshes}
              disabled={meshOff}
            />
            <ScrollableCheckboxList
              items={Array.from({ length: meshCount }, (_, i) => i).map((index: number) => ({
                id: String(index),
                label: meshLabel(index),
                checked: visibleMeshes[index] || false,
                disabled: meshOff,
              }))}
              onToggle={(id) => toggleMeshVisibility(Number(id))}
            />
          </>
        )}
      </MenuSubsection>,
    )
  }

  if (hasPointClouds && (!toolbar || pointCloudCount > 1)) {
    if (displayBlocks.length > 0) {
      displayBlocks.push(<MenuDivider key="divider-pc" />)
    }
    displayBlocks.push(
      <MenuSubsection
        key="point-clouds"
        title={pointCloudCount > 1 ? `Point clouds (${pointCloudCount})` : 'Point cloud'}
      >
        {!toolbar && (
          <SegmentedControl
            id="pointCloudGeometryModeSelect"
            accessibleName="Point cloud"
            value={pointCloudSwitchValue}
            onValueChange={onPointCloudSwitch}
            disabled={isProxyOnly}
            options={pointCloudSwitchOptions}
          />
        )}
        {pointCloudCount > 1 && (
          <>
            <CheckboxControl
              id="toggle-all-point-clouds"
              label="Show all"
              checked={allPointCloudsVisible}
              onChange={toggleAllPointClouds}
              disabled={pointCloudOff}
            />
            <ScrollableCheckboxList
              items={Array.from({ length: pointCloudCount }, (_, index) => ({
                id: String(index),
                label: pointCloudLabel(index),
                checked: visiblePointClouds[index] || false,
                disabled: pointCloudOff,
              }))}
              onToggle={(id) => togglePointCloudVisibility(Number(id))}
            />
          </>
        )}
      </MenuSubsection>,
    )
  }

  if (displayBlocks.length > 0) {
    displayBlocks.push(<MenuDivider key="divider-opacity" />)
  }
  displayBlocks.push(
    <OpacitySlider
      key="opacity"
      value={opacity}
      onChange={setOpacity}
      nothingShown={visibleBodyLayers({
        showingProxy,
        showProxyMesh: !meshOff,
        showEdges: showEdges && !meshOff,
        visibleMeshes: shownMeshes,
        visiblePointClouds: shownPointClouds,
      }).length === 0}
    />,
  )

  const orientationHelp = `${snapshot.bbx && snapshot.bbx[2] > snapshot.bbx[0]
    ? 'Canonical: a standing column, its length along z.'
    : 'Canonical: longest side along x, shortest along z.'} As stored: the geometry as it was captured. The stored geometry is never turned; this only changes the view.`

  if (snapshotFrame && !toolbar) {
    if (displayBlocks.length > 0) {
      displayBlocks.push(<MenuDivider key="divider-orientation" />)
    }
    displayBlocks.push(
      <MenuSubsection
        key="orientation"
        title="Orientation"
        help={`${snapshot.bbx && snapshot.bbx[2] > snapshot.bbx[0]
          ? 'Canonical: a standing column, its length along z.'
          : 'Canonical: longest side along x, shortest along z.'} As stored: the geometry as it was captured. The stored geometry is never turned; this only changes the view.`}
      >
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
        {snapshot.bbx && (
          <p className="text-xs text-muted-foreground">
            {snapshot.bbx.map((v: number) => Math.round(v)).join(' x ')} mm
          </p>
        )}
      </MenuSubsection>,
    )
  }

  // the deviation overlays compare a scan with its proxy: a piece with an
  // authored proxy only has nothing to overlay (0.6.0.2)
  if (overlayProxy && proxyShape && !isProxyOnly) {
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
        {!toolbar && (
          <InfoLine
            label="Proxy fit"
            help={'The proxy is the simple shape fitted to the scan. The word in brackets names the fitting method. '
              + 'p95: 95 % of the scan points lie within this distance of the proxy surface. '
              + 'max: the distance of the farthest scan point.'}
          >
            {overlayProxy.primitive} ({fit.method})
            {fit.p95_mm != null
              ? `: p95 ${fit.p95_mm.toFixed(1)} mm, max ${(fit.max_mm ?? 0).toFixed(1)} mm`
              : ''}
          </InfoLine>
        )}
        {proxyRange != null && proxyDisplay !== 'off' && proxyDisplay !== 'outline' && (
          <InfoLine label="Colour scale" help={overlayHelp(proxyDisplay, overlayProxy.primitive)}>
            {proxyDisplay === 'distance'
              ? `Scale +/-${proxyRange.toFixed(1)} ${unit}`
              : `Scale 0 to ${proxyRange.toFixed(proxyDisplay === 'occupancy' ? 0 : 1)} ${unit}`}
          </InfoLine>
        )}
        {deviationError && (
          <p className="text-xs text-destructive">Deviation maps unavailable ({deviationError}).</p>
        )}
      </MenuSubsection>,
    )
  }

  // Show edges is one entry, here; it has no effect while the mesh is Off
  const edges = edgesControl(showEdges, meshOff)
  const noScan = isProxyOnly && !hasOverlays
  if (hasOverlays || hasMeshOrProxy || noScan) {
    if (displayBlocks.length > 0) {
      displayBlocks.push(<MenuDivider key="divider-overlays" />)
    }
    displayBlocks.push(
      <MenuSubsection key="overlays" title="Overlays">
        {hasMeshOrProxy && (
          <CheckboxControl
            id="toggle-edges"
            label="Show edges"
            checked={edges.checked}
            disabled={edges.disabled}
            onChange={(checked) => setShowEdges(checked)}
          />
        )}
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
        {hasReinforcement && showReinforcement && (
          <SegmentedControl
            id="reinforcement-colours"
            label="Bar colours"
            value={barColourMode}
            onValueChange={(value) => setBarColourMode(value as BarColourMode)}
            options={BAR_COLOUR_OPTIONS}
          />
        )}
        {hasEvidenceMarks && (
          <CheckboxControl
            id="toggle-evidence-marks"
            label={`Test positions (${evidenceMarks.length})`}
            checked={showEvidenceMarks}
            onChange={(checked) => setShowEvidenceMarks(checked)}
          />
        )}
        {noScan && (
          <p className="text-xs text-muted-foreground">No scan: overlays need a mesh or point cloud.</p>
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

  const desktopViewportClass = fill
    ? 'h-full min-h-[16rem]'
    : compactDesktop
      ? 'h-[30dvh] sm:h-[40dvh] md:h-[50dvh] 2xl:h-[56vh]'
      : 'h-[30dvh] sm:h-[40dvh] md:h-[50dvh]'

  // the toolbar of the component page (8.118): detail level, orientation and
  // an Overlay menu in place of the settings panel
  const toolbarBar = toolbar ? (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Viewer">
      {hasMeshOrProxy && (
        <ToolbarSwitch label="Mesh">
          <div className="w-full max-w-[22rem] sm:w-auto sm:min-w-[19rem]">
            <SegmentedControl
              id="meshGeometryModeSelect"
              accessibleName="Mesh"
              value={meshSwitchValue}
              onValueChange={onMeshSwitch}
              options={meshSwitchOptions}
            />
          </div>
        </ToolbarSwitch>
      )}
      {hasPointClouds && !isProxyOnly && (
        <ToolbarSwitch label="Point cloud">
          <div className="w-full max-w-[16rem] sm:w-auto sm:min-w-[13rem]">
            <SegmentedControl
              id="pointCloudGeometryModeSelect"
              accessibleName="Point cloud"
              value={pointCloudSwitchValue}
              onValueChange={onPointCloudSwitch}
              options={pointCloudSwitchOptions}
            />
          </div>
        </ToolbarSwitch>
      )}
      {snapshotFrame && (
        <div className="flex items-center gap-1" title={orientationHelp}>
          <SegmentedControl
            id="orientationSelect"
            value={orientation}
            onValueChange={(value) => setOrientation(value as 'stored' | 'canonical')}
            options={[
              { value: 'stored', label: 'As stored' },
              { value: 'canonical', label: 'Canonical' },
            ]}
          />
          <Help label="Orientation" text={orientationHelp} />
        </div>
      )}
      {hasDisplayOptions && (
        <Popover>
          <PopoverTrigger asChild>
            <Button type="button" variant="outline" size="sm" className="h-6 gap-1 px-2 text-[11px]">
              <SlidersHorizontal className="h-3 w-3" />
              Overlay
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="max-h-[70vh] w-72 overflow-y-auto p-3">
            <div className="flex flex-col gap-3 text-xs">{displayBlocks}</div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  ) : null

  return (
    <div className={cn('flex flex-col md:flex-row gap-2 w-full', fill && 'h-full', toolbar && 'md:flex-col')}>
      {toolbarBar}
      {hasDisplayOptions && !toolbar && !bare && (
        <div
          className={cn(
            'w-full md:w-64 md:flex-shrink-0 order-2 md:order-1',
            fill ? 'hidden md:block md:h-full' : 'md:h-[50dvh]',
            !fill && compactDesktop && '2xl:h-[56vh]',
          )}
        >
          <ViewerMenu sections={menuSections} className="h-full" />
        </div>
      )}

      <Card className={cn('overflow-hidden order-1 md:order-2 p-0', toolbar ? 'w-full' : 'flex-1', desktopViewportClass)}>
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
          {legend && (
            <div className="pointer-events-none absolute bottom-2 left-2 z-10 max-w-[70%] rounded-md border border-border bg-background/90 px-2 py-1.5 text-[11px] shadow-sm backdrop-blur-sm"
              role="group" aria-label="Bar colours">
              {legend.kind === 'layout' ? (
                <ul className="space-y-0.5">
                  {legend.items.map((item) => (
                    <li key={item.label} className="flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: item.colour }} aria-hidden />
                      <span className="truncate">{item.label}</span>
                      <span className="text-muted-foreground">{item.count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="w-36">
                  <div className="h-2.5 rounded-sm" aria-hidden
                    style={{ background: `linear-gradient(to right, ${legend.stops.join(', ')})` }} />
                  <div className="mt-0.5 flex justify-between tabular-nums text-muted-foreground">
                    <span>{legend.min} mm</span>
                    <span>{legend.max} mm</span>
                  </div>
                </div>
              )}
            </div>
          )}
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
            <FitCameraController fitRef={fitCameraRef} contentRef={pickRootRef} />
            <Turntable enabled={turntableEnabled}>
              <group ref={pickRootRef} matrixAutoUpdate={false} matrix={orientationMatrix}>
              <VisualizeComponent
                catalog={catalog}
                meshGeometryMode={meshGeometryMode}
                pointCloudGeometryMode={pointCloudGeometryMode}
                visibleMeshes={shownMeshes}
                visiblePointClouds={shownPointClouds}
                externalMeshes={isMeshExternalMode ? meshCopies : []}
                externalPointClouds={isPointCloudExternalMode ? pointCloudCopies : []}
                isLoadingExternalMeshes={isLoadingExternalMeshes}
                isLoadingExternalPointClouds={isLoadingExternalPointClouds}
                meshGeometryError={meshGeometryError}
                showEdges={showEdges}
                proxyShape={proxyShape}
                meshOff={meshOff}
                opacity={opacity}
              />
              {/* overlays are context, not the component: never a pick target (8.43) */}
              <group userData={{ noPick: true }}>
                <MarkerPoints markerPoints={markerPoints} visible={showMarkerPoints} />
                <CaptureFixtures fixtures={fixtureGroups} visible={showFixtures} />
                <ReinforcementBars bars={reinforcementBars} visible={showReinforcement} mode={barColourMode} />
              </group>
              {showEvidenceMarks && (
                <EvidenceMarks marks={evidenceMarks} snapshotId={snapshotIdForOverlays} />
              )}
              <EvidenceMarks marks={marks} snapshotId={snapshotIdForOverlays} />
              {proxyShape && (
                <group userData={{ noPick: true }}>
                  <ProxyOverlay
                    shape={proxyShape}
                    display={proxyDisplay}
                    maps={deviationMaps}
                    onRange={setProxyRange}
                  />
                </group>
              )}
              </group>
            </Turntable>
          </Bounds>

          {picking && (
            <PickLayer rootRef={pickRootRef} enabled={picking.enabled} onPick={picking.onPick} />
          )}
          <axesHelper args={[0.1]} />
          {showGrid && <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />}
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </Card>
    </div>
  )
}
