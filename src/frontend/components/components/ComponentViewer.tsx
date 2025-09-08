'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { ComponentModel, ComponentGeometry, ComponentMesh, ComponentExtrusion } from '@/generated/ComponentModel'
import { Card } from '@/components/ui/card'
import { Bounds, OrbitControls, Html } from '@react-three/drei'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { Skeleton } from '@/components/ui/skeleton'

// Scale factor for converting units to meters in THREE
const scale = 0.001

// Simple in-memory cache for external geometry
const externalGeometryCache = new Map<string, THREE.Group[] | null>()

/* ───────── Helpers ───────── */

type GeometryMode = 'primitive' | 'reduced' | 'detailed'

/* ───────── External geometry/mtl loading ───────── */

// Simple debug logging for dev mode only
const isDev = process.env.NODE_ENV === 'development'
const debugLog = (message: string, ...args: unknown[]) => {
  if (isDev) {
    console.log(`[ComponentViewer] ${message}`, ...args)
  }
}

/**
 * Smart color normalization - detects if colors are in 0-255 range and normalizes only if needed
 */
function normalizeColors(colors: number[]): number[] {
  if (colors.length === 0) return colors
  
  // Check if colors are already normalized (all values <= 1.0)
  const allNormalized = colors.every(color => color <= 1.0)
  
  if (allNormalized) {
    debugLog(`Colors already normalized, keeping as-is`)
    return colors
  }
  
  // Check if colors are in 0-255 range (all values >= 0 and <= 255)
  const allInRange = colors.every(color => color >= 0 && color <= 255)
  
  if (allInRange) {
    debugLog(`Converting colors from 0-255 range to 0-1 range`)
    return colors.map(color => color / 255)
  }
  
  // Mixed or invalid range - warn and clamp to 0-1
  debugLog(`Warning: Mixed color ranges detected, clamping to 0-1`)
  return colors.map(color => Math.max(0, Math.min(1, color)))
}

type GeometryLoadResult = {
  success: true
  meshes: THREE.Group[]
} | {
  success: false
  error: 'not_found' | 'network_error' | 'parse_error'
  message: string
}

/**
 * Parse OBJ file manually to extract multiple meshes with vertices, faces, and colors
 */
