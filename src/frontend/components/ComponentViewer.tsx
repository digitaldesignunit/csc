'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { ComponentPolylinePoints, ComponentData } from './models'
import { Card } from './ui/card'
import { Bounds, OrbitControls, Html } from '@react-three/drei'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { MTLLoader, OBJLoader } from 'three-stdlib'
import { Skeleton } from './ui/skeleton'

// Scale factor for converting units to meters in THREE
const scale: number = 0.001

// Simple in-memory cache for external geometry
const externalGeometryCache = new Map<string, THREE.Group | null>()

function ensureNormals(object: THREE.Object3D) {
  object.traverse((child: THREE.Object3D) => {
    if ((child as any).isMesh && (child as any).geometry) {
      const geometry = (child as any).geometry as THREE.BufferGeometry
      geometry.computeVertexNormals()
      geometry.normalizeNormals()
    }
  })
}

async function loadExternalGeometry(
  baseUrl: string,
  componentId: string,
  mode: 'reduced' | 'detailed'
): Promise<THREE.Group | null> {
  const cacheKey = `${componentId}:${mode}`
  if (externalGeometryCache.has(cacheKey)) {
    return externalGeometryCache.get(cacheKey) ?? null
  }

  // Decide routes
  const geometryRoute =
    mode === 'reduced'
      ? 'fetch-component-geometry-reduced'
      : 'fetch-component-geometry-detailed'
  const mtlRoute =
    mode === 'reduced'
      ? 'fetch-component-mtl-reduced'
      : 'fetch-component-mtl-detailed'

  const objUrl = `${baseUrl}/api/${geometryRoute}?component_id=${componentId}`
  const mtlUrl = `${baseUrl}/api/${mtlRoute}?component_id=${componentId}`

  try {
    const mtlLoader = new MTLLoader()
    // Ensure we handle texture references
    mtlLoader.setResourcePath(
      `${baseUrl}/api/fetch-component-texture?component_id=${componentId}&texture=`
    )

    const materials = await mtlLoader.loadAsync(mtlUrl)
    materials.preload()

    const objLoader = new OBJLoader()
    objLoader.setMaterials(materials)
    const object = await objLoader.loadAsync(objUrl)

    // Scale (Rhino -> meters)
    object.scale.set(scale, scale, scale)
    ensureNormals(object)

    externalGeometryCache.set(cacheKey, object)
    return object
  } catch (error) {
    console.error('Failed to load external geometry:', error)
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
  geometryMode: 'primitive' | 'reduced' | 'detailed'
}) => {
  const [externalObject, setExternalObject] = useState<THREE.Group | null>(null)
  const [isLoadingExternal, setIsLoadingExternal] = useState(false)

  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'

  useEffect(() => {
    let isMounted = true
    if (isExternalMode && component_data.type !== 'sheet') {
      const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || ''
      if (!baseUrl || !component_data._id) return

      setIsLoadingExternal(true)
      loadExternalGeometry(baseUrl, component_data._id.toString(), geometryMode).then(obj => {
        if (isMounted) {
          setExternalObject(obj)
          setIsLoadingExternal(false)
        }
      })
    } else {
      setExternalObject(null)
      setIsLoadingExternal(false)
    }
    return () => { isMounted = false }
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
              <Skeleton className='h-full rounded-xl m-2 flex items-center justify-center'>
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
  geometryMode: 'primitive' | 'reduced' | 'detailed'
}) {
  if (!component_data.geometry) return null
  if (component_data.type === 'sheet') {
    return <VisualizeSheet component_data={component_data} />
  } else {
    return <VisualizeMesh component_data={component_data} geometryMode={geometryMode} />
  }
}

/** 
 * BoundingBoxMesh:
 *  - Renders a semi-transparent box if showBoundingBox is true.
 *  - Reads .bbx.x, .bbx.y, .bbx.z from component_data
 *  - Scales by `scale`, places the box near [0,0,0].
 */
function BoundingBoxMesh({
  component_data,
  show,
}: {
  component_data: ComponentData
  show: boolean
}) {
  if (!show) return null

  // Assume component_data.bbx.x, .y, .z exist:
  const sizeX = (component_data.bbx[1][0] - component_data.bbx[0][0]) * scale
  const sizeY = (component_data.bbx[1][2] - component_data.bbx[0][2]) * scale
  const sizeZ = (component_data.bbx[1][1] - component_data.bbx[0][1]) * scale

  // Create a box geometry of that size
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
  

  // Position it so it encloses the object around the origin (if your object is near the origin)
  return (
    <>
      <mesh geometry={bbx_geometry} material={bbx_material} />
      <lineSegments geometry={bbx_edge_geometry} material={bbx_edge_material} />
    </>
  )
}

/**
 * ComponentViewer
 * - Overlays a fixed UI (dropdown + checkbox) over the canvas (absolute).
 * - This UI does NOT move/zoom with the 3D scene.
 */
export default function ComponentViewer({ component_data }: { component_data: ComponentData }) {
  const [geometryMode, setGeometryMode] = useState<'primitive' | 'reduced' | 'detailed'>('primitive')
  const [showBoundingBox, setShowBoundingBox] = useState(false)

  const isSheet = component_data.type === 'sheet'

  if (!component_data.geometry) {
    return <ComponentViewerSkeleton message="No Geometry Available" />
  }

  return (
    <Card className="flex flex-col m-2">
      {/* We wrap the canvas in a relative container so we can absolutely position the overlay */}
      <div className="relative h-[40dvh]">
        {/* ABSOLUTE overlay that doesn't move with the scene */}
        <div className="absolute top-2 left-2 z-10 bg-white bg-opacity-90 p-2 rounded shadow text-sm">
          
          {/* Geometry Mode Dropdown */}
          <div className="flex flex-col gap-1 mb-2">
            <label htmlFor="geometryModeSelect" className="mr-2">Geometry Resolution:</label>
            <select
              id="geometryModeSelect"
              value={geometryMode}
              onChange={(e) => setGeometryMode(e.target.value as any)}
              disabled={isSheet}
              className="border text-sm rounded p-1 w-full"
            >
              <option value="primitive">Primitive</option>
              <option value="reduced">Reduced</option>
              <option value="detailed">Detailed</option>
            </select>
          </div>

          {/* Display Bounding Box Checkbox */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="bboxCheckbox"
              checked={showBoundingBox}
              onChange={(e) => setShowBoundingBox(e.target.checked)}
            />
            <label htmlFor="bboxCheckbox">Display BoundingBox</label>
          </div>
        </div>

        <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight
            position={[10, 10, 10]}
            angle={0.15}
            penumbra={1}
            decay={0}
            intensity={Math.PI * 0.75}
          />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds fit clip observe margin={1.2} maxDuration={1}>
            {/* The main object */}
            <VisualizeComponent component_data={component_data} geometryMode={geometryMode} />

            {/* If user toggles bounding box, show it */}
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
