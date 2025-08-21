'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { ComponentPolylinePoints, ComponentData } from '@/components/common/models'
import { Card } from '@/components/ui/card'
import { Bounds, OrbitControls, Html } from '@react-three/drei'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { MTLLoader, OBJLoader } from 'three-stdlib'
import { Skeleton } from '@/components/ui/skeleton'

// Scale factor for converting units to meters in THREE
const scale = 0.001

// Simple in-memory cache for external geometry
const externalGeometryCache = new Map<string, THREE.Group | null>()

/* ───────── Type guards (no `any`) ───────── */

function isMesh(obj: THREE.Object3D): obj is THREE.Mesh<THREE.BufferGeometry, THREE.Material | THREE.Material[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (obj as any)?.isMesh === true
}
function isWithGeometry(obj: THREE.Object3D): obj is THREE.Mesh<THREE.BufferGeometry, THREE.Material | THREE.Material[]> {
  return isMesh(obj) && obj.geometry instanceof THREE.BufferGeometry
}
function isMaterial(m: unknown): m is THREE.Material {
  return !!m && typeof m === 'object' && 'uuid' in (m as Record<string, unknown>)
}
function isTexture(t: unknown): t is THREE.Texture {
  return !!t && typeof t === 'object' && 'isTexture' in (t as Record<string, unknown>)
}

/* ───────── Helpers ───────── */

function ensureNormals(object: THREE.Object3D) {
  object.traverse((child) => {
    if (isWithGeometry(child)) {
      const geometry = child.geometry
      geometry.computeVertexNormals()
      geometry.normalizeNormals()
    }
  })
}

type GeometryMode = 'primitive' | 'reduced' | 'detailed'

/** extend typings for optional three-stdlib APIs present in some versions */
type MTLLoaderWithOptional = MTLLoader & {
  setTexturePath?: (path: string) => void
  setWithCredentials?: (withCreds: boolean) => void
}
type OBJLoaderWithOptional = OBJLoader & {
  setWithCredentials?: (withCreds: boolean) => void
}

/* ───────── External geometry/mtl loading ───────── */

async function loadExternalGeometry(
  componentId: string,
  mode: Exclude<GeometryMode, 'primitive'>
): Promise<THREE.Group | null> {
  const cacheKey = `${componentId}:${mode}`
  if (externalGeometryCache.has(cacheKey)) {
    return externalGeometryCache.get(cacheKey) ?? null
  }

  const geometryRoute = mode === 'reduced' ? 'geometry_reduced' : 'geometry_detailed'
  const mtlRoute = mode === 'reduced' ? 'material_reduced' : 'material_detailed'

  const objUrl = `/api/backend/components/${componentId}/${geometryRoute}`
  const mtlUrl = `/api/backend/components/${componentId}/${mtlRoute}`

  try {
    const mtlLoader: MTLLoaderWithOptional = new MTLLoader() as MTLLoaderWithOptional
    // Let MTLLoader resolve map_Kd/etc via our texture proxy
    const textureBase = `/api/fetch-component-texture?component_id=${encodeURIComponent(componentId)}&texture=`
    mtlLoader.setResourcePath(textureBase)
    mtlLoader.setTexturePath?.(textureBase)
    mtlLoader.setWithCredentials?.(true)

    const materials = await mtlLoader.loadAsync(mtlUrl)
    materials.preload()

    const objLoader: OBJLoaderWithOptional = new OBJLoader() as OBJLoaderWithOptional
    objLoader.setWithCredentials?.(true)
    objLoader.setMaterials(materials)

    const object = await objLoader.loadAsync(objUrl)

    // make sure textures render correctly on modern three
    object.traverse((o) => {
      if (!isMesh(o)) return
      const mat = o.material
      const mats = Array.isArray(mat) ? mat : [mat]
      mats.forEach((mm) => {
        if (!isMaterial(mm)) return
        const maybeMap = (mm as unknown as { map?: unknown }).map
        if (isTexture(maybeMap)) {
          maybeMap.colorSpace = THREE.SRGBColorSpace
          maybeMap.needsUpdate = true
        }
      })
      if (isWithGeometry(o)) {
        const g = o.geometry
        if (!g.getAttribute('uv')) {
          // no UVs present -> texture cannot display
          // (do not throw; just warn)
          console.warn('OBJ mesh has no UVs; texture cannot display', o.name)
        }
      }
    })

    object.scale.set(scale, scale, scale)
    ensureNormals(object)

    externalGeometryCache.set(cacheKey, object)
    return object
  } catch (e) {
    console.error('Failed to load external geometry:', e)
    externalGeometryCache.set(cacheKey, null)
    return null
  }
}

