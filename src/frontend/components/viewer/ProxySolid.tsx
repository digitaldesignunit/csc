'use client'

import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

import { solidGeometry, type ProxyShape } from '@/lib/proxyShape'

/**
 * The proxy as a grey solid with its edges: the same faces and placement the
 * deviation overlay draws (decision 8.85). "Show mesh" is the surface,
 * "Show edges" the edge lines.
 */
export default function ProxySolid({
  shape,
  color,
  showMesh,
  showEdges,
}: {
  shape: ProxyShape
  color: string
  showMesh: boolean
  showEdges: boolean
}) {
  const solid = useMemo(() => solidGeometry(shape), [shape])
  const edgeMaterial = useMemo(() => new THREE.LineBasicMaterial({ color: 0x000000 }), [])
  useEffect(() => () => solid.dispose(), [solid])
  useEffect(() => () => edgeMaterial.dispose(), [edgeMaterial])

  return (
    <group matrixAutoUpdate={false} matrix={shape.matrix}>
      {showMesh && (
        <mesh geometry={solid}>
          {/* some faces are wound inward (the overlay texture does not care) */}
          <meshStandardMaterial color={color} side={THREE.DoubleSide} />
        </mesh>
      )}
      {showEdges && Object.entries(shape.edges).map(([face, geometry]) => (
        <lineSegments key={face} geometry={geometry} material={edgeMaterial} />
      ))}
    </group>
  )
}
