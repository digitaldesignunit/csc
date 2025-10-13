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

// Rotating mesh component that loads random GLTF files
const RotatingMesh = ({ 
  color = '#3b82f6', 
  opacity = 0.1,
  rotationSpeed = 0.5,
  onVisibilityChange
}: {
  color: string
  opacity: number
  rotationSpeed: number
  onVisibilityChange: (visible: boolean) => void
}) => {
  const meshRef = useRef<THREE.Group>(null)
  const [selectedMesh, setSelectedMesh] = useState<string>('')
  
  // Resolve mesh base URL: use env for remote, local public when on localhost
  const meshBaseUrl = useMemo(() => {
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
    }
  })


  // Set up materials when scene is available
  useEffect(() => {
    if (!scene) return
    
    scene.traverse((child: THREE.Object3D) => {
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
          opacity: opacity,
          wireframe: true
        })
      }
    })
  }, [scene, color, opacity])

  // When scene becomes available, trigger CSS fade-in
  useEffect(() => {
    if (scene) {
      // Small delay to ensure scene is ready
      setTimeout(() => {
        onVisibilityChange(true)
      }, 100)
    }
  }, [scene, onVisibilityChange])

  // If not loaded, render nothing (no fallback). We'll fade in when ready
  if (!scene) {
    return null
  }

  return (
    <group ref={meshRef}>
      <primitive object={scene} />
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
  const [isVisible, setIsVisible] = useState<boolean>(false)
  
  // Theme-aware color selection that handles system theme
  const getMeshColor = () => {
    if (color) return color
    
    // If theme is system, use systemTheme to determine color
    const effectiveTheme = theme === 'system' ? systemTheme : theme
    
    return effectiveTheme === 'dark' ? '#4080ff' : '#ef509c'
  }
  
  const meshColor = getMeshColor()
  
  return (
    <div 
      className={`absolute inset-0 pointer-events-none ${className}`}
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
        <Suspense fallback={null}>
          <RotatingMesh 
            color={meshColor}
            opacity={opacity}
            rotationSpeed={rotationSpeed}
            onVisibilityChange={setIsVisible}
          />
        </Suspense>
      </Canvas>
    </div>
  )
}