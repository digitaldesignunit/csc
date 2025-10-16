'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { DesignModel, DesignComponent } from '@/generated/DesignModel'
import { DesignAdditionalGeometry, DesignInsertionFrame } from '@/generated/DesignModel'
import { Card } from '@/components/ui/card'
import { Bounds, OrbitControls } from '@react-three/drei'
import { Skeleton } from '@/components/ui/skeleton'
import { Checkbox } from '@/components/ui/checkbox'

// Scale factor for converting units to meters in THREE
const scale = 0.001

// Simple in-memory cache for external geometry with ETag support
interface CachedGeometry {
  meshes: THREE.Group[] | null
  etag?: string
  timestamp: number
}

const externalGeometryCache = new Map<string, CachedGeometry>()

// Simple debug logging for dev mode only
const isDev = process.env.NODE_ENV === 'development'
const debugLog = (message: string, ...args: unknown[]) => {
  if (isDev) {
    console.log(`[DesignViewer] ${message}`, ...args)
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
 * Create transformation matrix from iframe, converting from Rhino XYZ to Three.js coordinate system
 */
function createTransformMatrix(iframe: DesignComponent['iframe']): THREE.Matrix4 {
  const matrix = new THREE.Matrix4()
  
  // Convert position from Rhino XYZ to Three.js coordinate system
  // Rhino: X=right, Y=back, Z=up
  // Three.js: X=right, Y=up, Z=forward (out of screen)
  // So: Rhino(X,Y,Z) -> Three.js(X,Z,-Y)
  const position = new THREE.Vector3(
    iframe.o[0],  // X stays the same
    iframe.o[2],  // Z becomes Y (up)
    -iframe.o[1]  // -Y becomes Z (forward)
  )
  
  // Convert axis vectors from Rhino XYZ to Three.js coordinate system
  // Apply the same transformation to each axis vector
  const xAxis = new THREE.Vector3(
    iframe.x[0],  // X component stays the same
    iframe.x[2],  // Z component becomes Y
    -iframe.x[1]  // -Y component becomes Z
  )
  const yAxis = new THREE.Vector3(
    iframe.y[0],  // X component stays the same
    iframe.y[2],  // Z component becomes Y
    -iframe.y[1]  // -Y component becomes Z
  )
  const zAxis = new THREE.Vector3(
    iframe.z[0],  // X component stays the same
    iframe.z[2],  // Z component becomes Y
    -iframe.z[1]  // -Y component becomes Z
  )
  
  // Debug logging for coordinate transformation
  debugLog(`Coordinate transformation for iframe:`, {
    original: {
      position: iframe.o,
      xAxis: iframe.x,
      yAxis: iframe.y,
      zAxis: iframe.z
    },
    transformed: {
      position: [position.x, position.y, position.z],
      xAxis: [xAxis.x, xAxis.y, xAxis.z],
      yAxis: [yAxis.x, yAxis.y, yAxis.z],
      zAxis: [zAxis.x, zAxis.y, zAxis.z]
    }
  })
  
  // Create rotation matrix from transformed axis vectors
  const rotationMatrix = new THREE.Matrix4()
  rotationMatrix.set(
    xAxis.x, yAxis.x, zAxis.x, 0,
    xAxis.y, yAxis.y, zAxis.y, 0,
    xAxis.z, yAxis.z, zAxis.z, 0,
    0, 0, 0, 1
  )
  
  // Combine rotation and translation
  matrix.multiplyMatrices(
    new THREE.Matrix4().makeTranslation(position.x, position.y, position.z),
    rotationMatrix
  )
  
  return matrix
}

/**
 * Convert geometry data to THREE.js meshes using ComponentViewer logic
 */
function convertGeometryToMeshes(geometry: unknown, componentId: string): THREE.Group[] {
  const meshes: THREE.Group[] = []
  
  try {
    debugLog(`Converting geometry for ${componentId}:`, geometry)
    
    const geo = geometry as Record<string, unknown> | null
    const extrusion = geo?.extrusion as Record<string, unknown> | undefined
    const mesh = geo?.mesh as Record<string, unknown> | undefined
    const meshesArray = geo?.meshes as unknown[] | undefined
    
    const hasExtrusion = extrusion?.profile && extrusion?.height
    const hasMesh = mesh?.v && mesh?.f
    const hasMultipleMeshes = meshesArray && Array.isArray(meshesArray) && meshesArray.length > 0
    
    if (hasExtrusion) {
      debugLog(`Processing extrusion geometry for ${componentId}`)
      // Handle extrusion geometry
      const points = extrusion.profile as number[][]
      const height = extrusion.height as number
      const shape = new THREE.Shape()
      
      shape.moveTo(points[0][0], points[0][1])
      points.forEach((p: number[], i: number) => {
        if (i > 0) shape.lineTo(p[0], p[1])
      })
      
      // Create extrusion geometry
      const extrudeSettings = { 
        steps: 2, 
        depth: height, 
        bevelEnabled: false 
      }
      const extrudeGeometry = new THREE.ExtrudeGeometry(shape, extrudeSettings)
      extrudeGeometry.translate(0, 0, -height * 0.5)
      // Note: No rotateX needed here - coordinate system conversion is handled by iframe transformation
      extrudeGeometry.computeVertexNormals()
      extrudeGeometry.normalizeNormals()
      
      // Create face material
      const faceMaterial = new THREE.MeshBasicMaterial({ 
        color: (geo?.color as number) || 0x888888,
        side: THREE.DoubleSide
      })
      
      // Create edge material
      const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })
      
      // Create face mesh
      const faceMesh = new THREE.Mesh(extrudeGeometry, faceMaterial)
      faceMesh.name = `extrusion_face_${componentId}`
      
      // Create edge geometry
      const edgeGeometry = new THREE.EdgesGeometry(extrudeGeometry)
      const edgeMesh = new THREE.LineSegments(edgeGeometry, edgeMaterial)
      edgeMesh.name = `extrusion_edge_${componentId}`
      
      const group = new THREE.Group()
      group.add(faceMesh)
      group.add(edgeMesh)
      meshes.push(group)
      
    } else if (hasMultipleMeshes) {
      debugLog(`Processing multiple meshes for ${componentId}`)
      // Handle array of meshes
      meshesArray.forEach((meshData: unknown, index: number) => {
        const mesh = meshData as Record<string, unknown>
        if (mesh.v && mesh.f) {
          const threeGeometry = new THREE.BufferGeometry()
          
          // Convert vertices from [[x,y,z], [x,y,z], ...] to [x,y,z,x,y,z,...]
          const vertices = (mesh.v as number[][]).flat()
          threeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
          
          // Convert faces from [[a,b,c], [a,b,c], ...] to [a,b,c,a,b,c,...]
          const faces = (mesh.f as number[][]).flat()
          threeGeometry.setIndex(faces)
          
          threeGeometry.computeVertexNormals()
          threeGeometry.normalizeNormals()
          
          // Set colors if available
          let material: THREE.MeshBasicMaterial
          if (mesh.c && Array.isArray(mesh.c) && mesh.c.length > 0) {
            // Convert colors from [[r,g,b], [r,g,b], ...] to [r,g,b,r,g,b,...]
            const colors = (mesh.c as number[][]).flat()
            const normalizedColors = normalizeColors(colors)
            threeGeometry.setAttribute('color', new THREE.Float32BufferAttribute(normalizedColors, 3))
            material = new THREE.MeshBasicMaterial({ 
              vertexColors: true,
              side: THREE.DoubleSide
            })
          } else {
            // Use a default color
            material = new THREE.MeshBasicMaterial({ 
              color: 0x888888,
              side: THREE.DoubleSide
            })
          }
          
          const threeMesh = new THREE.Mesh(threeGeometry, material)
          threeMesh.name = `mesh_${index}_${componentId}`
          
          // Create edge geometry and material
          const edgeGeometry = new THREE.EdgesGeometry(threeGeometry)
          const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })
          const edgeMesh = new THREE.LineSegments(edgeGeometry, edgeMaterial)
          edgeMesh.name = `mesh_edge_${index}_${componentId}`
          
          const group = new THREE.Group()
          group.add(threeMesh)
          group.add(edgeMesh)
          meshes.push(group)
        }
      })
      
    } else if (hasMesh) {
      debugLog(`Processing single mesh for ${componentId}`)
      // Handle single mesh
      const threeGeometry = new THREE.BufferGeometry()
      
      // Convert vertices from [[x,y,z], [x,y,z], ...] to [x,y,z,x,y,z,...]
      const vertices = (mesh.v as number[][]).flat()
      threeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
      
      // Convert faces from [[a,b,c], [a,b,c], ...] to [a,b,c,a,b,c,...]
      const faces = (mesh.f as number[][]).flat()
      threeGeometry.setIndex(faces)
      
      threeGeometry.computeVertexNormals()
      threeGeometry.normalizeNormals()
      
      // Set colors if available
      let material: THREE.MeshBasicMaterial
      if (mesh.c && Array.isArray(mesh.c) && mesh.c.length > 0) {
        // Convert colors from [[r,g,b], [r,g,b], ...] to [r,g,b,r,g,b,...]
        const colors = (mesh.c as number[][]).flat()
        const normalizedColors = normalizeColors(colors)
        threeGeometry.setAttribute('color', new THREE.Float32BufferAttribute(normalizedColors, 3))
        material = new THREE.MeshBasicMaterial({ 
          vertexColors: true,
          side: THREE.DoubleSide
        })
      } else {
        // Use a default color
        material = new THREE.MeshBasicMaterial({ 
          color: 0x888888,
          side: THREE.DoubleSide
        })
      }
      
      const threeMesh = new THREE.Mesh(threeGeometry, material)
      threeMesh.name = `mesh_${componentId}`
      
      // Create edge geometry and material
      const edgeGeometry = new THREE.EdgesGeometry(threeGeometry)
      const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })
      const edgeMesh = new THREE.LineSegments(edgeGeometry, edgeMaterial)
      edgeMesh.name = `mesh_edge_${componentId}`
      
      const group = new THREE.Group()
      group.add(threeMesh)
      group.add(edgeMesh)
      meshes.push(group)
    }
    
  } catch (error) {
    debugLog(`Error converting geometry for ${componentId}:`, error)
  }
  
  return meshes
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