function parseOBJ(objContent: string): { meshes: { vertices: number[], faces: number[], colors: number[], name: string }[] } {
  const lines = objContent.split('\n')
  const meshes: { vertices: number[], faces: number[], colors: number[], name: string }[] = []
  
  let currentMesh: { vertices: number[], faces: number[], colors: number[], name: string } | null = null
  const globalVertices: number[] = []
  const globalColors: number[] = []
  
  for (const line of lines) {
    const trimmed = line.trim()
    
    // Parse object/group definition: o name or g name
    if (trimmed.startsWith('o ') || trimmed.startsWith('g ')) {
      // Save previous mesh if it exists
      if (currentMesh && currentMesh.faces.length > 0) {
        meshes.push(currentMesh)
      }
      
      // Start new mesh
      const name = trimmed.split(/\s+/).slice(1).join(' ') || `Mesh ${meshes.length + 1}`
      currentMesh = { vertices: [], faces: [], colors: [], name }
    }
    
    // Parse vertex with colors: v x y z r g b
    if (trimmed.startsWith('v ') && !trimmed.startsWith('vt ') && !trimmed.startsWith('vn ')) {
      const parts = trimmed.split(/\s+/)
      if (parts.length >= 4) {
        // Position
        globalVertices.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]))
        
        // Colors (if present)
        if (parts.length >= 7) {
          const r = parseFloat(parts[4])
          const g = parseFloat(parts[5])
          const b = parseFloat(parts[6])
          if (!isNaN(r) && !isNaN(g) && !isNaN(b)) {
            globalColors.push(r, g, b)
          } else {
            globalColors.push(0.5, 0.5, 0.5) // Default gray
          }
        } else {
          globalColors.push(0.5, 0.5, 0.5) // Default gray
        }
      }
    }
    // Parse faces: f v1 v2 v3 (1-indexed)
    else if (trimmed.startsWith('f ')) {
      if (!currentMesh) {
        // If no object/group defined, create a default mesh
        currentMesh = { vertices: [], faces: [], colors: [], name: 'Default Mesh' }
      }
      
      const parts = trimmed.split(/\s+/)
      if (parts.length >= 4) {
        // Convert from 1-indexed to 0-indexed and handle negative indices
        const faceIndices: number[] = []
        for (let i = 1; i < parts.length; i++) {
          const faceIndex = parseInt(parts[i].split('/')[0])
          const index = faceIndex < 0 ? globalVertices.length / 3 + faceIndex : faceIndex - 1
          faceIndices.push(index)
        }
        
        // Triangulate faces (convert quads to triangles)
        if (faceIndices.length === 3) {
          // Triangle - add as-is
          currentMesh.faces.push(...faceIndices)
        } else if (faceIndices.length === 4) {
          // Quad - split into two triangles
          currentMesh.faces.push(faceIndices[0], faceIndices[1], faceIndices[2])
          currentMesh.faces.push(faceIndices[0], faceIndices[2], faceIndices[3])
        } else if (faceIndices.length > 4) {
          // N-gon - fan triangulation
          for (let i = 1; i < faceIndices.length - 1; i++) {
            currentMesh.faces.push(faceIndices[0], faceIndices[i], faceIndices[i + 1])
          }
        }
      }
    }
  }
  
  // Save the last mesh if it exists
  if (currentMesh && currentMesh.faces.length > 0) {
    meshes.push(currentMesh)
  }
  
  // If no meshes were created (no object/group definitions), create a single mesh from all data
  if (meshes.length === 0 && globalVertices.length > 0) {
    const singleMesh = { vertices: globalVertices, faces: [], colors: globalColors, name: 'Single Mesh' }
    // We need to reconstruct faces from the global data - this is a fallback
    meshes.push(singleMesh)
  }
  
  // For each mesh, extract the relevant vertices and colors based on face indices
  for (const mesh of meshes) {
    if (mesh.faces.length > 0) {
      const usedVertices = new Set<number>()
      
      // Find all unique vertex indices used by this mesh
      for (let i = 0; i < mesh.faces.length; i++) {
        usedVertices.add(mesh.faces[i])
      }
      
      // Create mapping from old indices to new indices
      const vertexMap = new Map<number, number>()
      const newVertices: number[] = []
      const newColors: number[] = []
      
      let newIndex = 0
      for (const oldIndex of usedVertices) {
        vertexMap.set(oldIndex, newIndex)
        newIndex++
        
        // Copy vertex data
        if (oldIndex * 3 + 2 < globalVertices.length) {
          newVertices.push(
            globalVertices[oldIndex * 3],
            globalVertices[oldIndex * 3 + 1],
            globalVertices[oldIndex * 3 + 2]
          )
        }
        
        // Copy color data
        if (oldIndex * 3 + 2 < globalColors.length) {
          newColors.push(
            globalColors[oldIndex * 3],
            globalColors[oldIndex * 3 + 1],
            globalColors[oldIndex * 3 + 2]
          )
        }
      }
      
      // Update face indices to use new mapping
      mesh.faces = mesh.faces.map(oldIndex => vertexMap.get(oldIndex) || 0)
      mesh.vertices = newVertices
      mesh.colors = newColors
    }
  }
  
  debugLog(`Parsed OBJ: ${meshes.length} meshes, ${globalVertices.length / 3} total vertices, ${globalColors.length / 3} total colors`)
  return { meshes }
}

