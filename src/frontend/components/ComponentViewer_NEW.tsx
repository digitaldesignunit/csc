'use client'

import { Canvas } from '@react-three/fiber'
import { useMemo, useState, useEffect } from 'react'
import * as THREE from 'three'
import { ComponentData } from './models'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { Bounds, OrbitControls } from '@react-three/drei'
import { Card } from './ui/card'
import { OBJLoader } from 'three-stdlib'
import { MTLLoader } from 'three-stdlib'

// Scale factor because THREE unit system is in meters
const scale = 0.001

// Enum for mesh types
const MESH_TYPES = {
  PRIMITIVE: 'primitive',
  REDUCED: 'reduced',
  DETAILED: 'detailed',
}

// Function to load external mesh with MTL
const loadExternalMesh = async (url: string, objFileName: string, mtlFileName: string) => {
  const mtlLoader = new MTLLoader()
  const materials = await mtlLoader.loadAsync(`${url}/${mtlFileName}`)
  materials.preload()

  const objLoader = new OBJLoader()
  objLoader.setMaterials(materials)
  const mesh = await objLoader.loadAsync(`${url}/${objFileName}`)

  return mesh
}

// VisualizeMesh Component
const VisualizeMesh = ({ component_data, meshType }: { component_data: ComponentData, meshType: string }) => {
  const [externalMesh, setExternalMesh] = useState<THREE.Group | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Load external mesh if meshType is reduced or detailed
  useEffect(() => {
    if (meshType === MESH_TYPES.REDUCED || meshType === MESH_TYPES.DETAILED) {
      const baseUrl = process.env.NEXT_PUBLIC_COMPONENT_GEOMETRY_BASE_URL
      const componentId = component_data._id
      const url = `${baseUrl}/${componentId}`

      const objFileName = meshType === MESH_TYPES.REDUCED ? 'mesh_reduced.obj' : 'mesh.obj'
      const mtlFileName = meshType === MESH_TYPES.REDUCED ? 'mesh_reduced.mtl' : 'mesh.mtl'

      setIsLoading(true)
      loadExternalMesh(url, objFileName, mtlFileName)
        .then((mesh) => {
          setExternalMesh(mesh)
        })
        .catch((error) => {
          console.error(`Failed to load ${meshType} mesh:`, error)
          setExternalMesh(null)
        })
        .finally(() => {
          setIsLoading(false)
        })
    }
  }, [component_data._id, meshType])

  // Get component color from data and convert to hex for display
  const component_color = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

  // Primitive mesh geometry (default)
  const mesh_geometry = useMemo(() => {
    if (meshType !== MESH_TYPES.PRIMITIVE) return null

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

    mesh_geometry.rotateX(-Math.PI / 2)
    mesh_geometry.computeVertexNormals()

    return mesh_geometry
  }, [component_data, meshType])

  if (isLoading) {
    return <div>Loading {meshType} mesh...</div>
  }

  if (meshType !== MESH_TYPES.PRIMITIVE && externalMesh) {
    return <primitive object={externalMesh} scale={0.001} />
  }

  if (mesh_geometry) {
    return (
      <mesh geometry={mesh_geometry}>
        <meshBasicMaterial color={component_color} vertexColors={!!component_data.geometry.mesh.c} side={THREE.DoubleSide} />
      </mesh>
    )
  }

  return null
}

// VisualizeSheet Component (unchanged)
const VisualizeSheet = ({ component_data }: { component_data: ComponentData }) => {
  const pline_shape = useMemo(() => {
    const pline_shape = new THREE.Shape()
    const points = component_data.geometry.extrusion.profile
    pline_shape.moveTo(points[0][0] * scale, points[0][1] * scale)
    points.forEach(([x, y], index) => {
      if (index > 0) pline_shape.lineTo(x * scale, y * scale)
    })
    return pline_shape
  }, [component_data])

  const extrude_geometry = useMemo(() => {
    const extrudeSettings = {
      steps: 2,
      depth: component_data.geometry.extrusion.height * scale,
      bevelEnabled: false,
    }
    const geometry = new THREE.ExtrudeGeometry(pline_shape, extrudeSettings)
    geometry.translate(0, 0, -component_data.geometry.extrusion.height * scale * 0.5)
    geometry.rotateX(-Math.PI / 2)
    return geometry
  }, [pline_shape, component_data.geometry.extrusion.height])

  const component_color = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

  return (
    <mesh geometry={extrude_geometry}>
      <meshStandardMaterial color={new THREE.Color(component_color)} />
    </mesh>
  )
}

// VisualizeComponent with control element for mesh types
const VisualizeComponent = ({ component_data }: { component_data: ComponentData }) => {
  const [meshType, setMeshType] = useState(MESH_TYPES.PRIMITIVE)

  if (component_data.type === 'sheet') {
    return <VisualizeSheet component_data={component_data} />
  }

  return (
    <div>
      <div style={{ marginBottom: '1em' }}>
        <label htmlFor="meshType">Select Mesh Detail: </label>
        <select id="meshType" value={meshType} onChange={(e) => setMeshType(e.target.value)}>
          <option value={MESH_TYPES.PRIMITIVE}>Primitive</option>
          <option value={MESH_TYPES.REDUCED}>Reduced</option>
          <option value={MESH_TYPES.DETAILED}>Detailed</option>
        </select>
      </div>
      <VisualizeMesh component_data={component_data} meshType={meshType} />
    </div>
  )
}

export default function ComponentViewer({ component_data }: { component_data: ComponentData }) {
  return (
    <>
      {component_data.geometry == undefined ? (
        <ComponentViewerSkeleton message="No Geometry Available" />
      ) : (
        <Card className="flex h-[40dvh] m-2">
          <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
            <ambientLight intensity={Math.PI / 2} />
            <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
            <Bounds fit clip observe margin={1.2}>
              <VisualizeComponent component_data={component_data} />
            </Bounds>
            <axesHelper args={[0.1]} />
            <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
            <OrbitControls makeDefault />
          </Canvas>
        </Card>
      )}
    </>
  )
}
