'use client'

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type {
  CatalogComponent,
  ComponentSnapshot,
  SnapshotExtrusion,
  SnapshotGeometry,
  SnapshotMesh,
  SnapshotPointCloud,
  SnapshotReinforcement,
} from '@/generated/CatalogModels'
import type { SnapshotMeshRouting } from '@/generated/catalogExtras'
import {
  primarySnapshot,
  snapshotMeshRoutingFromSnapshot,
} from '@/generated/catalogExtras'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Scan, Grid3x3 } from 'lucide-react'
import { Bounds, OrbitControls, Html, useBounds } from '@react-three/drei'
import { rgbToHex } from '@/lib/utils'
import {
  buildPointCloudThreeGroup,
  loadSnapshotPointCloudPlyGroups,
  snapshotPointCloudsFromGeometry,
} from '@/lib/pointCloudGeometry'
import {
  REINFORCEMENT_RADIAL_SEGMENTS,
  buildReinforcementBarMeshes,
  reinforcementSteelMaterial,
  snapshotReinforcementsFromGeometry,
} from '@/lib/reinforcementGeometry'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ViewerMenu, MenuSection, MenuSubsection, MenuDivider, SegmentedControl, ScrollableCheckboxList, CheckboxControl } from '@/components/viewer/ViewerMenu'

// Scale factor for converting units to meters in THREE
const scale = 0.001

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

type GeometryMode = 'primitive' | 'reduced' | 'detailed'
type PointCloudGeometryMode = 'primitive' | 'detailed'

function nextPointCloudVisibility(
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

/** Flat buffers for one mesh primitive (snapshot geometry). */
type PrimitiveDrawBuffers = {
  positionsFlat: number[]
  indices: number[]
  rawColors?: number[][]
}

function snapshotMeshesFromGeometry(geometry: SnapshotGeometry): SnapshotMesh[] {
  const meshes = geometry.meshes
  return Array.isArray(meshes) ? (meshes as SnapshotMesh[]) : []
}

function snapshotExtrusionsFromGeometry(
  geometry: SnapshotGeometry,
): SnapshotExtrusion[] {
  const extrusions = geometry.extrusions
  return Array.isArray(extrusions) ? (extrusions as SnapshotExtrusion[]) : []
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
  meshes: SnapshotMesh[],
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
  mode: Exclude<GeometryMode, 'primitive'>,
  manifest: Record<string, string[]> | null | undefined,
): Promise<{ ok: true; meshes: THREE.Group[]; etag?: string } | { ok: false }> {
  const resolution = mode === 'reduced' ? 'reduced' : 'detailed'
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
      const label = `PLY Mesh ${primitiveIndex + 1}`
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
  mode: Exclude<GeometryMode, 'primitive'>,
  snapshotRouting: SnapshotMeshRouting | null,
): Promise<MeshLoadResult> {
  debugLog(`Loading ${mode} PLY meshes for identity ${identityId}`)

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
      message: `No ${mode} PLY geometry available for this snapshot`,
    }
  }

  if (!snapshotRouting?.snapshot_id) {
    const msg = `No snapshot routing for ${mode} mode (compose payload missing current snapshot _id)`
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
    message: `No ${mode} PLY geometry available for this snapshot`,
  }
}

async function loadExternalPointClouds(
  identityId: string,
  snapshotRouting: SnapshotMeshRouting | null,
  pointCloudCount: number,
): Promise<PointCloudLoadResult> {
  debugLog(`Loading PLY point clouds for identity ${identityId}`)

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
      message: 'No PLY point cloud geometry available for this snapshot',
    }
  }

  if (!snapshotRouting?.snapshot_id) {
    const msg = 'No snapshot routing for point cloud PLY (compose payload missing current snapshot _id)'
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
    message: 'No PLY point cloud geometry available for this snapshot',
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

const ReinforcementBar = React.memo(({
  bar,
}: {
  bar: SnapshotReinforcement
}) => {
  const { segments, cornerJoints } = useMemo(
    () => buildReinforcementBarMeshes(bar.points),
    [bar.points, bar.diameter],
  )
  const radius = bar.diameter / 2

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
            args={[
              radius,
              radius,
              segment.height,
              REINFORCEMENT_RADIAL_SEGMENTS,
            ]}
          />
        </mesh>
      ))}
      {cornerJoints.map((joint, index) => (
        <mesh
          key={`joint-${index}`}
          position={joint}
          material={reinforcementSteelMaterial}
        >
          <sphereGeometry args={[radius, REINFORCEMENT_RADIAL_SEGMENTS, 12]} />
        </mesh>
      ))}
    </group>
  )
})
ReinforcementBar.displayName = 'ReinforcementBar'