async function loadExternalGeometry(
  componentId: string,
  mode: Exclude<GeometryMode, 'primitive'>
): Promise<GeometryLoadResult> {
  debugLog(`Loading ${mode} geometry for component ${componentId}`)
  
  const cacheKey = `${componentId}:${mode}`
  if (externalGeometryCache.has(cacheKey)) {
    const cached = externalGeometryCache.get(cacheKey)
    if (cached) {
      debugLog(`Using cached geometry for ${componentId}: ${cached.length} meshes`)
      return { success: true, meshes: cached }
    } else {
      return { 
        success: false, 
        error: 'not_found', 
        message: `No ${mode} geometry available for this component` 
      }
    }
  }

  const geometryRoute = mode === 'reduced' ? 'geometry_reduced' : 'geometry_detailed'
  const objUrl = `/api/backend/components/${componentId}/${geometryRoute}`

  try {
    // Fetch and parse OBJ content manually
    debugLog(`Fetching OBJ content...`)
    const response = await fetch(objUrl, { credentials: 'include' })
    if (!response.ok) {
      throw new Error(`Failed to fetch OBJ: ${response.status} ${response.statusText}`)
    }
    
    const objContent = await response.text()
    const { meshes: parsedMeshes } = parseOBJ(objContent)
    
    if (parsedMeshes.length === 0) {
      throw new Error('No meshes found in OBJ file')
    }

    const threeMeshes: THREE.Group[] = []

    for (const meshData of parsedMeshes) {
      if (meshData.vertices.length === 0) continue

      // Build BufferGeometry manually
      const geometry = new THREE.BufferGeometry()
      
      // Set positions
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(meshData.vertices, 3))
      
      // Set faces (indices)
      if (meshData.faces.length > 0) {
        geometry.setIndex(meshData.faces)
      }
      
      // Set colors if available
      if (meshData.colors.length > 0) {
        // Normalize colors using smart normalization
        const normalizedColors = normalizeColors(meshData.colors)
        geometry.setAttribute('color', new THREE.Float32BufferAttribute(normalizedColors, 3))
        debugLog(`Applied ${normalizedColors.length / 3} normalized vertex colors to ${meshData.name}`)
      }

      // Compute normals to fix see-through faces
      geometry.computeVertexNormals()
      geometry.normalizeNormals()
      
      // Debug geometry info
      debugLog(`${meshData.name} stats: ${meshData.vertices.length / 3} vertices, ${meshData.faces.length / 3} triangles`)

      // Create material with proper settings
      const material = meshData.colors.length > 0
        ? new THREE.MeshBasicMaterial({
            vertexColors: true,
            side: THREE.DoubleSide,
            transparent: false,
            opacity: 1.0
          })
        : new THREE.MeshBasicMaterial({ 
            color: 0x888888, 
            side: THREE.DoubleSide,
            transparent: false,
            opacity: 1.0
          })

      // Create mesh
      const mesh = new THREE.Mesh(geometry, material)
      mesh.name = meshData.name
      
      // Create group and add mesh
      const object = new THREE.Group()
      object.add(mesh)
      
      // Apply scaling
      object.scale.set(scale, scale, scale)

      threeMeshes.push(object)
    }

    debugLog(`Created ${threeMeshes.length} meshes from OBJ file`)

    // Cache the individual meshes
    externalGeometryCache.set(cacheKey, threeMeshes)
    
    return { success: true, meshes: threeMeshes }
  } catch (e) {
    debugLog(`Failed to load external geometry:`, e)
    
    let errorType: 'not_found' | 'network_error' | 'parse_error' = 'network_error'
    let message = `Failed to load ${mode} geometry`
    
    if (e instanceof Error) {
      if (e.message.includes('404') || e.message.includes('not found')) {
        errorType = 'not_found'
        message = `No ${mode} geometry available for this component`
      } else if (e.message.includes('Failed to fetch') || e.message.includes('NetworkError')) {
        errorType = 'network_error'
        message = `Network error loading ${mode} geometry`
      } else {
        errorType = 'parse_error'
        message = `Error parsing ${mode} geometry data`
      }
    }
    
    externalGeometryCache.set(cacheKey, null)
    return { success: false, error: errorType, message }
  }
}

