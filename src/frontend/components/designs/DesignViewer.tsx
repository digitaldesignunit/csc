'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { DesignModel, DesignComponent } from '@/generated/DesignModel'
import { DesignAdditionalGeometry, DesignInsertionFrame } from '@/generated/DesignModel'
import { loadDesignSnapshotGeometry } from '@/lib/designViewerGeometry'
import { Card } from '@/components/ui/card'
import { Bounds, OrbitControls, Html } from '@react-three/drei'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ViewerMenu, MenuSection, CheckboxControl, SelectControl, ScrollableCheckboxList } from '@/components/viewer/ViewerMenu'

// Scale factor for converting units to meters in THREE
const scale = 0.001

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

/**
 * Placement matrix from a Rhino Z-up iframe into the Three.js Y-up scene.
 * Snapshot mesh data is left in Rhino Z-up; this matrix is the only axis
 * conversion (legacy OBJ used a separate per-mesh rotateX — not used here).
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
 * Convert geometry data to THREE.js meshes for additional geometry (no coordinate system transformation)
 */
function convertAdditionalGeometryToMeshes(geometry: unknown, itemId: string): THREE.Group[] {
  const meshes: THREE.Group[] = []
  
  try {
    debugLog(`Converting additional geometry for ${itemId}:`, geometry)
    
    const geo = geometry as Record<string, unknown> | null
    const extrusion = geo?.extrusion as Record<string, unknown> | undefined
    const meshesArray = geo?.meshes as unknown[] | undefined

    const hasExtrusion = extrusion?.profile && extrusion?.height
    const hasMultipleMeshes = meshesArray && Array.isArray(meshesArray) && meshesArray.length > 0

    if (hasExtrusion) {
      debugLog(`Processing additional extrusion geometry for ${itemId}`)
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
      // No coordinate system transformation for additional geometry
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
      faceMesh.name = `extrusion_face_${itemId}`
      
      // Create edge geometry
      const edgeGeometry = new THREE.EdgesGeometry(extrudeGeometry)
      const edgeMesh = new THREE.LineSegments(edgeGeometry, edgeMaterial)
      edgeMesh.name = `extrusion_edge_${itemId}`
      
      const group = new THREE.Group()
      group.add(faceMesh)
      group.add(edgeMesh)
      meshes.push(group)
      
    } else if (hasMultipleMeshes) {
      debugLog(`Processing additional multiple meshes for ${itemId}`)
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
          
          // No coordinate system transformation for additional geometry
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
          threeMesh.name = `mesh_${index}_${itemId}`
          
          // Create edge geometry and material
          const edgeGeometry = new THREE.EdgesGeometry(threeGeometry)
          const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })
          const edgeMesh = new THREE.LineSegments(edgeGeometry, edgeMaterial)
          edgeMesh.name = `mesh_edge_${index}_${itemId}`
          
          const group = new THREE.Group()
          group.add(threeMesh)
          group.add(edgeMesh)
          meshes.push(group)
        }
      })
    }

  } catch (error) {
    debugLog(`Error converting additional geometry for ${itemId}:`, error)
  }

  return meshes
}

interface DesignViewerProps {
  design: DesignModel
}

