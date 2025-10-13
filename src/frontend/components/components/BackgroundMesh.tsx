'use client'

import React, { useRef, useMemo, useState, useEffect, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import { resolveStatic } from '@/lib/utils'
import { useTheme } from 'next-themes'
import * as THREE from 'three'

interface BackgroundMeshProps {
  className?: string
  intensity?: number
  rotationSpeed?: number
  color?: string
  opacity?: number
}

// Available mesh files
const MESH_FILES = [
  '0aad9436-ead8-4651-81a1-8b435012d799_reduced.glb',
  '0dd38d21-87ea-4c1d-a0b8-7245b45cd633_reduced.glb',
  '153b9ae8-f858-4e8f-a7c2-bbec658c4a60_reduced.glb',
  'eb011945-0315-449c-8117-c4e1e4292c9b_reduced.glb',
  'c4dfa0c4-4691-4dbb-a834-62240e3e4972_reduced.glb',
  'b9521122-5d01-4392-bd51-026b9cc5fbf0_reduced.glb',
  '6dc08bb0-4ae3-42e6-8cd9-23b49f624706_reduced.glb'
]

// No visible fallback while loading; we fade-in once loaded

// Rotating mesh component that loads random GLTF files
const RotatingMesh = ({ 
  color = '#3b82f6', 
  opacity = 0.1,
  rotationSpeed = 0.5 
}: {
  color: string
  opacity: number
  rotationSpeed: number
}) => {
  const meshRef = useRef<THREE.Group>(null)
  const [selectedMesh, setSelectedMesh] = useState<string>('')
  const [currentOpacity, setCurrentOpacity] = useState<number>(0)
  const targetOpacityRef = useRef<number>(opacity)
  const fadeInSpeed = 0.25
  
  // Resolve mesh base URL: use env for remote, local public when on localhost
  const meshBaseUrl = useMemo(() => {
    // resolveStatic will prepend NEXT_STATIC_BASE_URL in prod; locally remains as provided
    const basePath = '/backgroundmeshes/'
    const resolved = resolveStatic(basePath)
    return resolved.endsWith('/') ? resolved : resolved + '/'
  }, [])

  // Select a random mesh file on component mount
  useEffect(() => {
    const randomMesh = MESH_FILES[Math.floor(Math.random() * MESH_FILES.length)]
    setSelectedMesh(randomMesh)
  }, [])
  
  // Preload selected GLTF into cache
  useEffect(() => {
    if (!selectedMesh) return
    try {
      // Attempt to preload if available at runtime
      const anyUseGltf = useGLTF as unknown as { preload?: (path: string) => void }
      anyUseGltf.preload?.(`${meshBaseUrl}${selectedMesh}`)
    } catch {
      // ignore
    }
  }, [selectedMesh, meshBaseUrl])
  
  // Load the GLB file - useGLTF handles errors internally
  const gltf = useGLTF(
    selectedMesh
      ? `${meshBaseUrl}${selectedMesh}`
      : `${meshBaseUrl}0aad9436-ead8-4651-81a1-8b435012d799_reduced.glb`
  )
  const scene = gltf?.scene
  
  // Generate random rotation axis
  const rotationAxis = useMemo(() => {
    return new THREE.Vector3(
      Math.random() * 2 - 1,
      Math.random() * 2 - 1,
      Math.random() * 2 - 1
    ).normalize()
  }, [])

  useFrame((state, delta) => {
    if (meshRef.current) {
      // Rotate around the random axis
      meshRef.current.rotateOnAxis(rotationAxis, rotationSpeed * delta)
      
      // Incrementally increase opacity until target reached
      if (currentOpacity < targetOpacityRef.current) {
        const next = Math.min(targetOpacityRef.current, currentOpacity + fadeInSpeed * delta)
        if (next !== currentOpacity) setCurrentOpacity(next)
      }
      
      // Apply opacity and styling to all mesh materials
      meshRef.current.traverse((child: THREE.Object3D) => {
        if (child instanceof THREE.Mesh) {
          const mesh = child as THREE.Mesh
          const mat = mesh.material as THREE.Material | THREE.Material[]
          if (Array.isArray(mat)) {
            mat.forEach(m => {
              const mb = m as THREE.MeshBasicMaterial
              mb.transparent = true
              mb.opacity = currentOpacity
              mb.wireframe = true
              mb.color = new THREE.Color(color)
            })
          } else if (mat) {
            const mb = mat as THREE.MeshBasicMaterial
            mb.transparent = true
            mb.opacity = currentOpacity
            mb.wireframe = true
            mb.color = new THREE.Color(color)
          }
        }
      })
    }
  })

  // Clone the scene; materials will be set and faded in during frames
  const clonedScene = useMemo(() => {
    if (!scene) return null
    
    const cloned = scene.clone()
    // Initialize materials to invisible basic wireframe, color applied each frame
    cloned.traverse((child: THREE.Object3D) => {
      if (child instanceof THREE.Mesh) {
        // Ensure vertex normals are present and up to date
        const geom = child.geometry as THREE.BufferGeometry
        if (geom) {
          if (geom.getAttribute('position')) {
            // Drop stale normals and recompute
            if (geom.getAttribute('normal')) {
              geom.deleteAttribute('normal')
            }
            geom.computeVertexNormals()
            geom.normalizeNormals()
          }
        }
        child.material = new THREE.MeshBasicMaterial({
          color: new THREE.Color(color),
          transparent: true,
          opacity: 0,
          wireframe: true
        })
      }
    })
    
    return cloned
  }, [scene, color])

  // When scene becomes available, reset current opacity for fresh fade-in
  useEffect(() => {
    if (clonedScene) setCurrentOpacity(0)
  }, [clonedScene])

  // Update target when prop changes
  useEffect(() => {
    targetOpacityRef.current = opacity
  }, [opacity])

  // If not loaded, render nothing (no fallback). We'll fade in when ready
  if (!clonedScene) {
    return null
  }

  return (
    <group ref={meshRef}>
      <primitive object={clonedScene} />
    </group>
  )
}

export default function BackgroundMesh({
  className = '',
  intensity = 0.3,
  rotationSpeed = 0.5,
  color,
  opacity = 0.1
}: BackgroundMeshProps) {
  const { theme, systemTheme } = useTheme()
  
  // Theme-aware color selection that handles system theme
  const getMeshColor = () => {
    if (color) return color
    
    // If theme is system, use systemTheme to determine color
    const effectiveTheme = theme === 'system' ? systemTheme : theme
    
    return effectiveTheme === 'dark' ? '#4080ff' : '#ef509c'
  }
  
  const meshColor = getMeshColor()
  
  return (
    <div className={`absolute inset-0 pointer-events-none ${className}`}>
      <Canvas
        camera={{ position: [0, 0, 0.8], fov: 50 }}
        style={{ background: 'transparent' }}
        gl={{ alpha: true, antialias: true }}
      >
        <ambientLight intensity={intensity} />
        <Suspense fallback={null}>
          <RotatingMesh 
            color={meshColor}
            opacity={opacity}
            rotationSpeed={rotationSpeed}
          />
        </Suspense>
      </Canvas>
    </div>
  )
}
