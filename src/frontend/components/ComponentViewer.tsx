'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { ComponentPolylinePoints, ComponentData } from './models'
import { Card } from './ui/card'
import { Bounds, OrbitControls, Html } from '@react-three/drei'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { MTLLoader } from 'three-stdlib'
import { OBJLoader } from 'three-stdlib'

// Scale factor for converting units to meters in THREE
const scale: number = 0.001

// Simple in-memory cache for external geometry
// Key: `${componentId}:${mode}`, Value: THREE.Group | null
const externalGeometryCache = new Map<string, THREE.Group | null>()

// Helper function to ensure normals are computed and pointing outwards
function ensureNormals(object: THREE.Object3D) {
  object.traverse((child: THREE.Object3D) => {
    if ((child as any).isMesh && (child as any).geometry) {
      const geometry = (child as any).geometry as THREE.BufferGeometry
      geometry.computeVertexNormals()
      geometry.normalizeNormals()
    }
  })
}

// Helper function to load external OBJ/MTL geometry
async function loadExternalGeometry(
  baseUrl: string,
  componentId: string,
  mode: 'reduced' | 'detailed'
): Promise<THREE.Group | null> {

  // Check cache first
  const cacheKey = `${componentId}:${mode}`
  if (externalGeometryCache.has(cacheKey)) {
    return externalGeometryCache.get(cacheKey) ?? null
  }

  const objName = mode === 'reduced' ? 'mesh_reduced.obj' : 'mesh.obj'
  const mtlName = mode === 'reduced' ? 'mesh_reduced.mtl' : 'mesh.mtl'
  
  const objUrl = `${baseUrl}/${componentId}/${objName}`
  const mtlUrl = `${baseUrl}/${componentId}/${mtlName}`

  try {
    const mtlLoader = new MTLLoader()
    const materials = await mtlLoader.loadAsync(mtlUrl)
    materials.preload()

    const objLoader = new OBJLoader()
    objLoader.setMaterials(materials)
    const object = await objLoader.loadAsync(objUrl)

    // Align scale and orientation with primitive geometry
    object.scale.set(scale, scale, scale)
    object.rotateX(-Math.PI / 2)

    // Compute and normalize normals for external geometry
    ensureNormals(object)

    // Store result in cache
    externalGeometryCache.set(cacheKey, object)

    return object
  } catch (error) {
    console.error('Failed to load external geometry:', error)
    // Store null in cache so we don’t keep retrying
    externalGeometryCache.set(cacheKey, null)
    return null
  }
}

/**
 * VisualizeMesh component:
 * - Displays a 3D mesh of the component in THREE.js.
 * - If geometryMode is "reduced" or "detailed", attempts to load external geometry.
 * - Shows a loading indicator while external geometry is being fetched.
 * - Falls back to primitive geometry if external geometry fails to load.
 * - Caches external geometry to prevent re-fetching on subsequent switches.
 */
const VisualizeMesh = React.memo((
  { component_data, geometryMode }: {
    component_data: ComponentData,
    geometryMode: 'primitive' | 'reduced' | 'detailed'
  }
) => {
  const [externalObject, setExternalObject] = useState<THREE.Group | null>(null)
  const [isLoadingExternal, setIsLoadingExternal] = useState(false)

  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'

  // Load external geometry if needed
  useEffect(() => {
    let isMounted = true

    if (isExternalMode && component_data.type !== 'sheet') {
      const baseUrl = process.env.NEXT_PUBLIC_COMPONENT_GEOMETRY_BASE_URL || ''
      if (!baseUrl || !component_data._id) return

      setIsLoadingExternal(true)
      loadExternalGeometry(baseUrl, component_data._id.toString(), geometryMode).then(obj => {
        if (isMounted) {
          setExternalObject(obj)
          setIsLoadingExternal(false)
        }
      })
    } else {
      // Not external mode, no need to load external geometry
      setExternalObject(null)
      setIsLoadingExternal(false)
    }
    return () => { isMounted = false }
  }, [geometryMode, component_data, isExternalMode])

  // Create primitive mesh geometry as fallback or for primitive mode
  const mesh_geometry = useMemo(() => {
    const mesh_geometry = new THREE.BufferGeometry()

    const vertices = component_data.geometry.mesh.v
    const flatVertices = vertices.flat().map((v) => v * scale)
    const verticesAttribute = new THREE.Float32BufferAttribute(flatVertices, 3)
    mesh_geometry.setAttribute('position', verticesAttribute)

    const faces = component_data.geometry.mesh.f
    const flatFaces = faces.flat()
    mesh_geometry.setIndex(flatFaces)

    const colors = component_data.geometry.mesh.c
    if (colors && colors.length === vertices.length) {
      const flatColors = colors.flatMap((color) => color.map((v) => v / 255))
      const colorAttribute = new THREE.Float32BufferAttribute(flatColors, 3)
      mesh_geometry.setAttribute('color', colorAttribute)
    }

    // Adjust orientation and compute normals
    mesh_geometry.rotateX(-Math.PI / 2)
    mesh_geometry.computeVertexNormals()
    mesh_geometry.normalizeNormals()

    return mesh_geometry
  }, [component_data])

  const component_color = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

  const mesh_material = useMemo(() => {
    return new THREE.MeshBasicMaterial({
      color: component_color,
      vertexColors: component_data.geometry.mesh.c ? true : false,
      side: THREE.DoubleSide,
    })
  }, [component_color, component_data.geometry.mesh.c])

  const edge_geometry = useMemo(() => {
    return new THREE.EdgesGeometry(mesh_geometry)
  }, [mesh_geometry])

  const edge_material = useMemo(() => {
    return new THREE.LineBasicMaterial({ color: 0x000000 })
  }, [])

  // Rendering logic:
  if (isExternalMode) {
    // If loading external geometry, show loading indicator
    if (isLoadingExternal) {
      return (
        <mesh>
          <Html center style={{ background: 'rgba(255,255,255,0.8)', padding: '5px', borderRadius: '5px' }}>
            Loading external geometry...
          </Html>
        </mesh>
      )
    }

    // If external object loaded successfully, show it
    if (externalObject) {
      return <primitive object={externalObject} />
    }

    // If external loading failed, fallback to primitive
    return (
      <>
        <mesh visible geometry={mesh_geometry} material={mesh_material} />
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </>
    )
  } else {
    // Primitive mode only
    return (
      <>
        <mesh visible geometry={mesh_geometry} material={mesh_material} />
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </>
    )
  }
})