/**
 * Load external geometry (reduced or detailed) for a component
 */
async function loadExternalGeometry(
  componentId: string,
  mode: 'reduced' | 'detailed'
): Promise<GeometryLoadResult> {
  debugLog(`Loading ${mode} geometry for component ${componentId}`)
  
  const cacheKey = `${componentId}_${mode}`
  const cached = externalGeometryCache.get(cacheKey)
  
  // Check if we have valid cached data
  if (cached && cached.meshes) {
    debugLog(`Using cached geometry for ${componentId}: ${cached.meshes.length} meshes`)
    return { success: true, meshes: cached.meshes }
  }
  
  // Check if we have cached "not found" state
  if (cached && cached.meshes === null) {
    return { 
      success: false, 
      error: 'not_found', 
      message: `No ${mode} geometry available for this component` 
    }
  }

  const geometryRoute = mode === 'reduced' ? 'geometry_reduced' : 'geometry_detailed'
  const objUrl = `/api/backend/components/${componentId}/${geometryRoute}`

  try {
    // Prepare headers for conditional request
    const headers: HeadersInit = { credentials: 'include' }
    if (cached?.etag) {
      headers['If-None-Match'] = cached.etag
    }

    // Fetch and parse OBJ content manually
    debugLog(`Fetching OBJ content...`)
    const response = await fetch(objUrl, { headers })
    
    if (response.status === 304) {
      // Not modified - use cached data
      debugLog(`Geometry not modified, using cached data`)
      if (cached && cached.meshes) {
        return { success: true, meshes: cached.meshes }
      } else {
        return { 
          success: false, 
          error: 'not_found', 
          message: `No ${mode} geometry available for this component` 
        }
      }
    }
    
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

      // Apply coordinate system transformation (Rhino Y-up to Three.js Z-up)
      geometry.rotateX(-Math.PI / 2)
      
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

      // Create group and add mesh (and edges support)
      const object = new THREE.Group()
      object.add(mesh)
      {
        const edgeGeometry = new THREE.EdgesGeometry(geometry)
        const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })
        const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial)
        edges.name = `${meshData.name}_edges`
        object.add(edges)
      }
      
      // Don't apply scaling here - it will be handled by the group scale in rendering
      threeMeshes.push(object)
    }

    debugLog(`Created ${threeMeshes.length} meshes from OBJ file`)
    threeMeshes.forEach((mesh, index) => {
      debugLog(`External mesh ${index}:`, {
        name: mesh.name,
        children: mesh.children.length,
        position: mesh.position,
        visible: mesh.visible,
        scale: mesh.scale
      })
    })

    // Extract ETag from response headers
    const etag = response.headers.get('ETag')
    debugLog(`Received ETag: ${etag}`)

    // Cache the individual meshes with ETag and timestamp
    externalGeometryCache.set(cacheKey, {
      meshes: threeMeshes,
      etag: etag || undefined,
      timestamp: Date.now()
    })
    
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
    
    // Cache the error state with timestamp
    externalGeometryCache.set(cacheKey, {
      meshes: null,
      etag: undefined,
      timestamp: Date.now()
    })
    return { success: false, error: errorType, message }
  }
}