/** 
 * VisualizeMesh 
 */
const VisualizeMesh = React.memo(({
  component_data,
  geometryMode,
  visibleMeshes = [],
  externalMeshes = [],
  isLoadingExternal = false,
  geometryError = null
}: {
  component_data: ComponentModel
  geometryMode: GeometryMode
  visibleMeshes?: boolean[]
  externalMeshes?: THREE.Group[]
  isLoadingExternal?: boolean
  geometryError?: string | null
}) => {
  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'

  // Primitive fallback geometry
  const mesh_geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    
    // Check if geometry has mesh data
    const geometry = component_data.geometry as ComponentGeometry
    const mesh = geometry.mesh as ComponentMesh | undefined
    if (!mesh?.v || !mesh?.f) {
      return g; // Return empty geometry if structure is invalid
    }
    
    const vertices = mesh.v
    // Don't apply scaling here - it will be handled by the group scale
    const flatVertices = vertices.flat()
    g.setAttribute('position', new THREE.Float32BufferAttribute(flatVertices, 3))

    const faces = mesh.f
    g.setIndex(faces.flat())

    const colors = mesh.c
    if (colors && Array.isArray(colors) && colors.length === vertices.length) {
      const flatColors = colors.flatMap((c) => Array.isArray(c) ? c.map((v) => v / 255) : [])
      g.setAttribute('color', new THREE.Float32BufferAttribute(flatColors, 3))
    }
    
    // Apply the same coordinate system transformation as external geometry
    // This ensures primitive geometry appears in the same orientation as reduced/detailed
    g.rotateX(-Math.PI / 2)
    g.computeVertexNormals()
    g.normalizeNormals()
    return g
  }, [component_data])

  const colorHex = rgbToHex(
    Array.isArray(component_data.color) ? component_data.color[0] as number : 0,
    Array.isArray(component_data.color) ? component_data.color[1] as number : 0,
    Array.isArray(component_data.color) ? component_data.color[2] as number : 0
  )

  const mesh_material = useMemo(() => {
    const geometry = component_data.geometry as ComponentGeometry
    const mesh = geometry.mesh as ComponentMesh | undefined
    const hasVertexColors = Boolean(mesh?.c && Array.isArray(mesh.c) && mesh.c.length > 0);

    return new THREE.MeshBasicMaterial({
      color: colorHex,
      vertexColors: hasVertexColors,
      side: THREE.DoubleSide
    })
  }, [colorHex, component_data.geometry])

  const edge_geometry = useMemo(() => new THREE.EdgesGeometry(mesh_geometry), [mesh_geometry])
  const edge_material = useMemo(() => new THREE.LineBasicMaterial({ color: 0x000000 }), [])

  if (isExternalMode) {
    if (isLoadingExternal) {
      return (
        <mesh>
          <Html center>
            <div
              style={{
                minWidth: '200px',
                padding: '8px',
                background: 'rgba(255,255,255,0.8)',
                borderRadius: '4px',
                textAlign: 'center',
              }}
            >
              <Skeleton className="h-full rounded-xl m-2 flex items-center justify-center">
                <strong>Loading {geometryMode} geometry...</strong>
              </Skeleton>
            </div>
          </Html>
        </mesh>
      )
    }
    if (externalMeshes.length > 0) {
      return (
        <>
          {externalMeshes.map((mesh, index) => {
            if (!visibleMeshes[index]) return null
            return <primitive key={index} object={mesh} />
          })}
        </>
      )
    }
    if (geometryError) {
      return (
        <mesh>
          <Html center>
            <div
              style={{
                minWidth: '200px',
                padding: '12px',
                background: 'rgba(255,255,255,0.9)',
                borderRadius: '4px',
                textAlign: 'center',
                border: '1px solid #e5e7eb',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              }}
            >
              <div style={{ color: '#6b7280', fontSize: '14px', marginBottom: '8px' }}>
                <strong>{geometryError}</strong>
              </div>
            </div>
          </Html>
        </mesh>
      )
    }
    // fallback if external fail
    return (
      <>
        <mesh visible geometry={mesh_geometry} material={mesh_material} />
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </>
    )
  } else {
    // Primitive - group and scale like external geometry
    return (
      <group scale={[scale, scale, scale]}>
        <mesh visible geometry={mesh_geometry} material={mesh_material} />
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </group>
    )
  }
})
VisualizeMesh.displayName = 'VisualizeMesh'