/** 
 * VisualizeMesh 
 */
const VisualizeMesh = React.memo(({
  component_data,
  geometryMode
}: {
  component_data: ComponentData
  geometryMode: GeometryMode
}) => {
  const [externalObject, setExternalObject] = useState<THREE.Group | null>(null)
  const [isLoadingExternal, setIsLoadingExternal] = useState(false)

  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'

  useEffect(() => {
    let isMounted = true
    if (isExternalMode && component_data.type !== 'sheet') {
      if (!component_data._id) return
      setIsLoadingExternal(true)
      loadExternalGeometry(component_data._id.toString(), geometryMode)
        .then((obj) => {
          if (isMounted) {
            setExternalObject(obj)
            setIsLoadingExternal(false)
          }
        })
        .catch(() => {
          if (isMounted) {
            setExternalObject(null)
            setIsLoadingExternal(false)
          }
        })
    } else {
      setExternalObject(null)
      setIsLoadingExternal(false)
    }
    return () => {
      isMounted = false
    }
  }, [geometryMode, component_data, isExternalMode])

  // Primitive fallback geometry
  const mesh_geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const vertices = component_data.geometry.mesh.v
    const flatVertices = vertices.flat().map((v) => v * scale)
    g.setAttribute('position', new THREE.Float32BufferAttribute(flatVertices, 3))

    const faces = component_data.geometry.mesh.f
    g.setIndex(faces.flat())

    const colors = component_data.geometry.mesh.c
    if (colors && colors.length === vertices.length) {
      const flatColors = colors.flatMap((c) => c.map((v) => v / 255))
      g.setAttribute('color', new THREE.Float32BufferAttribute(flatColors, 3))
    }
    // Adjust orientation
    g.rotateX(-Math.PI / 2)
    g.computeVertexNormals()
    g.normalizeNormals()
    return g
  }, [component_data])

  const colorHex = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

  const mesh_material = useMemo(() => {
    return new THREE.MeshBasicMaterial({
      color: colorHex,
      vertexColors: !!component_data.geometry.mesh.c,
      side: THREE.DoubleSide
    })
  }, [colorHex, component_data.geometry.mesh.c])

  const edge_geometry = useMemo(() => new THREE.EdgesGeometry(mesh_geometry), [mesh_geometry])
  const edge_material = useMemo(() => new THREE.LineBasicMaterial({ color: 0x000000 }), [])

  if (isExternalMode) {
    if (isLoadingExternal) {
      return (
        <mesh>
          <Html center>
            <div
              style={{
                minWidth: '200px',
                padding: '8px',
                background: 'rgba(255,255,255,0.8)',
                borderRadius: '4px',
                textAlign: 'center',
              }}
            >
              <Skeleton className="h-full rounded-xl m-2 flex items-center justify-center">
                <strong>Loading geometry...</strong>
              </Skeleton>
            </div>
          </Html>
        </mesh>
      )
    }
    if (externalObject) {
      return <primitive object={externalObject} />
    }
    // fallback if external fail
    return (
      <>
        <mesh visible geometry={mesh_geometry} material={mesh_material} />
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </>
    )
  } else {
    // Primitive
    return (
      <>
        <mesh visible geometry={mesh_geometry} material={mesh_material} />
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </>
    )
  }
})
VisualizeMesh.displayName = 'VisualizeMesh'

/** 
 * VisualizeSheet 
 */
const VisualizeSheet = React.memo(({ component_data }: { component_data: ComponentData }) => {
  const pline_shape = useMemo(() => {
    const shape = new THREE.Shape()
    const points: ComponentPolylinePoints = component_data.geometry.extrusion.profile
    shape.moveTo(points[0][0] * scale, points[0][1] * scale)
    points.forEach((p, i) => {
      if (i > 0) shape.lineTo(p[0] * scale, p[1] * scale)
    })
    return shape
  }, [component_data])

  const extrude_geometry = useMemo(() => {
    const extrudeSettings = { steps: 2, depth: component_data.geometry.extrusion.height * scale, bevelEnabled: false }
    const g = new THREE.ExtrudeGeometry(pline_shape, extrudeSettings)
    g.translate(0, 0, -component_data.geometry.extrusion.height * scale * 0.5)
    g.rotateX(-Math.PI / 2)
    g.computeVertexNormals()
    g.normalizeNormals()
    return g
  }, [pline_shape, component_data.geometry.extrusion.height])

  const colorHex = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

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
})
VisualizeSheet.displayName = 'VisualizeSheet'

