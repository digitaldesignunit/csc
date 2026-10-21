'use client'

import { useEffect, useLayoutEffect, useMemo } from 'react'
import * as THREE from 'three'

import { solidGeometry, type ProxyShape } from '@/lib/proxyShape'
import { FACE_POLYGON_OFFSET, edgeLineMaterial } from '@/lib/viewerDepth'
import { OPACITY_DEFAULT, applyOpacity, materialSettings } from '@/lib/viewerOpacity'

/**
 * The proxy as a grey solid with its edges: the same faces and placement the
 * deviation overlay draws (decision 8.85). `showMesh` is the surface,
 * `showEdges` the edge lines (both off when the mesh switch is Off). The
 * piece-opacity slider fades both (8.165 C).
 */
export default function ProxySolid({
  shape,
  color,
  showMesh,
  showEdges,
  opacity = OPACITY_DEFAULT,
}: {
  shape: ProxyShape
  color: string
  showMesh: boolean
  showEdges: boolean
  /** Percent, 0 to 100. */
  opacity?: number
}) {
  const solid = useMemo(() => solidGeometry(shape), [shape])
  const edgeMaterial = useMemo(() => edgeLineMaterial(), [])
  useEffect(() => () => solid.dispose(), [solid])
  useEffect(() => () => edgeMaterial.dispose(), [edgeMaterial])
  useLayoutEffect(() => applyOpacity(edgeMaterial, opacity), [edgeMaterial, opacity])
  const fade = materialSettings(opacity)

  return (
    <group matrixAutoUpdate={false} matrix={shape.matrix}>
      {showMesh && (
        <mesh geometry={solid}>
          {/* some faces are wound inward (the overlay texture does not care) */}
          {/* the key rebuilds the shader when the opaque variant changes */}
          <meshStandardMaterial
            key={fade.transparent ? 'faded' : 'solid'}
            color={color}
            side={THREE.DoubleSide}
            transparent={fade.transparent}
            opacity={fade.opacity}
            depthWrite={fade.depthWrite}
            polygonOffset={FACE_POLYGON_OFFSET.polygonOffset}
            polygonOffsetFactor={FACE_POLYGON_OFFSET.polygonOffsetFactor}
            polygonOffsetUnits={FACE_POLYGON_OFFSET.polygonOffsetUnits}
          />
        </mesh>
      )}
      {showEdges && Object.entries(shape.edges).map(([face, geometry]) => (
        <lineSegments key={face} geometry={geometry} material={edgeMaterial} />
      ))}
    </group>
  )
}