/** 
 * VisualizeSheet 
 */
const VisualizeSheet = React.memo(({ component_data }: { component_data: ComponentModel }) => {
  const pline_shape = useMemo(() => {
    const shape = new THREE.Shape()
    
    // Check if geometry has extrusion data
    const geometry = component_data.geometry as ComponentGeometry
    const extrusion = geometry.extrusion as ComponentExtrusion | undefined
    if (!extrusion?.profile || !Array.isArray(extrusion.profile)) {
      return shape; // Return empty shape if structure is invalid
    }
    
    const points = extrusion.profile
    shape.moveTo(points[0][0] * scale, points[0][1] * scale)
    points.forEach((p, i) => {
      if (i > 0) shape.lineTo(p[0] * scale, p[1] * scale)
    })
    return shape
  }, [component_data])

  const extrude_geometry = useMemo(() => {
    const geometry = component_data.geometry as ComponentGeometry
    const extrusion = geometry.extrusion as ComponentExtrusion | undefined
    if (!extrusion?.profile || !extrusion?.height) {
      return new THREE.ExtrudeGeometry(new THREE.Shape());
    }
    
    const extrudeSettings = { steps: 2, depth: extrusion.height * scale, bevelEnabled: false }
    const g = new THREE.ExtrudeGeometry(pline_shape, extrudeSettings)
    g.translate(0, 0, -extrusion.height * scale * 0.5)
    g.rotateX(-Math.PI / 2)
    g.computeVertexNormals()
    g.normalizeNormals()
    return g
  }, [pline_shape, component_data.geometry])

  const colorHex = rgbToHex(
    Array.isArray(component_data.color) ? component_data.color[0] as number : 0,
    Array.isArray(component_data.color) ? component_data.color[1] as number : 0,
    Array.isArray(component_data.color) ? component_data.color[2] as number : 0
  )

  const edge_geometry = useMemo(() => new THREE.EdgesGeometry(extrude_geometry), [extrude_geometry])
  const edge_material = useMemo(() => new THREE.LineBasicMaterial({ color: 0x000000 }), [])

  return (
    <>
      <mesh visible geometry={extrude_geometry}>
        <meshStandardMaterial color={new THREE.Color(colorHex)} />
      </mesh>
      <lineSegments geometry={edge_geometry} material={edge_material} />
    </>
  )
})
VisualizeSheet.displayName = 'VisualizeSheet'

/** 
 * MarkerPoints - renders marker points as red dots
 */
const MarkerPoints = React.memo(({
  markerPoints,
  visible
}: {
  markerPoints: number[][]
  visible: boolean
}) => {
  if (!visible || markerPoints.length === 0) return null

  return (
    <group scale={[scale, scale, scale]} rotation={[-Math.PI / 2, 0, 0]}>
      {markerPoints.map((point, index) => {
        const [x, y, z] = point
        return (
          <mesh key={index} position={[x, y, z]}>
            <sphereGeometry args={[5.0, 16, 12]} />
            <meshBasicMaterial color={0xff0000} />
          </mesh>
        )
      })}
    </group>
  )
})
MarkerPoints.displayName = 'MarkerPoints'

/** 
 * VisualizeMultipleMeshes - handles multiple meshes with individual visibility controls
 */
