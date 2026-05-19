'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { CatalogComponent, SnapshotMesh } from '@/generated/CatalogModels'
import type { SnapshotMeshRouting } from '@/generated/catalogExtras'
import { snapshotMeshRoutingFromSnapshot } from '@/generated/catalogExtras'
import { Card } from '@/components/ui/card'
import { Bounds, OrbitControls, Html } from '@react-three/drei'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ViewerMenu, MenuSection, SelectControl, ScrollableCheckboxList, CheckboxControl } from '@/components/viewer/ViewerMenu'

// Scale factor for converting units to meters in THREE
const scale = 0.001

// Simple in-memory cache for external geometry with ETag support
interface CachedGeometry {
  meshes: THREE.Group[] | null
  etag?: string
  timestamp: number
}

const externalGeometryCache = new Map<string, CachedGeometry>()

// Helpers

type GeometryMode = 'primitive' | 'reduced' | 'detailed'

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

type GeometryLoadResult = {
  success: true
  meshes: THREE.Group[]
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

async function loadExternalGeometry(
  identityId: string,
  mode: Exclude<GeometryMode, 'primitive'>,
  snapshotRouting: SnapshotMeshRouting | null,
): Promise<GeometryLoadResult> {
  debugLog(`Loading ${mode} PLY geometry for identity ${identityId}`)

  const hint = meshHintForCache(snapshotRouting)
  const cacheKey = `${identityId}:${mode}:${hint}`
  const cached = externalGeometryCache.get(cacheKey)

  if (cached && cached.meshes) {
    debugLog(`Using cached geometry for ${identityId}: ${cached.meshes.length} meshes`)
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
    externalGeometryCache.set(cacheKey, {
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
      externalGeometryCache.set(cacheKey, {
        meshes: plyResult.meshes,
        etag: plyResult.etag,
        timestamp: Date.now(),
      })
      debugLog(`Loaded ${plyResult.meshes.length} mesh(es) from PLY`)
      return { success: true, meshes: plyResult.meshes }
    }
  } catch (err) {
    debugLog('PLY pipeline failed:', err)
  }

  externalGeometryCache.set(cacheKey, {
    meshes: null,
    etag: undefined,
    timestamp: Date.now(),
  })
  return {
    success: false,
    error: 'not_found',
    message: `No ${mode} PLY meshes in snapshot manifest`,
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
      g.computeVertexNormals()
      g.normalizeNormals()
      return g
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

const VisualizeMultipleMeshes = React.memo(({
  primitiveDraws,
  geometryMode,
  visibleMeshes = [],
  externalMeshes = [],
  isLoadingExternal = false,
  geometryError = null,
  showEdges
}: {
  primitiveDraws: PrimitiveDrawBuffers[]
  geometryMode: GeometryMode
  visibleMeshes?: boolean[]
  externalMeshes?: THREE.Group[]
  isLoadingExternal?: boolean
  geometryError?: string | null
  showEdges: boolean
}) => {
  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'

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
  geometryMode: GeometryMode
  visibleMeshes?: boolean[]
  externalMeshes?: THREE.Group[]
  isLoadingExternal?: boolean
  geometryError?: string | null
  showEdges: boolean
}

function snapshotExtrusionRgb(snap: CatalogComponent['snapshot']): [number, number, number] {
  const c = snap.color
  return [
    Array.isArray(c) ? (c[0] as number) : 110,
    Array.isArray(c) ? (c[1] as number) : 110,
    Array.isArray(c) ? (c[2] as number) : 110,
  ]
}

function VisualizeComponent(props: VisualizeProps) {
  const sg = props.catalog.snapshot.geometry
  const ext = sg.extrusions?.[0]
  const meshesApi = sg.meshes ?? []
  const primitiveDraws = snapshotMeshesToDrawBuffers(meshesApi)

  const hasExtrusion =
    !!ext?.profile?.length && typeof ext.height === 'number' && Number.isFinite(ext.height)
  const hasMeshes = primitiveDraws.length > 0

  if (hasExtrusion) {
    return (
      <ExtrusionVisualization
        profile={ext!.profile}
        height={ext!.height}
        colorRgb={snapshotExtrusionRgb(props.catalog.snapshot)}
      />
    )
  }
  if (hasMeshes) {
    return (
      <VisualizeMultipleMeshes
        primitiveDraws={primitiveDraws}
        geometryMode={props.geometryMode}
        visibleMeshes={props.visibleMeshes}
        externalMeshes={props.externalMeshes}
        isLoadingExternal={props.isLoadingExternal}
        geometryError={props.geometryError}
        showEdges={props.showEdges}
      />
    )
  }
  if (props.catalog.identity.type === 'panel') {
    return (
      <ExtrusionVisualization
        profile={ext?.profile ?? []}
        height={typeof ext?.height === 'number' ? ext!.height : 0}
        colorRgb={snapshotExtrusionRgb(props.catalog.snapshot)}
      />
    )
  }
  return (
    <VisualizeMultipleMeshes
      primitiveDraws={primitiveDraws}
      geometryMode={props.geometryMode}
      visibleMeshes={props.visibleMeshes}
      externalMeshes={props.externalMeshes}
      isLoadingExternal={props.isLoadingExternal}
      geometryError={props.geometryError}
      showEdges={props.showEdges}
    />
  )
}

/**
 * Catalog 3D viewer: **`GET /identities/{id}/compose`** payload (`identity` + `snapshot`).
 * Reduced/detailed modes load **`GET /snapshots/{snapshot_id}/meshes/...`** PLY only.
 */
export type ComponentViewerProps = { catalog: CatalogComponent }

export default function ComponentViewer({ catalog }: ComponentViewerProps) {
  const identityId = catalog.identity._id
  const catalogType = catalog.identity.type

  const snapshotRouting = useMemo(
    () => snapshotMeshRoutingFromSnapshot(catalog.snapshot),
    [catalog.snapshot],
  )

  const canRenderViewport =
    !!(catalog.snapshot.geometry.meshes?.length || catalog.snapshot.geometry.extrusions?.length)

  const [geometryMode, setGeometryMode] = useState<GeometryMode>('primitive')
  const [visibleMeshes, setVisibleMeshes] = useState<boolean[]>([])
  const [externalMeshes, setExternalMeshes] = useState<THREE.Group[]>([])
  const [isLoadingExternal, setIsLoadingExternal] = useState(false)
  const [geometryError, setGeometryError] = useState<string | null>(null)
  const [showMarkerPoints, setShowMarkerPoints] = useState<boolean>(true)
  const [showEdges, setShowEdges] = useState<boolean>(true)

  const primitiveMeshCount = useMemo(
    () => catalog.snapshot.geometry.meshes?.length ?? 0,
    [catalog.snapshot.geometry.meshes],
  )

  const snapshotMeshCacheKey = useMemo(() => {
    if (!snapshotRouting?.snapshot_id) return ''
    return `${snapshotRouting.snapshot_id}:${JSON.stringify(snapshotRouting.mesh_ply_resolutions ?? null)}`
  }, [snapshotRouting])

  const isPanel = catalogType === 'panel'
  const hasMultipleMeshes = primitiveMeshCount > 0
  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'

  const markerPoints = useMemo(() => {
    const points = catalog.snapshot.geometry.marker_points
    if (Array.isArray(points) && points.length > 0) {
      return points.filter((point) => Array.isArray(point) && point.length >= 3)
    }
    return []
  }, [catalog.snapshot.geometry.marker_points])

  const hasMarkerPoints = markerPoints.length > 0

  useEffect(() => {
    let isMounted = true
    if (isExternalMode && catalogType !== 'panel' && identityId) {
      setIsLoadingExternal(true)
      setGeometryError(null)
      setShowEdges(false)
      loadExternalGeometry(
        identityId.toString(),
        geometryMode,
        snapshotRouting,
      )
        .then((result) => {
          if (isMounted) {
            if (result.success) {
              setExternalMeshes(result.meshes)
              setGeometryError(null)
              setVisibleMeshes(new Array(result.meshes.length).fill(true))
            } else {
              setExternalMeshes([])
              setGeometryError(result.message)
              setVisibleMeshes([])
            }
            setIsLoadingExternal(false)
          }
        })
        .catch(() => {
          if (isMounted) {
            setExternalMeshes([])
            setGeometryError(`Failed to load ${geometryMode} geometry`)
            setVisibleMeshes([])
            setIsLoadingExternal(false)
          }
        })
    } else {
      setExternalMeshes([])
      setIsLoadingExternal(false)
      setGeometryError(null)
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
    geometryMode,
    catalogType,
    identityId,
    isExternalMode,
    primitiveMeshCount,
    hasMultipleMeshes,
    snapshotRouting,
    snapshotMeshCacheKey,
  ])

  const onModeChange: React.ChangeEventHandler<HTMLSelectElement> = (e) => {
    const v = e.target.value as GeometryMode
    setGeometryMode(v)
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

  const allMeshesVisible = useMemo(
    () => visibleMeshes.length > 0 && visibleMeshes.every((v) => v),
    [visibleMeshes],
  )

  useEffect(() => {
    if (!isExternalMode) return
    externalMeshes.forEach((group) => {
      group.traverse((obj) => {
        if ((obj as THREE.LineSegments).isLineSegments && obj.name.endsWith('_edges')) {
          obj.visible = showEdges
        }
      })
    })
  }, [showEdges, isExternalMode, externalMeshes])

  if (!canRenderViewport) {
    return <ComponentViewerSkeleton message="No Geometry Available" />
  }

  const menuSections: MenuSection[] = [
    {
      id: 'geometry-mode',
      content: (
        <SelectControl
          id="geometryModeSelect"
          label="Geometry Resolution:"
          value={geometryMode}
          onChange={onModeChange}
          disabled={isPanel}
          options={[
            { value: 'primitive', label: 'Primitive' },
            { value: 'reduced', label: 'Reduced' },
            { value: 'detailed', label: 'Detailed' },
          ]}
        />
      ),
    },
  ]

  if ((hasMultipleMeshes && geometryMode === 'primitive') || (isExternalMode && externalMeshes.length > 0)) {
    const meshCount = isExternalMode ? externalMeshes.length : primitiveMeshCount
    menuSections.push({
      id: 'global-toggles',
      content: (
        <div className="flex flex-col gap-1">
          <CheckboxControl
            id="toggle-all-meshes"
            label="Show All Meshes"
            checked={allMeshesVisible}
            onChange={toggleAllMeshes}
          />
          <CheckboxControl
            id="toggle-edges"
            label="Show Edges"
            checked={showEdges}
            onChange={(checked) => setShowEdges(checked)}
          />
        </div>
      ),
    })
    menuSections.push({
      id: 'mesh-visibility',
      title: 'Mesh Visibility',
      collapsible: true,
      defaultExpanded: true,
      itemCount: meshCount,
      content: (
        <ScrollableCheckboxList
          items={(isExternalMode
            ? Array.from({ length: externalMeshes.length }, (_, i) => i)
            : Array.from({ length: primitiveMeshCount }, (_, i) => i)
          ).map((index: number) => ({
            id: String(index),
            label: isExternalMode
              ? (
                  externalMeshes[index]?.children[0]?.name ||
                  `External Mesh ${index + 1}`
                )
              : `Mesh ${index + 1}`,
            checked: visibleMeshes[index] || false,
          }))}
          onToggle={(id) => toggleMeshVisibility(Number(id))}
        />
      ),
    })
  }

  if (hasMarkerPoints) {
    menuSections.push({
      id: 'marker-points',
      title: 'Marker Points:',
      content: (
        <CheckboxControl
          id="toggle-marker-points"
          label={`Show (${markerPoints.length})`}
          checked={showMarkerPoints}
          onChange={(checked) => setShowMarkerPoints(checked)}
        />
      ),
    })
  }

  return (
    <div className="flex flex-col md:flex-row gap-2 w-full">
      <div className="w-full md:w-64 md:flex-shrink-0 order-2 md:order-1 md:h-[50dvh]">
        <ViewerMenu sections={menuSections} className="h-full" />
      </div>

      <Card className="flex-1 overflow-hidden order-1 md:order-2 h-[30dvh] sm:h-[40dvh] md:h-[50dvh] p-0">
        <div className="relative w-full h-full">
          <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds fit clip observe margin={1.2} maxDuration={1}>
            <VisualizeComponent
              catalog={catalog}
              geometryMode={geometryMode}
              visibleMeshes={visibleMeshes}
              externalMeshes={isExternalMode ? externalMeshes : []}
              isLoadingExternal={isLoadingExternal}
              geometryError={geometryError}
              showEdges={showEdges}
            />
            <MarkerPoints markerPoints={markerPoints} visible={showMarkerPoints} />
          </Bounds>

          <axesHelper args={[0.1]} />
          <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </Card>
    </div>
  )
}