const ReinforcementBars = React.memo(({
  reinforcements,
  visible,
}: {
  reinforcements: SnapshotReinforcement[]
  visible: boolean
}) => {
  if (!visible || reinforcements.length === 0) return null

  return (
    <group scale={[scale, scale, scale]} rotation={[-Math.PI / 2, 0, 0]}>
      {reinforcements.map((bar, index) => (
        <ReinforcementBar
          key={`${bar.spec}-${bar.diameter}-${index}`}
          bar={bar}
        />
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
  pointClouds: SnapshotPointCloud[]
  visiblePointClouds: boolean[]
  externalPointClouds: THREE.Group[]
  pointCloudGeometryMode: PointCloudGeometryMode
  isLoadingExternal: boolean
}) => {
  const isExternalMode = pointCloudGeometryMode === 'detailed'

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
  const isExternalMode = meshGeometryMode === 'reduced' || meshGeometryMode === 'detailed'

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

function snapshotExtrusionRgb(snap: ComponentSnapshot): [number, number, number] {
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
  const ext = snapshotExtrusionsFromGeometry(sg)[0]
  const primitiveDraws = snapshotMeshesToDrawBuffers(snapshotMeshesFromGeometry(sg))
  const pointClouds = snapshotPointCloudsFromGeometry(sg)

  const hasExtrusion =
    !!ext?.profile?.length && typeof ext.height === 'number' && Number.isFinite(ext.height)
  const hasMeshes = primitiveDraws.length > 0
  const hasPointClouds = pointClouds.length > 0

  if (hasExtrusion) {
    return (
      <>
        <ExtrusionVisualization
          profile={ext!.profile}
          height={ext!.height}
          colorRgb={snapshotExtrusionRgb(snapshot)}
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
  if (hasMeshes || hasPointClouds || props.catalog.identity.type === 'panel') {
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
 * Reduced/detailed mesh modes load **`GET /snapshots/{snapshot_id}/meshes/...`** PLY.
 * Detailed point cloud mode loads **`GET /snapshots/{snapshot_id}/point_clouds/...`** PLY.
 */
export type ComponentViewerProps = { catalog: CatalogComponent }

export default function ComponentViewer({ catalog }: ComponentViewerProps) {
  const snapshot = primarySnapshot(catalog)
  const identityId = catalog.identity._id
  const catalogType = catalog.identity.type

  const snapshotRouting = useMemo(
    () => snapshotMeshRoutingFromSnapshot(snapshot),
    [snapshot],
  )

  const snapshotGeometry = snapshot.geometry
  const snapshotMeshes = useMemo(
    () => snapshotMeshesFromGeometry(snapshotGeometry),
    [snapshotGeometry],
  )
  const snapshotExtrusions = useMemo(
    () => snapshotExtrusionsFromGeometry(snapshotGeometry),
    [snapshotGeometry],
  )
  const snapshotPointClouds = useMemo(
    () => snapshotPointCloudsFromGeometry(snapshotGeometry),
    [snapshotGeometry],
  )

  const canRenderViewport =
    snapshotMeshes.length > 0
    || snapshotExtrusions.length > 0
    || snapshotPointClouds.length > 0

  const [meshGeometryMode, setMeshGeometryMode] = useState<GeometryMode>('primitive')
  const [pointCloudGeometryMode, setPointCloudGeometryMode] = useState<PointCloudGeometryMode>('primitive')
  const [visibleMeshes, setVisibleMeshes] = useState<boolean[]>([])
  const [visiblePointClouds, setVisiblePointClouds] = useState<boolean[]>([])
  const [externalMeshes, setExternalMeshes] = useState<THREE.Group[]>([])
  const [externalPointClouds, setExternalPointClouds] = useState<THREE.Group[]>([])
  const [isLoadingExternalMeshes, setIsLoadingExternalMeshes] = useState(false)
  const [isLoadingExternalPointClouds, setIsLoadingExternalPointClouds] = useState(false)
  const [meshGeometryError, setMeshGeometryError] = useState<string | null>(null)
  const [showMarkerPoints, setShowMarkerPoints] = useState<boolean>(true)
  const [showReinforcements, setShowReinforcements] = useState<boolean>(true)
  const [showEdges, setShowEdges] = useState<boolean>(true)
  const [showGrid, setShowGrid] = useState<boolean>(true)
  const fitCameraRef = useRef<(() => void) | null>(null)

  const primitiveMeshCount = snapshotMeshes.length
  const primitivePointCloudCount = snapshotPointClouds.length
  const hasPointClouds = primitivePointCloudCount > 0
  const pointCloudVisibilitySeedRef = useRef(
    `${identityId?.toString() ?? ''}:${primitivePointCloudCount}`,
  )

  const snapshotMeshCacheKey = useMemo(() => {
    if (!snapshotRouting?.snapshot_id) return ''
    return `${snapshotRouting.snapshot_id}:${JSON.stringify(snapshotRouting.mesh_ply_resolutions ?? null)}`
  }, [snapshotRouting])

  const isPanel = catalogType === 'panel'
  const hasMultipleMeshes = primitiveMeshCount > 0
  const pointCloudVisibleByDefault = !hasMultipleMeshes
  const isMeshExternalMode = meshGeometryMode === 'reduced' || meshGeometryMode === 'detailed'
  const isPointCloudExternalMode = pointCloudGeometryMode === 'detailed'

  const markerPoints = useMemo(() => {
    const points = snapshot.geometry.marker_points
    if (Array.isArray(points) && points.length > 0) {
      return points.filter((point) => Array.isArray(point) && point.length >= 3)
    }
    return []
  }, [snapshot.geometry.marker_points])

  const hasMarkerPoints = markerPoints.length > 0

  const reinforcements = useMemo(
    () => snapshotReinforcementsFromGeometry(snapshot.geometry),
    [snapshot.geometry],
  )
  const hasReinforcements = reinforcements.length > 0

  useEffect(() => {
    let isMounted = true
    if (isMeshExternalMode && catalogType !== 'panel' && identityId) {
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
              setVisibleMeshes(new Array(result.meshes.length).fill(true))
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
        setVisibleMeshes(new Array(primitiveMeshCount).fill(true))
      } else {
        setVisibleMeshes([])
      }
    }
    return () => {
      isMounted = false
    }
  }, [
    meshGeometryMode,
    catalogType,
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

    if (isPointCloudExternalMode && catalogType !== 'panel' && identityId) {
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
              setVisiblePointClouds((prev) => nextPointCloudVisibility(
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
        setVisiblePointClouds((prev) => nextPointCloudVisibility(
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
    catalogType,
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

  const meshResolutionOptions = [
    { value: 'primitive', label: 'Primitive' },
    { value: 'reduced', label: 'Reduced' },
    { value: 'detailed', label: 'Detailed' },
  ]

  const pointCloudResolutionOptions = [
    { value: 'primitive', label: 'Primitive' },
    { value: 'detailed', label: 'Detailed' },
  ]

  const meshCount = activeMeshCount || primitiveMeshCount
  const pointCloudCount = activePointCloudCount || primitivePointCloudCount
  const hasOverlays = hasMarkerPoints || hasReinforcements

  const meshLabel = (index: number) => (
    isMeshExternalMode && externalMeshes[index]
      ? (
          externalMeshes[index]?.children[0]?.name ||
          `External Mesh ${index + 1}`
        )
      : `Mesh ${index + 1}`
  )

  const pointCloudLabel = (index: number) => (
    isPointCloudExternalMode
      ? (
          externalPointClouds[index]?.name ||
          `Point Cloud ${index + 1}`
        )
      : `Point Cloud ${index + 1}`
  )

  const displayBlocks: React.ReactNode[] = []

  if (hasMultipleMeshes) {
    displayBlocks.push(
      <MenuSubsection key="meshes" title={`Meshes (${meshCount})`}>
        <SegmentedControl
          id="meshGeometryModeSelect"
          label="Resolution"
          value={meshGeometryMode}
          onValueChange={onMeshModeChange}
          disabled={isPanel}
          options={meshResolutionOptions}
        />
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
            label={meshLabel(0)}
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
      <MenuSubsection key="point-clouds" title={`Point clouds (${pointCloudCount})`}>
        <SegmentedControl
          id="pointCloudGeometryModeSelect"
          label="Resolution"
          value={pointCloudGeometryMode}
          onValueChange={onPointCloudModeChange}
          disabled={isPanel}
          options={pointCloudResolutionOptions}
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
            label={pointCloudLabel(0)}
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
        {hasReinforcements && (
          <CheckboxControl
            id="toggle-reinforcements"
            label={`Reinforcement (${reinforcements.length})`}
            checked={showReinforcements}
            onChange={(checked) => setShowReinforcements(checked)}
          />
        )}
      </MenuSubsection>,
    )
  }

  const hasDisplayOptions = displayBlocks.length > 0

  const menuSections: MenuSection[] = hasDisplayOptions
    ? [{
        id: 'display',
        title: 'Display',
        content: <div className="flex flex-col gap-3">{displayBlocks}</div>,
      }]
    : []

  return (
    <div className="flex flex-col md:flex-row gap-2 w-full">
      {hasDisplayOptions && (
        <div className="w-full md:w-64 md:flex-shrink-0 order-2 md:order-1 md:h-[50dvh]">
          <ViewerMenu sections={menuSections} className="h-full" />
        </div>
      )}

      <Card className="flex-1 overflow-hidden order-1 md:order-2 h-[30dvh] sm:h-[40dvh] md:h-[50dvh] p-0">
        <div className="relative w-full h-full">
          <div className="absolute top-2 right-2 z-10 flex flex-col gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="secondary"
                  size="icon-xs"
                  className="h-7 w-7 bg-background/85 shadow-sm backdrop-blur-sm"
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
                  className={`h-7 w-7 shadow-sm backdrop-blur-sm ${
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
            <ReinforcementBars
              reinforcements={reinforcements}
              visible={showReinforcements}
            />
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