const VisualizeMultipleMeshes = React.memo(({
  component_data,
  geometryMode,
  visibleMeshes = [],
  externalMeshes = [],
  isLoadingExternal = false,
  geometryError = null
}: {
  component_data: ComponentModel
  geometryMode: GeometryMode
  visibleMeshes?: boolean[]
  externalMeshes?: THREE.Group[]
  isLoadingExternal?: boolean
  geometryError?: string | null
}) => {
  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'
  const geometry = component_data.geometry as ComponentGeometry
  const meshes = (geometry.meshes || []) as ComponentMesh[]

  if (isLoadingExternal) {
    return (
      <mesh>
        <Html center>
          <div
            style={{
              minWidth: '200px',
              padding: '8px',
              background: 'rgba(255,255,255,0.8)',
              borderRadius: '4px',
              textAlign: 'center',
            }}
          >
            <Skeleton className="h-full rounded-xl m-2 flex items-center justify-center">
              <strong>Loading {geometryMode} geometry...</strong>
            </Skeleton>
          </div>
        </Html>
      </mesh>
    )
  }

  if (geometryError) {
    return (
      <mesh>
        <Html center>
          <div
            style={{
              minWidth: '200px',
              padding: '12px',
              background: 'rgba(255,255,255,0.9)',
              borderRadius: '4px',
              textAlign: 'center',
              border: '1px solid #e5e7eb',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <div style={{ color: '#6b7280', fontSize: '14px', marginBottom: '8px' }}>
              <strong>{geometryError}</strong>
            </div>
          </div>
        </Html>
      </mesh>
    )
  }

  if (isExternalMode && externalMeshes.length > 0) {
    // For external geometry, render individual meshes with visibility controls
    return (
      <>
        {externalMeshes.map((mesh, index) => {
          if (!visibleMeshes[index]) return null
          return <primitive key={index} object={mesh} />
        })}
      </>
    )
  }

  // For primitive mode, render individual meshes with visibility controls
  // Group all meshes together and apply scaling like external geometry
  return (
    <group scale={[scale, scale, scale]}>
      {meshes.map((mesh: ComponentMesh, index: number) => {
        if (!visibleMeshes[index]) return null

        // Create geometry from mesh data (without scaling here, handled by group)
        const positions = (mesh.v || []).flat()
        const indices = (mesh.f || []).flat()
        const rawColors = mesh.c ? (mesh.c as number[][] || []) : undefined

        const geometry = new THREE.BufferGeometry()
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
        geometry.setIndex(indices)

        if (rawColors && rawColors.length > 0) {
          // Use smart normalization
          const flatColors = rawColors.flat()
          const normalizedColors = normalizeColors(flatColors)
          geometry.setAttribute('color', new THREE.Float32BufferAttribute(normalizedColors, 3))
          debugLog(`Applied ${normalizedColors.length / 3} vertex colors to primitive mesh ${index + 1}`)
        }

        // Apply the same coordinate system transformation as external geometry
        geometry.rotateX(-Math.PI / 2)
        geometry.computeVertexNormals()
        geometry.normalizeNormals()

        const material = rawColors && rawColors.length > 0
          ? new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })
          : new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.DoubleSide })

        const edgeGeometry = new THREE.EdgesGeometry(geometry)
        const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })

        return (
          <group key={index}>
            <mesh geometry={geometry} material={material} />
            <lineSegments geometry={edgeGeometry} material={edgeMaterial} />
          </group>
        )
      })}
    </group>
  )
})
VisualizeMultipleMeshes.displayName = 'VisualizeMultipleMeshes'

/** 
 * VisualizeComponent 
 */
