'use client'

import React, { useRef, useMemo, useState, useEffect, Suspense } from 'react'
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

// Fallback mesh component for when GLTF loading fails
const FallbackMesh = ({ 
  color, 
  opacity, 
  rotationSpeed 
}: {
  color: string
  opacity: number
  rotationSpeed: number
}) => {
  const meshRef = useRef<THREE.Group>(null)
  
  useFrame((state, delta) => {
    if (meshRef.current) {
      meshRef.current.rotateY(rotationSpeed * delta)
    }
  })

  return (
    <group ref={meshRef}>
      <mesh>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial 
          color={color}
          transparent={true}
          opacity={opacity}
          wireframe={true}
        />
      </mesh>
    </group>
  )
}

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
  
  // Select a random mesh file on component mount
  useEffect(() => {
    const randomMesh = MESH_FILES[Math.floor(Math.random() * MESH_FILES.length)]
    setSelectedMesh(randomMesh)
  }, [])
  
  // Load the GLB file - useGLTF handles errors internally
  const gltf = useGLTF(selectedMesh ? `/meshes/${selectedMesh}` : '/meshes/0aad9436-ead8-4651-81a1-8b435012d799_reduced.glb')
  const scene = gltf?.scene
  
  // Debug logging
  useEffect(() => {
    if (selectedMesh) {
      console.log('Loading mesh:', `/meshes/${selectedMesh}`)
    }
  }, [selectedMesh])
  
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

  // Clone the scene and apply wireframe material
  const clonedScene = useMemo(() => {
    if (!scene) return null
    
    const cloned = scene.clone()
    
    // Apply wireframe material to all meshes
    cloned.traverse((child: THREE.Object3D) => {
      if (child instanceof THREE.Mesh) {
        child.material = new THREE.MeshBasicMaterial({
          color: color,
          transparent: true,
          opacity: opacity,
          wireframe: true
        })
      }
    })
    
    return cloned
  }, [scene, color, opacity])

  // If no scene available, use fallback
  if (!clonedScene) {
    return <FallbackMesh color={color} opacity={opacity} rotationSpeed={rotationSpeed} />
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
        <Suspense fallback={<FallbackMesh color={meshColor} opacity={opacity} rotationSpeed={rotationSpeed} />}>
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