/**
 * Load geometry for a single component
 */
async function loadComponentGeometry(
  componentId: string,
  mode: 'primitive' | 'reduced' | 'detailed' = 'primitive'
): Promise<GeometryLoadResult> {
  const cacheKey = `${componentId}_${mode}`
  const cached = externalGeometryCache.get(cacheKey)
  
  // Check cache validity (5 minutes)
  if (cached && Date.now() - cached.timestamp < 5 * 60 * 1000) {
    debugLog(`Using cached geometry for ${componentId}`)
    return { success: true, meshes: cached.meshes || [] }
  }
  
  try {
    const baseUrl = window.location.origin
    
    if (mode === 'primitive') {
      // ALWAYS fetch the full component JSON and extract primitive geometry
      debugLog(`Loading full component data for ${componentId} to extract primitive geometry`)
      
      const response = await fetch(`${baseUrl}/api/backend/components/${componentId}`, {
        cache: 'no-store',
        headers: {
          'If-None-Match': cached?.etag || '',
        },
      })
      
      if (response.status === 304) {
        debugLog(`Component data unchanged for ${componentId}, using cache`)
        return { success: true, meshes: cached?.meshes || [] }
      }
      
      if (!response.ok) {
        debugLog(`Failed to load component data for ${componentId}: ${response.status}`)
        return { success: false, error: 'network_error', message: `HTTP ${response.status}` }
      }
      
      const componentData = await response.json()
      const etag = response.headers.get('etag') || undefined
      
      debugLog(`Component data for ${componentId}:`, componentData)
      debugLog(`Geometry structure:`, componentData.geometry)
      
      // Extract geometry data using the same logic as ComponentViewer
      const geometry = componentData.geometry
      const extrusion = geometry?.extrusion
      const mesh = geometry?.mesh
      const meshes = geometry?.meshes
      
      const hasExtrusion = extrusion?.profile && extrusion?.height
      const hasMesh = mesh?.v && mesh?.f
      const hasMultipleMeshes = meshes && Array.isArray(meshes) && meshes.length > 0
      
      debugLog(`Geometry analysis for ${componentId}:`, {
        hasExtrusion,
        hasMesh,
        hasMultipleMeshes,
        extrusion: !!extrusion,
        mesh: !!mesh,
        meshes: meshes?.length || 0
      })
      
      if (!hasExtrusion && !hasMesh && !hasMultipleMeshes) {
        debugLog(`No usable geometry found in component ${componentId}`)
        debugLog(`Geometry object structure:`, JSON.stringify(geometry, null, 2))
        return { success: false, error: 'not_found', message: 'No usable geometry found in component data' }
      }
      
      // Convert geometry to THREE.js meshes using ComponentViewer logic
      const threeMeshes = convertGeometryToMeshes(geometry, componentId)
      
      debugLog(`Converted to ${threeMeshes.length} THREE.js meshes for ${componentId}`)
      threeMeshes.forEach((mesh, index) => {
        debugLog(`Mesh ${index}:`, {
          name: mesh.name,
          children: mesh.children.length,
          position: mesh.position,
          visible: mesh.visible
        })
      })
      
      // Cache the result
      externalGeometryCache.set(cacheKey, {
        meshes: threeMeshes,
        etag,
        timestamp: Date.now()
      })
      
      debugLog(`Successfully loaded ${threeMeshes.length} primitive meshes for ${componentId}`)
      return { success: true, meshes: threeMeshes }
    } else {
      // Load external geometry (reduced or detailed)
      return await loadExternalGeometry(componentId, mode)
    }
    
  } catch (error) {
    debugLog(`Error loading geometry for ${componentId}:`, error)
    return { 
      success: false, 
      error: 'network_error', 
      message: error instanceof Error ? error.message : 'Unknown error' 
    }
  }
}