/** 
 * VisualizeComponent 
 */
function VisualizeComponent({
  component_data,
  geometryMode
}: {
  component_data: ComponentData
  geometryMode: GeometryMode
}) {
  if (!component_data.geometry) return null
  if (component_data.type === 'sheet') {
    return <VisualizeSheet component_data={component_data} />
  } else {
    return <VisualizeMesh component_data={component_data} geometryMode={geometryMode} />
  }
}

/** 
 * BoundingBoxMesh
 */
function BoundingBoxMesh({
  component_data,
  show,
}: {
  component_data: ComponentData
  show: boolean
}) {
  const sizeX = (component_data.bbx[1][0] - component_data.bbx[0][0]) * scale
  const sizeY = (component_data.bbx[1][2] - component_data.bbx[0][2]) * scale
  const sizeZ = (component_data.bbx[1][1] - component_data.bbx[0][1]) * scale

  const bbx_geometry = useMemo(() => new THREE.BoxGeometry(sizeX, sizeY, sizeZ), [sizeX, sizeY, sizeZ])
  const bbx_material = useMemo(() => {
    return new THREE.MeshBasicMaterial({
      color: 0xff0000,
      transparent: true,
      opacity: 0.2,
    })
  }, [])
  const bbx_edge_geometry = useMemo(() => new THREE.EdgesGeometry(bbx_geometry), [bbx_geometry])
  const bbx_edge_material = useMemo(() => new THREE.LineBasicMaterial({ color: 0x000000 }), [])

  if (!show) return null
  return (
    <>
      <mesh geometry={bbx_geometry} material={bbx_material} />
      <lineSegments geometry={bbx_edge_geometry} material={bbx_edge_material} />
    </>
  )
}

/**
 * ComponentViewer
 */
export default function ComponentViewer({ component_data }: { component_data: ComponentData }) {
  const [geometryMode, setGeometryMode] = useState<GeometryMode>('primitive')
  const [showBoundingBox, setShowBoundingBox] = useState(false)

  const isSheet = component_data.type === 'sheet'
  if (!component_data.geometry) {
    return <ComponentViewerSkeleton message="No Geometry Available" />
  }

  const onModeChange: React.ChangeEventHandler<HTMLSelectElement> = (e) => {
    const v = e.target.value as GeometryMode
    setGeometryMode(v)
  }

  return (
    <Card className="flex flex-col m-2 w-full overflow-x-auto">
      <div className="relative h-[40dvh]">
        {/* Overlay UI */}
        <div className="absolute top-2 left-2 z-10 bg-accent-foreground bg-opacity-90 p-2 rounded shadow text-sm max-w-[calc(100%-1rem)]">
          <div className="mb-2 flex flex-col gap-1">
            <label htmlFor="geometryModeSelect" className="mr-2 text-xs sm:text-sm">Geometry Resolution:</label>
            <select
              id="geometryModeSelect"
              value={geometryMode}
              onChange={onModeChange}
              disabled={isSheet}
              className="w-full rounded border bg-accent-foreground p-1 text-xs sm:text-sm"
            >
              <option value="primitive">Primitive</option>
              <option value="reduced">Reduced</option>
              <option value="detailed">Detailed</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="bboxCheckbox"
              checked={showBoundingBox}
              onChange={(e) => setShowBoundingBox(e.target.checked)}
            />
            <label htmlFor="bboxCheckbox" className="text-xs sm:text-sm">Display BoundingBox</label>
          </div>
        </div>

        <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds fit clip observe margin={1.2} maxDuration={1}>
            <VisualizeComponent component_data={component_data} geometryMode={geometryMode} />
            <BoundingBoxMesh component_data={component_data} show={showBoundingBox} />
          </Bounds>

          <axesHelper args={[0.1]} />
          <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </Card>
  )
}
