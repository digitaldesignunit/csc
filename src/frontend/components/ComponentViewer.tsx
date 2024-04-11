'use client'

import { Canvas, useFrame } from '@react-three/fiber';
import { useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { ComponentPolylinePoints } from './models';
import { Card } from './ui/card';
import { Bounds, OrbitControls } from '@react-three/drei';
import { ComponentData } from './models';
import { rgbToHex } from '@/lib/utils';

const VisualizeSheet = (component_data: ComponentData) => {
  
  // Create a shape from the points
  const polyline_shape = useMemo(() => {
    const polyline_shape = new THREE.Shape()
    const points: ComponentPolylinePoints = component_data.geometry.polyline
    polyline_shape.moveTo(points[0][0] * 0.001, points[0][1] * 0.001)
    points.forEach((pointtuple: number[], index) => {
      if (index > 0) {
        polyline_shape.lineTo(pointtuple[0] * 0.001, pointtuple[1] * 0.001);
      }
    })
    return polyline_shape;
  }, [component_data])

  // Define extrusion settings
  const extrudeSettings = {
    steps: 2,
    depth: component_data.materialthickness * 0.001,
    bevelEnabled: false,
  }

  // Create extruded geometry from the shape
  const extrudeGeometry = useMemo(() => {
    let extrude_geo = new THREE.ExtrudeGeometry(polyline_shape, extrudeSettings)
    extrude_geo.rotateX(-Math.PI / 2)
    return extrude_geo
  }, [polyline_shape])
  
  const component_color = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )
  return (
    <mesh
      visible
      geometry={extrudeGeometry}>
      <meshStandardMaterial color={new THREE.Color(component_color)} />
    </mesh>
  )
}

const VisualizeComponent = ({component_data } : {component_data: ComponentData}) => {
  if (component_data.type == 'sheet') {
    return VisualizeSheet(component_data)
  } else {
    return null
  }
}

export default function ComponentViewer({
  component_data,
}: {
  component_data: ComponentData
}) {

  return (
      <Card className='flex h-[40dvh] m-2'>
        <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />
          <Bounds fit clip observe margin={1.2} maxDuration={1} >
            <VisualizeComponent component_data={component_data}/>
          </Bounds>
          <axesHelper args={[0.1]}/>
          <gridHelper args={[2, 20, 0xff0000, 'grey']} />
          <OrbitControls makeDefault/>
        </Canvas>
      </Card>
  );
};