interface DesignViewerProps {
  design: DesignModel
  className?: string
}

export default function DesignViewer({ 
  design, 
  className = ''
}: DesignViewerProps) {
  const [geometryMode, setGeometryMode] = useState<'primitive' | 'reduced' | 'detailed'>('primitive')
  const [loadedComponents, setLoadedComponents] = useState<Map<string, THREE.Group[]>>(new Map())
  const [loadingStates, setLoadingStates] = useState<Map<string, boolean>>(new Map())
  const [errorStates, setErrorStates] = useState<Map<string, string>>(new Map())
  const [visibleComponents, setVisibleComponents] = useState<Map<string, boolean>>(new Map())
  const [visibleAdditionalGeometry, setVisibleAdditionalGeometry] = useState<Map<string, boolean>>(new Map())
  const [showEdges, setShowEdges] = useState<boolean>(true)
  const [isLoading, setIsLoading] = useState(true)

  // Initialize visibility states
  useEffect(() => {
    const initialComponentVisibility = new Map<string, boolean>()
    design.components.forEach(comp => {
      initialComponentVisibility.set(comp.component, true)
    })
    setVisibleComponents(initialComponentVisibility)

    const initialAdditionalGeometryVisibility = new Map<string, boolean>()
    if (Array.isArray(design.additional_geometry)) {
      design.additional_geometry.forEach((item, index) => {
        const itemId = item._id || `additional_${index}`
        initialAdditionalGeometryVisibility.set(itemId, true)
      })
    }
    setVisibleAdditionalGeometry(initialAdditionalGeometryVisibility)
  }, [design.components, design.additional_geometry])

  // Load all component geometries one by one
  useEffect(() => {
    const loadAllGeometries = async () => {
      setIsLoading(true)
      const newLoadedComponents = new Map<string, THREE.Group[]>()
      const newLoadingStates = new Map<string, boolean>()
      const newErrorStates = new Map<string, string>()

      // Set loading states
      design.components.forEach(comp => {
        newLoadingStates.set(comp.component, true)
      })
      setLoadingStates(new Map(newLoadingStates))

      // Set default edge visibility based on geometry mode
      if (geometryMode === 'primitive') {
        setShowEdges(true) // Show edges for primitive geometry
      } else {
        setShowEdges(false) // Hide edges for external geometry by default
      }

      // Load each component one by one to avoid overwhelming the system
      for (const comp of design.components) {
        try {
          debugLog(`Loading ${geometryMode} geometry for component ${comp.component}`)
          const result = await loadComponentGeometry(comp.component, geometryMode)
          
          if (result.success) {
            newLoadedComponents.set(comp.component, result.meshes)
            newErrorStates.delete(comp.component)
            debugLog(`Successfully loaded ${result.meshes.length} meshes for component ${comp.component}`)
          } else {
            newErrorStates.set(comp.component, result.message)
            debugLog(`Failed to load geometry for component ${comp.component}: ${result.message}`)
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Unknown error'
          newErrorStates.set(comp.component, errorMessage)
          debugLog(`Error loading geometry for component ${comp.component}:`, errorMessage)
        }
        
        newLoadingStates.set(comp.component, false)
        setLoadingStates(new Map(newLoadingStates))
        
        // Update loaded components state after each component
        setLoadedComponents(new Map(newLoadedComponents))
        setErrorStates(new Map(newErrorStates))
        
        // Small delay to prevent overwhelming the system
        await new Promise(resolve => setTimeout(resolve, 100))
      }

      setIsLoading(false)
    }

    loadAllGeometries()
  }, [design.components, geometryMode])

  const toggleComponentVisibility = (componentId: string) => {
    setVisibleComponents(prev => {
      const newMap = new Map(prev)
      newMap.set(componentId, !newMap.get(componentId))
      return newMap
    })
  }

  const toggleAdditionalGeometryVisibility = (itemId: string) => {
    setVisibleAdditionalGeometry(prev => {
      const newMap = new Map(prev)
      newMap.set(itemId, !newMap.get(itemId))
      return newMap
    })
  }

  const allComponentsVisible = useMemo(() => {
    return Array.from(visibleComponents.values()).every(visible => visible)
  }, [visibleComponents])

  const allAdditionalGeometryVisible = useMemo(() => {
    return Array.from(visibleAdditionalGeometry.values()).every(visible => visible)
  }, [visibleAdditionalGeometry])

  const toggleAllComponents = () => {
    const newVisibility = !allComponentsVisible
    setVisibleComponents(prev => {
      const newMap = new Map(prev)
      design.components.forEach(comp => {
        newMap.set(comp.component, newVisibility)
      })
      return newMap
    })
  }

  const toggleAllAdditionalGeometry = () => {
    const newVisibility = !allAdditionalGeometryVisible
    setVisibleAdditionalGeometry(prev => {
      const newMap = new Map(prev)
      if (Array.isArray(design.additional_geometry)) {
        design.additional_geometry.forEach((item, index) => {
          const itemId = item._id || `additional_${index}`
          newMap.set(itemId, newVisibility)
        })
      }
      return newMap
    })
  }

  // Apply edge visibility to external meshes by toggling child LineSegments visibility
  useEffect(() => {
    if (geometryMode === 'primitive') return
    loadedComponents.forEach(componentMeshes => {
      componentMeshes.forEach(group => {
        group.traverse(obj => {
          if ((obj as THREE.LineSegments).isLineSegments && obj.name.endsWith('_edges')) {
            obj.visible = showEdges
          }
        })
      })
    })
  }, [showEdges, geometryMode, loadedComponents])

  if (isLoading) {
    return (
      <Card className={`p-4 ${className}`}>
        <div className="space-y-4">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-64 w-full" />
        </div>
      </Card>
    )
  }

  return (
    <Card className="flex flex-col w-full overflow-x-auto">
      <div className="relative h-[30dvh] sm:h-[40dvh]">
        {/* Overlay UI */}
        <div className="absolute top-1 left-1 sm:top-2 sm:left-2 z-10 bg-accent-foreground bg-opacity-90 p-1 sm:p-2 rounded shadow text-xs sm:text-sm max-w-[calc(100%-0.5rem)] sm:max-w-[calc(100%-1rem)]">
          <div className="mb-1 sm:mb-2 flex flex-col gap-1">
            <label className="text-xs sm:text-sm">Design Assembly</label>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="toggle-all"
                checked={allComponentsVisible}
                onCheckedChange={toggleAllComponents}
              />
              <label htmlFor="toggle-all" className="text-xs">
                Show All
              </label>
            </div>
            <div className="flex items-center space-x-2 mt-1">
              <input
                id="toggle-edges"
                type="checkbox"
                checked={showEdges}
                onChange={() => setShowEdges(prev => !prev)}
                className="rounded"
              />
              <label htmlFor="toggle-edges" className="text-xs">Show Edges</label>
            </div>
          </div>
          
          {/* Geometry Mode Selector */}
          <div className="mb-1 sm:mb-2 flex flex-col gap-1">
            <label htmlFor="geometryModeSelect" className="text-xs sm:text-sm">Geometry Resolution:</label>
            <select
              id="geometryModeSelect"
              value={geometryMode}
              onChange={(e) => setGeometryMode(e.target.value as 'primitive' | 'reduced' | 'detailed')}
              className="w-full rounded border bg-accent-foreground p-1 text-xs sm:text-sm"
            >
              <option value="primitive">Primitive</option>
              <option value="reduced">Reduced</option>
              <option value="detailed">Detailed</option>
            </select>
          </div>
          
          {/* Component Visibility Controls */}
          <div className="mb-1 sm:mb-2 flex flex-col gap-1">
            <label className="text-xs sm:text-sm">Component Visibility:</label>
            <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
              {design.components.map((comp, index) => {
                const isVisible = visibleComponents.get(comp.component) ?? true
                const isLoading = loadingStates.get(comp.component) ?? false
                const error = errorStates.get(comp.component)

                return (
                  <label key={comp.component} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={isVisible}
                      onChange={() => toggleComponentVisibility(comp.component)}
                      disabled={isLoading || !!error}
                      className="rounded"
                    />
                    <span className="truncate">
                      {isLoading ? 'Loading...' : error ? `Error: ${error}` : `Component ${index + 1}`}
                    </span>
                  </label>
                )
              })}
            </div>
          </div>

          {/* Additional Geometry Visibility Controls */}
          {Array.isArray(design.additional_geometry) && design.additional_geometry.length > 0 && (
            <div className="mb-1 sm:mb-2 flex flex-col gap-1">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="toggle-all-additional"
                  checked={allAdditionalGeometryVisible}
                  onCheckedChange={toggleAllAdditionalGeometry}
                />
                <label htmlFor="toggle-all-additional" className="text-xs">
                  Show All Additional Geometry
                </label>
              </div>
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {design.additional_geometry.map((item, index) => {
                  const itemId = item._id || `additional_${index}`
                  const isVisible = visibleAdditionalGeometry.get(itemId) ?? true
                  const itemName = typeof item.name === 'string' && item.name.trim() 
                    ? item.name 
                    : `Additional Geometry ${index + 1}`

                  return (
                    <label key={itemId} className="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={isVisible}
                        onChange={() => toggleAdditionalGeometryVisibility(itemId)}
                        className="rounded"
                      />
                      <span className="truncate">{itemName}</span>
                    </label>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds fit clip observe margin={1.2} maxDuration={1}>
            {design.components.map((comp) => {
              const meshes = loadedComponents.get(comp.component) || []
              const isVisible = visibleComponents.get(comp.component) ?? true
              const isLoading = loadingStates.get(comp.component) ?? false
              const error = errorStates.get(comp.component)

              debugLog(`Rendering component ${comp.component}:`, {
                meshes: meshes.length,
                isVisible,
                isLoading,
                error
              })

              if (isLoading) {
                debugLog(`Component ${comp.component} is loading, skipping render`)
                return null // Will be handled by loading state
              }

              if (error) {
                debugLog(`Component ${comp.component} has error:`, error)
                return null // Error state
              }

              if (!isVisible || meshes.length === 0) {
                debugLog(`Component ${comp.component} not visible or no meshes:`, { isVisible, meshCount: meshes.length })
                return null
              }

              debugLog(`Rendering component ${comp.component} with ${meshes.length} meshes`)
              debugLog(`Geometry mode: ${geometryMode}, Component iframe:`, comp.iframe)

              return (
                <group key={comp.component} scale={[scale, scale, scale]}>
                  <group matrix={createTransformMatrix(comp.iframe)} matrixAutoUpdate={false}>
                    {meshes.map((meshGroup, index) => {
                      // For external geometry, edges are already handled by the edge visibility effect
                      // For primitive geometry, apply edge visibility here
                      if (geometryMode === 'primitive') {
                        meshGroup.traverse(obj => {
                          if ((obj as THREE.LineSegments).isLineSegments && obj.name.includes('edge')) {
                            obj.visible = showEdges
                          }
                        })
                      }
                      return (
                        <primitive key={`${comp.component}_${index}`} object={meshGroup} />
                      )
                    })}
                  </group>
                </group>
              )
            })}

            {/* Render additional geometry embedded in the design */}
            {(
              Array.isArray(design.additional_geometry)
                ? (design.additional_geometry as DesignAdditionalGeometry[])
                : []
            ).map((item, idx) => {
              try {
                const itemId = item._id || `additional_${idx}`
                const isVisible = visibleAdditionalGeometry.get(itemId) ?? true
                
                if (!isVisible) return null
                
                const meshes = convertGeometryToMeshes(item.geometry as unknown, itemId)
                if (!meshes || meshes.length === 0) return null
                return (
                  <group key={`add_${itemId}`} scale={[scale, scale, scale]}>
                    <group matrix={createTransformMatrix(item.iframe as DesignInsertionFrame)} matrixAutoUpdate={false}>
                      {meshes.map((meshGroup, index) => {
                        meshGroup.traverse(obj => {
                          if ((obj as THREE.LineSegments).isLineSegments && obj.name.includes('edge')) {
                            obj.visible = showEdges
                          }
                        })
                        return (
                          <primitive key={`add_${itemId}_${index}`} object={meshGroup} />
                        )
                      })}
                    </group>
                  </group>
                )
              } catch (e) {
                debugLog('Failed to render additional_geometry item', item?._id, e)
                return null
              }
            })}
          </Bounds>

          <axesHelper args={[0.1]} />
          <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </Card>
  )
}