/**
 * VisualizeSheet component:
 * - Displays a "sheet" type component as an extrusion.
 * - Sheets don't support external geometry modes, so we keep it simple.
 */
const VisualizeSheet = React.memo(({ component_data }: { component_data: ComponentData }) => {
  const pline_shape = useMemo(() => {
    const pline_shape = new THREE.Shape()
    const points: ComponentPolylinePoints = component_data.geometry.extrusion.profile
    pline_shape.moveTo(points[0][0] * scale, points[0][1] * scale)
    points.forEach((pointtuple: number[], index) => {
      if (index > 0) {
        pline_shape.lineTo(pointtuple[0] * scale, pointtuple[1] * scale)
      }
    })
    return pline_shape
  }, [component_data]) 

  const extrude_geometry = useMemo(() => {
    const extrudeSettings = {
      steps: 2,
      depth: component_data.geometry.extrusion.height * scale,
      bevelEnabled: false,
    }
    const extrude_geometry = new THREE.ExtrudeGeometry(
      pline_shape,
      extrudeSettings
    )
    extrude_geometry.translate(
      0,
      0,
      -component_data.geometry.extrusion.height * scale * 0.5
    )
    extrude_geometry.rotateX(-Math.PI / 2)
    // Compute and normalize normals for the sheet geometry
    extrude_geometry.computeVertexNormals()
    extrude_geometry.normalizeNormals()
    return extrude_geometry
  }, [pline_shape, component_data.geometry.extrusion.height]) 

  const component_color = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

  const edge_geometry = useMemo(() => {
    return new THREE.EdgesGeometry(extrude_geometry)
  }, [extrude_geometry])

  const edge_material = useMemo(() => {
    return new THREE.LineBasicMaterial({ color: 0x000000 })
  }, [])

  return (
    <>
      <mesh visible geometry={extrude_geometry}>
        <meshStandardMaterial color={new THREE.Color(component_color)} />
      </mesh>
      <lineSegments geometry={edge_geometry} material={edge_material} />
    </>
  )
})

/**
 * VisualizeComponent:
 * - Chooses between VisualizeMesh and VisualizeSheet depending on component type.
 * - If it's a sheet, geometryMode does not matter (no external geometry).
 */
const VisualizeComponent = ({
  component_data,
  geometryMode
}: {
  component_data: ComponentData,
  geometryMode: 'primitive' | 'reduced' | 'detailed'
}) => {
  if (component_data.geometry == undefined) {
    return null
  } else {
    if (component_data.type == 'sheet') {
      // Sheets have no detailed geometry. Always show primitive.
      return <VisualizeSheet component_data={component_data} />
    } else {
      return <VisualizeMesh component_data={component_data} geometryMode={geometryMode} />
    }
  }
}

/**
 * ComponentViewer:
 * - Main viewer component that hosts the Canvas and controls.
 * - Provides a dropdown to switch geometryMode (primitive/reduced/detailed).
 * - If sheet, disables the dropdown.
 */
export default function ComponentViewer({
  component_data,
}: {
  component_data: ComponentData
}) {
  const [geometryMode, setGeometryMode] = useState<'primitive' | 'reduced' | 'detailed'>('primitive')
  const isSheet = component_data.type === 'sheet'

  return (
    <>
      {component_data.geometry == undefined ? (
        <ComponentViewerSkeleton message='No Geometry Available' />
      ) : (
        <Card className='flex flex-col m-2'>
          <div className="p-2">
            <label htmlFor="geometryModeSelect">Geometry Detail:</label>
            <select
              id="geometryModeSelect"
              value={geometryMode}
              onChange={(e) => setGeometryMode(e.target.value as 'primitive' | 'reduced' | 'detailed')}
              disabled={isSheet} 
              style={{ marginLeft: '0.5rem', opacity: isSheet ? 0.5 : 1 }}
            >
              <option value="primitive">Primitive</option>
              <option value="reduced">Reduced</option>
              <option value="detailed">Detailed</option>
            </select>
          </div>
          <div className='h-[40dvh]'>
            <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
              <ambientLight intensity={Math.PI / 2} />
              <spotLight
                position={[10, 10, 10]}
                angle={0.15}
                penumbra={1}
                decay={0}
                intensity={Math.PI * 0.75}
              />
              <pointLight
                position={[-10, 10, -10]}
                decay={0}
                intensity={Math.PI * 0.75}
              />
              <Bounds fit clip observe margin={1.2} maxDuration={1}>
                <VisualizeComponent component_data={component_data} geometryMode={geometryMode} />
              </Bounds>
              <axesHelper args={[0.1]} />
              <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
              <OrbitControls makeDefault />
            </Canvas>
          </div>
        </Card>
      )}
    </>
  )
}
