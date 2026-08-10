'use client'

import React, { Component, useRef, useMemo, useState, useEffect, Suspense, type ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import { useTheme } from 'next-themes'
import * as THREE from 'three'

interface BackgroundMeshProps {
  className?: string
  intensity?: number
  rotationSpeed?: number
  color?: string
  opacity?: number
  scale?: number
  fixed?: boolean
}

// Served from Next `public/backgroundmeshes` (same origin). Do not route these
// through NEXT_PUBLIC_STATIC_BASE_URL — cross-origin GLB fetches need CORS and
// a failed useGLTF throws hard enough to tear down the whole page.
const MESH_BASE_PATH = '/backgroundmeshes/'

const MESH_FILES = [
  '0aad9436-ead8-4651-81a1-8b435012d799_reduced.glb',
  '0dd38d21-87ea-4c1d-a0b8-7245b45cd633_reduced.glb',
  '153b9ae8-f858-4e8f-a7c2-bbec658c4a60_reduced.glb',
  'eb011945-0315-449c-8117-c4e1e4292c9b_reduced.glb',
  'c4dfa0c4-4691-4dbb-a834-62240e3e4972_reduced.glb',
  'b9521122-5d01-4392-bd51-026b9cc5fbf0_reduced.glb',
  '6dc08bb0-4ae3-42e6-8cd9-23b49f624706_reduced.glb'
]

class MeshErrorBoundary extends Component<
  { children: ReactNode; onError?: () => void },
  { hasError: boolean }
> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch() {
    this.props.onError?.()
  }

  render() {
    if (this.state.hasError) return null
    return this.props.children
  }
}

const RotatingMesh = ({
  color = '#3b82f6',
  opacity = 0.1,
  rotationSpeed = 0.5,
  scale = 1.0,
  onVisibilityChange
}: {
  color: string
  opacity: number
  rotationSpeed: number
  scale: number
  onVisibilityChange: (visible: boolean) => void
}) => {
  const meshRef = useRef<THREE.Group>(null)
  const [selectedMesh, setSelectedMesh] = useState<string>('')

  useEffect(() => {
    const randomMesh = MESH_FILES[Math.floor(Math.random() * MESH_FILES.length)]
    setSelectedMesh(randomMesh)
  }, [])

  useEffect(() => {
    if (!selectedMesh) return
    try {
      const anyUseGltf = useGLTF as unknown as { preload?: (path: string) => void }
      anyUseGltf.preload?.(`${MESH_BASE_PATH}${selectedMesh}`)
    } catch {
      // ignore preload failures
    }
  }, [selectedMesh])

  const gltf = useGLTF(
    selectedMesh
      ? `${MESH_BASE_PATH}${selectedMesh}`
      : `${MESH_BASE_PATH}${MESH_FILES[0]}`
  )
  const scene = gltf?.scene

  const rotationAxis = useMemo(() => {
    return new THREE.Vector3(
      Math.random() * 2 - 1,
      Math.random() * 2 - 1,
      Math.random() * 2 - 1
    ).normalize()
  }, [])

  useFrame((_state, delta) => {
    if (meshRef.current) {
      meshRef.current.rotateOnAxis(rotationAxis, rotationSpeed * delta)
    }
  })

  useEffect(() => {
    if (!scene) return

    scene.traverse((child: THREE.Object3D) => {
      if (child instanceof THREE.Mesh) {
        const geom = child.geometry as THREE.BufferGeometry
        if (geom?.getAttribute('position')) {
          if (geom.getAttribute('normal')) {
            geom.deleteAttribute('normal')
          }
          geom.computeVertexNormals()
          geom.normalizeNormals()
        }
        child.material = new THREE.MeshBasicMaterial({
          color: new THREE.Color(color),
          transparent: true,
          opacity: opacity,
          wireframe: true
        })
      }
    })
  }, [scene, color, opacity])

  useEffect(() => {
    if (scene) {
      const t = setTimeout(() => onVisibilityChange(true), 100)
      return () => clearTimeout(t)
    }
  }, [scene, onVisibilityChange])

  if (!scene) {
    return null
  }

  return (
    <group ref={meshRef} scale={[scale, scale, scale]}>
      <primitive object={scene} />
    </group>
  )
}

export default function BackgroundMesh({
  className = '',
  intensity = 0.3,
  rotationSpeed = 0.5,
  color,
  opacity = 0.1,
  scale = 1.0,
  fixed = false
}: BackgroundMeshProps) {
  const { theme, systemTheme } = useTheme()
  const [isVisible, setIsVisible] = useState<boolean>(false)

  const getMeshColor = () => {
    if (color) return color
    const effectiveTheme = theme === 'system' ? systemTheme : theme
    return effectiveTheme === 'dark' ? '#4080ff' : '#ef509c'
  }

  const meshColor = getMeshColor()

  return (
    <div
      className={`${fixed ? 'fixed' : 'absolute'} inset-0 pointer-events-none ${className}`}
      style={{
        opacity: isVisible ? 1 : 0,
        transition: 'opacity 0.5s ease-in-out'
      }}
    >
      <Canvas
        camera={{ position: [0, 0, 0.8], fov: 50 }}
        style={{ background: 'transparent' }}
        gl={{ alpha: true, antialias: true }}
      >
        <ambientLight intensity={intensity} />
        <MeshErrorBoundary onError={() => setIsVisible(false)}>
          <Suspense fallback={null}>
            <RotatingMesh
              color={meshColor}
              opacity={opacity}
              rotationSpeed={rotationSpeed}
              scale={scale}
              onVisibilityChange={setIsVisible}
            />
          </Suspense>
        </MeshErrorBoundary>
      </Canvas>
    </div>
  )
}