export default function DesignViewer({ 
  design
}: DesignViewerProps) {
  const [geometryMode, setGeometryMode] = useState<'primitive' | 'reduced' | 'detailed'>('primitive')
  const [loadedSnapshots, setLoadedSnapshots] = useState<Map<string, THREE.Group[]>>(new Map())
  const [loadedReinforcements, setLoadedReinforcements] = useState<Map<string, THREE.Group[]>>(new Map())
  const [loadingStates, setLoadingStates] = useState<Map<string, boolean>>(new Map())
  const [errorStates, setErrorStates] = useState<Map<string, string>>(new Map())
  const [visibleSnapshots, setVisibleSnapshots] = useState<Map<string, boolean>>(new Map())
  const [visibleAdditionalGeometry, setVisibleAdditionalGeometry] = useState<Map<string, boolean>>(new Map())
  const [showEdges, setShowEdges] = useState<boolean>(true)
  const [showReinforcements, setShowReinforcements] = useState<boolean>(true)

  // Initialize visibility states
  useEffect(() => {
    const initialSnapshotVisibility = new Map<string, boolean>()
    design.components.forEach(comp => {
      initialSnapshotVisibility.set(comp.snapshot, true)
    })
    setVisibleSnapshots(initialSnapshotVisibility)

    const initialAdditionalGeometryVisibility = new Map<string, boolean>()
    if (Array.isArray(design.additional_geometry)) {
      design.additional_geometry.forEach((item, index) => {
        const itemId = item._id || `additional_${index}`
        initialAdditionalGeometryVisibility.set(itemId, true)
      })
    }
    setVisibleAdditionalGeometry(initialAdditionalGeometryVisibility)
  }, [design.components, design.additional_geometry])

  // Load snapshot geometries when mode changes
  useEffect(() => {
    const loadAllGeometries = async () => {
      setLoadedSnapshots(new Map())
      setLoadedReinforcements(new Map())
      setErrorStates(new Map())
      const newLoadedSnapshots = new Map<string, THREE.Group[]>()
      const newLoadedReinforcements = new Map<string, THREE.Group[]>()
      const newErrorStates = new Map<string, string>()

      // Set default edge visibility based on geometry mode
      if (geometryMode === 'primitive') {
        setShowEdges(true) // Show edges for primitive geometry
      } else {
        setShowEdges(false) // Hide edges for external geometry by default
      }

      // Load each component one by one to avoid overwhelming the system
      for (const comp of design.components) {
        // Set loading state for this component
        setLoadingStates(prev => {
          const newMap = new Map(prev)
          newMap.set(comp.snapshot, true)
          return newMap
        })

        try {
          debugLog(`Loading ${geometryMode} geometry for component ${comp.snapshot}`)
          const result = await loadDesignSnapshotGeometry(comp.snapshot, geometryMode)
          
          if (result.success) {
            newLoadedSnapshots.set(comp.snapshot, result.meshes)
            newLoadedReinforcements.set(comp.snapshot, result.reinforcements)
            newErrorStates.delete(comp.snapshot)
            debugLog(
              `Successfully loaded ${result.meshes.length} meshes and `
              + `${result.reinforcements.length} reinforcement group(s) `
              + `for snapshot ${comp.snapshot}`,
            )
          } else {
            newErrorStates.set(comp.snapshot, result.message)
            debugLog(`Failed to load geometry for snapshot ${comp.snapshot}: ${result.message}`)
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Unknown error'
          newErrorStates.set(comp.snapshot, errorMessage)
          debugLog(`Error loading geometry for component ${comp.snapshot}:`, errorMessage)
        }
        
        // Update states for this component
        setLoadingStates(prev => {
          const newMap = new Map(prev)
          newMap.set(comp.snapshot, false)
          return newMap
        })
        
        setLoadedSnapshots(new Map(newLoadedSnapshots))
        setLoadedReinforcements(new Map(newLoadedReinforcements))
        setErrorStates(new Map(newErrorStates))
        
        // Small delay to prevent overwhelming the system
        await new Promise(resolve => setTimeout(resolve, 100))
      }
    }

    loadAllGeometries()
  }, [design.components, geometryMode])

  const toggleSnapshotVisibility = (snapshotId: string) => {
    setVisibleSnapshots(prev => {
      const newMap = new Map(prev)
      newMap.set(snapshotId, !newMap.get(snapshotId))
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

  const allSnapshotsVisible = useMemo(() => {
    return Array.from(visibleSnapshots.values()).every(visible => visible)
  }, [visibleSnapshots])

  const allAdditionalGeometryVisible = useMemo(() => {
    return Array.from(visibleAdditionalGeometry.values()).every(visible => visible)
  }, [visibleAdditionalGeometry])

  const reinforcementCount = useMemo(() => {
    let count = 0
    loadedReinforcements.forEach((groups) => {
      count += groups.length
    })
    return count
  }, [loadedReinforcements])

  const hasReinforcements = reinforcementCount > 0

  const toggleAllSnapshots = () => {
    const newVisibility = !allSnapshotsVisible
    setVisibleSnapshots(prev => {
      const newMap = new Map(prev)
      design.components.forEach(comp => {
        newMap.set(comp.snapshot, newVisibility)
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
    loadedSnapshots.forEach(componentMeshes => {
      componentMeshes.forEach(group => {
        group.traverse(obj => {
          if ((obj as THREE.LineSegments).isLineSegments && obj.name.endsWith('_edges')) {
            obj.visible = showEdges
          }
        })
      })
    })
  }, [showEdges, geometryMode, loadedSnapshots])


  // Build menu sections
  const menuSections: MenuSection[] = [
    // Geometry Resolution section
    {
      id: 'geometry-mode',
      content: (
        <SelectControl
          id="geometryModeSelect"
          label="Geometry Resolution:"
          value={geometryMode}
          onChange={(e) => setGeometryMode(e.target.value as 'primitive' | 'reduced' | 'detailed')}
          options={[
            { value: 'primitive', label: 'Primitive' },
            { value: 'reduced', label: 'Reduced' },
            { value: 'detailed', label: 'Detailed' }
          ]}
        />
      )
    },
    // Global toggles section
    {
      id: 'global-toggles',
      content: (
        <div className="flex flex-col gap-1">
          <CheckboxControl
            id="toggle-all"
            label="Show All Snapshots"
            checked={allSnapshotsVisible}
            onChange={toggleAllSnapshots}
          />
          <CheckboxControl
            id="toggle-edges"
            label="Show Edges"
            checked={showEdges}
            onChange={(checked) => setShowEdges(checked)}
          />
          {Array.isArray(design.additional_geometry) && design.additional_geometry.length > 0 && (
            <CheckboxControl
              id="toggle-all-additional"
              label="Show All Additional Geometry"
              checked={allAdditionalGeometryVisible}
              onChange={toggleAllAdditionalGeometry}
            />
          )}
          {hasReinforcements && (
            <CheckboxControl
              id="toggle-reinforcements"
              label={`Show Reinforcement (${reinforcementCount})`}
              checked={showReinforcements}
              onChange={(checked) => setShowReinforcements(checked)}
            />
          )}
        </div>
      )
    },
    // Snapshot visibility section
    {
      id: 'snapshot-visibility',
      title: 'Snapshot Visibility',
      collapsible: true,
      defaultExpanded: true,
      itemCount: design.components.length,
      content: (
        <ScrollableCheckboxList
          items={design.components.map((comp, index) => {
            const isVisible = visibleSnapshots.get(comp.snapshot) ?? true
            const isLoading = loadingStates.get(comp.snapshot) ?? false
            const error = errorStates.get(comp.snapshot)
            return {
              id: comp.snapshot,
              label: isLoading ? 'Loading...' : error ? `Error: ${error}` : `Snapshot ${index + 1}`,
              checked: isVisible,
              disabled: isLoading || !!error
            }
          })}
          onToggle={toggleSnapshotVisibility}
        />
      )
    }
  ]

  // Add Additional Geometry section if present
  if (Array.isArray(design.additional_geometry) && design.additional_geometry.length > 0) {
    menuSections.push({
      id: 'additional-geometry',
      title: 'Additional Geometry',
      collapsible: true,
      defaultExpanded: true,
      itemCount: design.additional_geometry.length,
      content: (
        <ScrollableCheckboxList
          items={design.additional_geometry.map((item, index) => {
            const itemId = item._id || `additional_${index}`
            const isVisible = visibleAdditionalGeometry.get(itemId) ?? true
            const itemName = typeof item.name === 'string' && item.name.trim() 
              ? item.name 
              : `Additional Geometry ${index + 1}`
            return {
              id: itemId,
              label: itemName,
              checked: isVisible
            }
          })}
          onToggle={toggleAdditionalGeometryVisibility}
        />
      )
    })
  }

  return (
    <div className="flex flex-col md:flex-row gap-2 w-full">
      {/* Menu - left on desktop, top on mobile */}
      <div className="w-full md:w-64 md:flex-shrink-0 order-2 md:order-1 md:h-[50dvh]">
        <ViewerMenu sections={menuSections} className="h-full" />
      </div>

      {/* Viewport - right on desktop, bottom on mobile */}
      <Card className="flex-1 overflow-hidden order-1 md:order-2 h-[30dvh] sm:h-[40dvh] md:h-[50dvh] p-0">
        <div className="relative w-full h-full">
          <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds fit clip observe margin={1.2} maxDuration={1}>
            {design.components.map((comp) => {
              const meshes = loadedSnapshots.get(comp.snapshot) || []
              const reinforcements = loadedReinforcements.get(comp.snapshot) || []
              const isVisible = visibleSnapshots.get(comp.snapshot) ?? true
              const isLoading = loadingStates.get(comp.snapshot) ?? false
              const error = errorStates.get(comp.snapshot)

              debugLog(`Rendering component ${comp.snapshot}:`, {
                meshes: meshes.length,
                isVisible,
                isLoading,
                error
              })

              if (!isVisible) {
                debugLog(`Component ${comp.snapshot} not visible, skipping render`)
                return null
              }

              if (isLoading) {
                debugLog(`Component ${comp.snapshot} is loading, showing loading indicator`)
                return (
                  <group key={comp.snapshot} scale={[scale, scale, scale]}>
                    <group matrix={createTransformMatrix(comp.iframe)} matrixAutoUpdate={false}>
                      <mesh>
                        <Html center>
                          <LoadingSpinner />
                        </Html>
                      </mesh>
                    </group>
                  </group>
                )
              }

              if (error) {
                debugLog(`Component ${comp.snapshot} has error:`, error)
                return (
                  <group key={comp.snapshot} scale={[scale, scale, scale]}>
                    <group matrix={createTransformMatrix(comp.iframe)} matrixAutoUpdate={false}>
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
                              <strong>{error}</strong>
                            </div>
                          </div>
                        </Html>
                      </mesh>
                    </group>
                  </group>
                )
              }

              if (meshes.length === 0 && reinforcements.length === 0) {
                debugLog(`Component ${comp.snapshot} has no renderable geometry`)
                return null
              }

              debugLog(
                `Rendering component ${comp.snapshot} with ${meshes.length} meshes `
                + `and ${reinforcements.length} reinforcement group(s)`,
              )
              debugLog(`Geometry mode: ${geometryMode}, Component iframe:`, comp.iframe)

              return (
                <group key={comp.snapshot} scale={[scale, scale, scale]}>
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
                        <primitive key={`${comp.snapshot}_${index}`} object={meshGroup} />
                      )
                    })}
                    {showReinforcements && reinforcements.map((reinforcementGroup, index) => (
                      <primitive
                        key={`${comp.snapshot}_reinforcement_${index}`}
                        object={reinforcementGroup}
                      />
                    ))}
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
                
                const meshes = convertAdditionalGeometryToMeshes(item.geometry as unknown, itemId)
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
    </div>
  )
}