function VisualizeComponent({
  component_data,
  geometryMode,
  visibleMeshes = [],
  externalMeshes = [],
  isLoadingExternal = false,
  geometryError = null
}: {
  component_data: ComponentModel
  geometryMode: GeometryMode
  visibleMeshes?: boolean[]
  externalMeshes?: THREE.Group[]
  isLoadingExternal?: boolean
  geometryError?: string | null
}) {
  if (!component_data.geometry) return null
  
  // Infer visualization type based on geometry content rather than just type field
  const geometry = component_data.geometry as ComponentGeometry
  const extrusion = geometry.extrusion as ComponentExtrusion | undefined
  const mesh = geometry.mesh as ComponentMesh | undefined
  const meshes = geometry.meshes as ComponentMesh[] | undefined
  
  const hasExtrusion = extrusion?.profile && extrusion?.height
  const hasMesh = mesh?.v && mesh?.f
  const hasMultipleMeshes = meshes && meshes.length > 0
  
  if (hasExtrusion) {
    return <VisualizeSheet component_data={component_data} />
  } else if (hasMultipleMeshes) {
    return <VisualizeMultipleMeshes component_data={component_data} geometryMode={geometryMode} visibleMeshes={visibleMeshes} externalMeshes={externalMeshes} isLoadingExternal={isLoadingExternal} geometryError={geometryError} />
  } else if (hasMesh) {
    return <VisualizeMesh component_data={component_data} geometryMode={geometryMode} visibleMeshes={visibleMeshes} externalMeshes={externalMeshes} isLoadingExternal={isLoadingExternal} geometryError={geometryError} />
  }
  
  // Fallback to type-based logic if geometry inference fails
  if (component_data.type === 'sheet') {
    return <VisualizeSheet component_data={component_data} />
  } else {
    return <VisualizeMesh component_data={component_data} geometryMode={geometryMode} visibleMeshes={visibleMeshes} externalMeshes={externalMeshes} isLoadingExternal={isLoadingExternal} geometryError={geometryError} />
  }
}

/**
 * ComponentViewer
 */
