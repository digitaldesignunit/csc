'use client'

import { Canvas, useFrame } from '@react-three/fiber'
import { useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { ComponentPolylinePoints } from './models'
import { Card } from './ui/card'
import { Bounds, OrbitControls } from '@react-three/drei'
import { ComponentData } from './models'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'

// Scale factor because THREE unit system is in meters
const scale: number = 0.001

const VisualizeMesh = (component_data: ComponentData) => {
  // Create mesh geometry on request
  const mesh_geometry = useMemo(() => {
    const mesh_geometry = new THREE.BufferGeometry()

    // Flatten the vertices array and add to the geometry
    const vertices = component_data.geometry.mesh.v
    const flatVertices = vertices.flat().map((v) => v * scale)
    const verticesAttribute = new THREE.Float32BufferAttribute(flatVertices, 3)
    mesh_geometry.setAttribute('position', verticesAttribute)

    // Flatten the faces array (indices) and set for the geometry
    const faces = component_data.geometry.mesh.f
    const flatFaces = faces.flat()
    mesh_geometry.setIndex(flatFaces)

    // Check if vertex colors are available
    const colors = component_data.geometry.mesh.c
    if (colors && colors.length === vertices.length) {
      const flatColors = colors.flatMap((color) => color.map((v) => v / 255)) // Normalize RGB to [0, 1]
      const colorAttribute = new THREE.Float32BufferAttribute(flatColors, 3)
      mesh_geometry.setAttribute('color', colorAttribute)
    }

    // Rotate to correct orientation to compensate for THREE.js axis system
    mesh_geometry.rotateX(-Math.PI / 2)

    // Ensure normals are computed
    mesh_geometry.computeVertexNormals()

    return mesh_geometry
  }, [component_data])

  // Get component color from data and convert to hex for display
  const component_color = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

  // Create a basic material for displaying the mesh polygons
  const mesh_material = useMemo(() => {
    return new THREE.MeshBasicMaterial({
      color: component_color,
      vertexColors: component_data.geometry.mesh.c ? true : false, // Enable vertex colors if available
      side: THREE.DoubleSide,
    })
  }, [component_color, component_data.geometry.mesh.c])

  // Create wireframe geometry
  const edge_geometry = useMemo(() => {
    return new THREE.EdgesGeometry(mesh_geometry)
  }, [mesh_geometry])

  // Create wireframe material
  const edge_material = useMemo(() => {
    return new THREE.LineBasicMaterial({ color: 0x000000 })
  }, [])

  // Return the mesh component
  return (
    <>
      <mesh visible geometry={mesh_geometry} material={mesh_material} />
      <lineSegments geometry={edge_geometry} material={edge_material} />
    </>
  )
}

const VisualizeSheet = (component_data: ComponentData) => {
  // Create a shape from the points
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
  // Create extruded geometry from the shape
  const extrude_geometry = useMemo(() => {
    // Define extrusion settings
    const extrudeSettings = {
      steps: 2,
      depth: component_data.geometry.extrusion.height * scale,
      bevelEnabled: false,
    }
    const extrude_geometry = new THREE.ExtrudeGeometry(
      pline_shape,
      extrudeSettings
    )
    // Translate to center of geometry
    extrude_geometry.translate(
      0,
      0,
      -component_data.geometry.extrusion.height * scale * 0.5
    )
    //Rotate to correct orientation to compensate for THREE.js axis system
    extrude_geometry.rotateX(-Math.PI / 2)
    return extrude_geometry
  }, [pline_shape, component_data.materialthickness])
  // Get component color
  const component_color = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )
  // Create wireframe
  const edge_geometry = useMemo(() => {
    const edge_geometry = new THREE.EdgesGeometry(extrude_geometry)
    return edge_geometry
  }, [extrude_geometry])
  // Create wireframe material
  const edge_material = new THREE.LineBasicMaterial({ color: 0x000000 })
  return (
    <>
      <mesh
        visible
        geometry={extrude_geometry}>
        <meshStandardMaterial color={new THREE.Color(component_color)} />
      </mesh>
      <lineSegments
        geometry={edge_geometry}
        material={edge_material}
      />
    </>
  )
}

const VisualizeComponent = ({
  component_data
} : {
  component_data: ComponentData
}) => {
  if (component_data.geometry == undefined) {
    return null
  }
  else {
    if (component_data.type == 'sheet') {
      return VisualizeSheet(component_data)
    } else {
      // we assume that every other component type has a mesh attached
      return VisualizeMesh(component_data)
    }
  }
}

export default function ComponentViewer({
  component_data,
}: {
  component_data: ComponentData
}) {

  return (
    <>
      {component_data.geometry == undefined ? <ComponentViewerSkeleton message='No Geometry Available'/> : 
        <Card className='flex h-[40dvh] m-2'>
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
            <Bounds fit clip observe margin={1.2} maxDuration={1} >
              <VisualizeComponent component_data={component_data}/>
            </Bounds>
            <axesHelper args={[0.1]}/>
            <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
            <OrbitControls makeDefault/>
          </Canvas>
        </Card>
      }
    </>
  )
}