export default function ComponentViewer({ component_data }: { component_data: ComponentModel }) {
  // Call ALL hooks FIRST, unconditionally
  const [geometryMode, setGeometryMode] = useState<GeometryMode>('primitive')
  const [visibleMeshes, setVisibleMeshes] = useState<boolean[]>([])
  const [externalMeshes, setExternalMeshes] = useState<THREE.Group[]>([])
  const [isLoadingExternal, setIsLoadingExternal] = useState(false)
  const [geometryError, setGeometryError] = useState<string | null>(null)
  const [showMarkerPoints, setShowMarkerPoints] = useState<boolean>(true)

  const isSheet = component_data.type === 'sheet'
  const geometry = component_data.geometry as ComponentGeometry
  const meshes = useMemo(() => (geometry?.meshes || []) as ComponentMesh[], [geometry?.meshes])
  const hasMultipleMeshes = meshes && meshes.length > 0
  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'
  
  // Extract marker points data
  const markerPoints = useMemo(() => {
    const points = component_data.marker_points
    if (Array.isArray(points) && points.length > 0) {
      return points.filter(point => Array.isArray(point) && point.length >= 3)
    }
    return []
  }, [component_data.marker_points])
  const hasMarkerPoints = markerPoints.length > 0

  // Load external geometry centrally
  useEffect(() => {
    let isMounted = true
    if (isExternalMode && component_data.type !== 'sheet' && component_data._id) {
      setIsLoadingExternal(true)
      setGeometryError(null)
      loadExternalGeometry(component_data._id.toString(), geometryMode)
        .then((result) => {
          if (isMounted) {
            if (result.success) {
              setExternalMeshes(result.meshes)
              setGeometryError(null)
              // Initialize visibility state for external meshes
              setVisibleMeshes(new Array(result.meshes.length).fill(true))
            } else {
              setExternalMeshes([])
              setGeometryError(result.message)
              setVisibleMeshes([])
            }
            setIsLoadingExternal(false)
          }
        })
        .catch(() => {
          if (isMounted) {
            setExternalMeshes([])
            setGeometryError(`Failed to load ${geometryMode} geometry`)
            setVisibleMeshes([])
            setIsLoadingExternal(false)
          }
        })
    } else {
      setExternalMeshes([])
      setIsLoadingExternal(false)
      setGeometryError(null)
      // Initialize visibility state for primitive meshes
      if (hasMultipleMeshes && meshes) {
        setVisibleMeshes(new Array(meshes.length).fill(true))
      } else if (geometry?.mesh) {
        setVisibleMeshes([true]) // Single mesh
      } else {
        setVisibleMeshes([])
      }
    }
    return () => {
      isMounted = false
    }
  }, [geometryMode, component_data, isExternalMode, hasMultipleMeshes, meshes, geometry?.mesh])

  const onModeChange: React.ChangeEventHandler<HTMLSelectElement> = (e) => {
    const v = e.target.value as GeometryMode
    setGeometryMode(v)
  }

  const toggleMeshVisibility = (index: number) => {
    setVisibleMeshes(prev => {
      const newVisibility = [...prev]
      newVisibility[index] = !newVisibility[index]
      return newVisibility
    })
  }

  const toggleMarkerPointsVisibility = () => {
    setShowMarkerPoints(prev => !prev)
  }

  // Handle the conditional logic AFTER all hooks
  if (!component_data.geometry) {
    return <ComponentViewerSkeleton message="No Geometry Available" />
  }

  return (
    <Card className="flex flex-col w-full overflow-x-auto">
      <div className="relative h-[30dvh] sm:h-[40dvh]">
        {/* Overlay UI */}
        <div className="absolute top-1 left-1 sm:top-2 sm:left-2 z-10 bg-accent-foreground bg-opacity-90 p-1 sm:p-2 rounded shadow text-xs sm:text-sm max-w-[calc(100%-0.5rem)] sm:max-w-[calc(100%-1rem)]">
          <div className="mb-1 sm:mb-2 flex flex-col gap-1">
            <label htmlFor="geometryModeSelect" className="text-xs sm:text-sm">Geometry Resolution:</label>
            <select
              id="geometryModeSelect"
              value={geometryMode}
              onChange={onModeChange}
              disabled={isSheet}
              className="w-full rounded border bg-accent-foreground p-1 text-xs sm:text-sm"
            >
              <option value="primitive">Primitive</option>
              <option value="reduced">Reduced</option>
              <option value="detailed">Detailed</option>
            </select>
          </div>
          
          {/* Mesh Visibility Controls */}
          {((hasMultipleMeshes && geometryMode === 'primitive') || (isExternalMode && externalMeshes.length > 0)) && (
            <div className="mb-1 sm:mb-2 flex flex-col gap-1">
              <label className="text-xs sm:text-sm">Mesh Visibility:</label>
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {(isExternalMode ? Array.from({ length: externalMeshes.length }, (_, i) => i) : meshes.map((_, i) => i)).map((index: number) => (
                  <label key={index} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={visibleMeshes[index] || false}
                      onChange={() => toggleMeshVisibility(index)}
                      className="rounded"
                    />
                    <span>{isExternalMode ? `External Mesh ${index + 1}` : `Mesh ${index + 1}`}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Marker Points Visibility Control */}
          {hasMarkerPoints && (
            <div className="mb-1 sm:mb-2 flex flex-col gap-1">
              <label className="text-xs sm:text-sm">Marker Points:</label>
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={showMarkerPoints}
                    onChange={toggleMarkerPointsVisibility}
                    className="rounded"
                  />
                  <span className="text-xs sm:text-sm">Show ({markerPoints.length})</span>
                </label>
              </div>
            </div>
          )}
        </div>

        <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds fit clip observe margin={1.2} maxDuration={1}>
            <VisualizeComponent 
              component_data={component_data} 
              geometryMode={geometryMode} 
              visibleMeshes={visibleMeshes} 
              externalMeshes={isExternalMode ? externalMeshes : []}
              isLoadingExternal={isLoadingExternal}
              geometryError={geometryError}
            />
            <MarkerPoints 
              markerPoints={markerPoints} 
              visible={showMarkerPoints} 
            />
          </Bounds>

          <axesHelper args={[0.1]} />
          <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </Card>
  )
}
