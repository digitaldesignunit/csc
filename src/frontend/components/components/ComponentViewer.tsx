'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { ComponentPolylinePoints, ComponentData } from '@/components/common/models'
import { Card } from '@/components/ui/card'
import { Bounds, OrbitControls, Html } from '@react-three/drei'
import { rgbToHex } from '@/lib/utils'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { MTLLoader, OBJLoader } from 'three-stdlib'
import { Skeleton } from '@/components/ui/skeleton'

// Scale factor for converting units to meters in THREE
const scale = 0.001

// Simple in-memory cache for external geometry
const externalGeometryCache = new Map<string, THREE.Group | null>()

/* ───────── Type guards (no `any`) ───────── */

function isMesh(obj: THREE.Object3D): obj is THREE.Mesh<THREE.BufferGeometry, THREE.Material | THREE.Material[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (obj as any)?.isMesh === true
}
function isWithGeometry(obj: THREE.Object3D): obj is THREE.Mesh<THREE.BufferGeometry, THREE.Material | THREE.Material[]> {
  return isMesh(obj) && obj.geometry instanceof THREE.BufferGeometry
}
function isMaterial(m: unknown): m is THREE.Material {
  return !!m && typeof m === 'object' && 'uuid' in (m as Record<string, unknown>)
}
function isTexture(t: unknown): t is THREE.Texture {
  return !!t && typeof t === 'object' && 'isTexture' in (t as Record<string, unknown>)
}

/* ───────── Helpers ───────── */

function ensureNormals(object: THREE.Object3D) {
  object.traverse((child) => {
    if (isWithGeometry(child)) {
      const geometry = child.geometry
      geometry.computeVertexNormals()
      geometry.normalizeNormals()
    }
  })
}

type GeometryMode = 'primitive' | 'reduced' | 'detailed'

/** extend typings for optional three-stdlib APIs present in some versions */
type MTLLoaderWithOptional = MTLLoader & {
  setTexturePath?: (path: string) => void
  setWithCredentials?: (withCreds: boolean) => void
}
type OBJLoaderWithOptional = OBJLoader & {
  setWithCredentials?: (withCreds: boolean) => void
}

/* ───────── External geometry/mtl loading ───────── */

/**
 * Parse vertex colors from OBJ file content
 * Handles both 'vc' format and 'v' format with color data
 */
function parseVertexColorsFromOBJ(objContent: string): number[][] {
  const vertexColors: number[][] = []
  const lines = objContent.split('\n')
  let vcCount = 0
  
  for (const line of lines) {
    const trimmedLine = line.trim()
    
    // Handle 'vc' format: vc r g b
    if (trimmedLine.startsWith('vc ')) {
      const parts = trimmedLine.split(/\s+/)
      if (parts.length >= 4) {
        const r = parseFloat(parts[1])
        const g = parseFloat(parts[2])
        const b = parseFloat(parts[3])
        if (!isNaN(r) && !isNaN(g) && !isNaN(b)) {
          // Validate that colors are in 0-1 range (normalized)
          const isValidColor = r >= 0 && r <= 1 && g >= 0 && g <= 1 && b >= 0 && b <= 1
          if (isValidColor) {
            vertexColors.push([r, g, b])
            vcCount++
            if (vcCount <= 3) { // Log first few for debugging
              console.log(`Parsed vc: r=${r}, g=${g}, b=${b} (normalized 0-1 range)`)
            }
          } else {
            console.warn(`Invalid vertex color values (not in 0-1 range): r=${r}, g=${g}, b=${b}`)
          }
        }
      }
    }
    // Handle 'v' format with colors: v x y z r g b
    else if (trimmedLine.startsWith('v ') && !trimmedLine.startsWith('vt ') && !trimmedLine.startsWith('vn ')) {
      const parts = trimmedLine.split(/\s+/)
      if (parts.length >= 7) {
        const r = parseFloat(parts[4])
        const g = parseFloat(parts[5])
        const b = parseFloat(parts[6])
        if (!isNaN(r) && !isNaN(g) && !isNaN(b)) {
          // Validate that colors are in 0-1 range (normalized)
          const isValidColor = r >= 0 && r <= 1 && g >= 0 && g <= 1 && b >= 0 && b <= 1
          if (isValidColor) {
            vertexColors.push([r, g, b])
          } else {
            console.warn(`Invalid vertex color values (not in 0-1 range): r=${r}, g=${g}, b=${b}`)
          }
        }
      }
    }
  }
  
  console.log(`Total vertex colors parsed: ${vertexColors.length}`)
  return vertexColors
}

type GeometryLoadResult = {
  success: true
  object: THREE.Group
} | {
  success: false
  error: 'not_found' | 'network_error' | 'parse_error'
  message: string
}

async function loadExternalGeometry(
  componentId: string,
  mode: Exclude<GeometryMode, 'primitive'>
): Promise<GeometryLoadResult> {
  const cacheKey = `${componentId}:${mode}`
  if (externalGeometryCache.has(cacheKey)) {
    const cached = externalGeometryCache.get(cacheKey)
    if (cached) {
      return { success: true, object: cached }
    } else {
      return { 
        success: false, 
        error: 'not_found', 
        message: `No ${mode} geometry available for this component` 
      }
    }
  }

  const geometryRoute = mode === 'reduced' ? 'geometry_reduced' : 'geometry_detailed'
  const mtlRoute = mode === 'reduced' ? 'material_reduced' : 'material_detailed'

  const objUrl = `/api/backend/components/${componentId}/${geometryRoute}`
  const mtlUrl = `/api/backend/components/${componentId}/${mtlRoute}`

  try {
    // Load MTL materials (should always exist)
    const mtlLoader: MTLLoaderWithOptional = new MTLLoader() as MTLLoaderWithOptional
    // Let MTLLoader resolve map_Kd/etc via our texture proxy
    const textureBase = `/api/fetch-component-texture?component_id=${encodeURIComponent(componentId)}&texture=`
    mtlLoader.setResourcePath(textureBase)
    mtlLoader.setTexturePath?.(textureBase)
    mtlLoader.setWithCredentials?.(true)

    const materials = await mtlLoader.loadAsync(mtlUrl)
    materials.preload()

    const objLoader: OBJLoaderWithOptional = new OBJLoader() as OBJLoaderWithOptional
    objLoader.setWithCredentials?.(true)
    objLoader.setMaterials(materials)

    const object = await objLoader.loadAsync(objUrl)

    // Check for vertex colors and handle texture/material fallback
    let hasVertexColors = false
    let hasTextures = false

    object.traverse((o) => {
      if (!isMesh(o)) return
      
      // Check for vertex colors in geometry
      if (isWithGeometry(o)) {
        const g = o.geometry
        const colorAttribute = g.getAttribute('color')
        if (colorAttribute) {
          hasVertexColors = true
        }
        
        if (!g.getAttribute('uv')) {
          // no UVs present -> texture cannot display
          console.warn('OBJ mesh has no UVs; texture cannot display', o.name)
        }
      }

      // Check for textures in materials
      const mat = o.material
      const mats = Array.isArray(mat) ? mat : [mat]
      mats.forEach((mm) => {
        if (!isMaterial(mm)) return
        const maybeMap = (mm as unknown as { map?: unknown }).map
        if (isTexture(maybeMap)) {
          hasTextures = true
          maybeMap.colorSpace = THREE.SRGBColorSpace
          maybeMap.needsUpdate = true
        }
      })
    })

    // If no vertex colors were detected but we expect them, try to parse them manually
    // This handles cases where the OBJLoader doesn't automatically parse vertex colors
    if (!hasVertexColors && !hasTextures) {
      console.log(`Attempting to parse vertex colors from ${mode} geometry OBJ file`)
      
      try {
        // Fetch the raw OBJ content to check for vertex colors
        const response = await fetch(objUrl, { credentials: 'include' })
        if (response.ok) {
          const objContent = await response.text()
          
          // Check if the OBJ file contains vertex colors (vc format or v with color data)
          const hasVcFormat = objContent.includes('vc ') || /^v\s+[\d.-]+\s+[\d.-]+\s+[\d.-]+\s+[\d.-]+\s+[\d.-]+\s+[\d.-]+/m.test(objContent)
          
          if (hasVcFormat) {
            console.log(`Found vertex color data in ${mode} geometry OBJ file, parsing manually`)
            
            // Parse vertex colors from OBJ content
            const vertexColors = parseVertexColorsFromOBJ(objContent)
            console.log(`Parsed ${vertexColors.length} vertex colors from ${mode} geometry OBJ file`)
            
            if (vertexColors.length > 0) {
              // Apply vertex colors to the geometry
              object.traverse((o) => {
                if (!isMesh(o)) return
                
                if (isWithGeometry(o)) {
                  const g = o.geometry
                  const positionAttribute = g.getAttribute('position')
                  
                  if (positionAttribute && vertexColors.length >= positionAttribute.count) {
                    // Create color attribute from parsed vertex colors
                    const colorArray = new Float32Array(vertexColors.length * 3)
                    for (let i = 0; i < vertexColors.length; i++) {
                      colorArray[i * 3] = vertexColors[i][0]     // R
                      colorArray[i * 3 + 1] = vertexColors[i][1] // G
                      colorArray[i * 3 + 2] = vertexColors[i][2] // B
                    }
                    
                    g.setAttribute('color', new THREE.Float32BufferAttribute(colorArray, 3))
                    hasVertexColors = true
                    console.log(`Applied ${vertexColors.length} vertex colors to ${mode} geometry`)
                    
                    // Debug: Verify the color attribute was set correctly
                    const colorAttr = g.getAttribute('color')
                    if (colorAttr) {
                      console.log(`Color attribute verified: count=${colorAttr.count}, itemSize=${colorAttr.itemSize}`)
                      // Log first few color values for verification
                      const firstColors = []
                      for (let i = 0; i < Math.min(3, colorAttr.count); i++) {
                        firstColors.push({
                          r: colorAttr.getX(i),
                          g: colorAttr.getY(i),
                          b: colorAttr.getZ(i)
                        })
                      }
                      console.log(`First few color values:`, firstColors)
                    }
                  }
                }
              })
            }
          }
        }
      } catch (parseError) {
        console.warn(`Failed to parse vertex colors from ${mode} geometry:`, parseError)
      }
    }

    // Handle different material scenarios
    if (hasVertexColors && !hasTextures) {
      // MTL file exists but textures are missing - use vertex colors
      console.log(`Using vertex colors for ${mode} geometry (MTL exists but textures missing)`)
      
      object.traverse((o) => {
        if (!isMesh(o)) return
        
        // Create a new material that uses vertex colors
        // Note: vertex colors are already in 0-1 range (normalized) as expected by Three.js
        const vertexColorMat = new THREE.MeshBasicMaterial({
          vertexColors: true,
          side: THREE.DoubleSide
        })
        
        console.log(`Applied vertex color material to mesh: ${o.name || 'unnamed'}`)
        o.material = vertexColorMat
        
        // Debug: Verify material configuration
        console.log(`Material vertexColors: ${vertexColorMat.vertexColors}`)
        console.log(`Material needsUpdate: ${vertexColorMat.needsUpdate}`)
        
        // Force material update
        vertexColorMat.needsUpdate = true
      })
    } else if (hasVertexColors && hasTextures) {
      // If we have both vertex colors and textures, prioritize textures
      console.log(`Both vertex colors and textures available for ${mode} geometry, using textures`)
    } else if (!hasTextures && !hasVertexColors) {
      // MTL file exists but no textures and no vertex colors - use MTL materials as-is
      console.log(`Using MTL materials for ${mode} geometry (no textures or vertex colors)`)
    }

    object.scale.set(scale, scale, scale)
    ensureNormals(object)

    externalGeometryCache.set(cacheKey, object)
    return { success: true, object }
  } catch (e) {
    console.error('Failed to load external geometry:', e)
    
    // Determine error type based on the error
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
  geometryMode
}: {
  component_data: ComponentData
  geometryMode: GeometryMode
}) => {
  const [externalObject, setExternalObject] = useState<THREE.Group | null>(null)
  const [isLoadingExternal, setIsLoadingExternal] = useState(false)
  const [geometryError, setGeometryError] = useState<string | null>(null)

  const isExternalMode = geometryMode === 'reduced' || geometryMode === 'detailed'

  useEffect(() => {
    let isMounted = true
    if (isExternalMode && component_data.type !== 'sheet') {
      if (!component_data._id) return
      setIsLoadingExternal(true)
      setGeometryError(null)
      loadExternalGeometry(component_data._id.toString(), geometryMode)
        .then((result) => {
          if (isMounted) {
            if (result.success) {
              setExternalObject(result.object)
              setGeometryError(null)
            } else {
              setExternalObject(null)
              setGeometryError(result.message)
            }
            setIsLoadingExternal(false)
          }
        })
        .catch((error) => {
          if (isMounted) {
            setExternalObject(null)
            setGeometryError(`Failed to load ${geometryMode} geometry`)
            setIsLoadingExternal(false)
          }
        })
    } else {
      setExternalObject(null)
      setIsLoadingExternal(false)
      setGeometryError(null)
    }
    return () => {
      isMounted = false
    }
  }, [geometryMode, component_data, isExternalMode])

  // Primitive fallback geometry
  const mesh_geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const vertices = component_data.geometry.mesh.v
    const flatVertices = vertices.flat().map((v) => v * scale)
    g.setAttribute('position', new THREE.Float32BufferAttribute(flatVertices, 3))

    const faces = component_data.geometry.mesh.f
    g.setIndex(faces.flat())

    const colors = component_data.geometry.mesh.c
    if (colors && colors.length === vertices.length) {
      const flatColors = colors.flatMap((c) => c.map((v) => v / 255))
      g.setAttribute('color', new THREE.Float32BufferAttribute(flatColors, 3))
    }
    // Adjust orientation
    g.rotateX(-Math.PI / 2)
    g.computeVertexNormals()
    g.normalizeNormals()
    return g
  }, [component_data])

  const colorHex = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
  )

  const mesh_material = useMemo(() => {
    return new THREE.MeshBasicMaterial({
      color: colorHex,
      vertexColors: !!component_data.geometry.mesh.c,
      side: THREE.DoubleSide
    })
  }, [colorHex, component_data.geometry.mesh.c])

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
    if (externalObject) {
      return <primitive object={externalObject} />
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
    // Primitive
    return (
      <>
        <mesh visible geometry={mesh_geometry} material={mesh_material} />
        <lineSegments geometry={edge_geometry} material={edge_material} />
      </>
    )
  }
})
VisualizeMesh.displayName = 'VisualizeMesh'

/** 
 * VisualizeSheet 
 */
const VisualizeSheet = React.memo(({ component_data }: { component_data: ComponentData }) => {
  const pline_shape = useMemo(() => {
    const shape = new THREE.Shape()
    const points: ComponentPolylinePoints = component_data.geometry.extrusion.profile
    shape.moveTo(points[0][0] * scale, points[0][1] * scale)
    points.forEach((p, i) => {
      if (i > 0) shape.lineTo(p[0] * scale, p[1] * scale)
    })
    return shape
  }, [component_data])

  const extrude_geometry = useMemo(() => {
    const extrudeSettings = { steps: 2, depth: component_data.geometry.extrusion.height * scale, bevelEnabled: false }
    const g = new THREE.ExtrudeGeometry(pline_shape, extrudeSettings)
    g.translate(0, 0, -component_data.geometry.extrusion.height * scale * 0.5)
    g.rotateX(-Math.PI / 2)
    g.computeVertexNormals()
    g.normalizeNormals()
    return g
  }, [pline_shape, component_data.geometry.extrusion.height])

  const colorHex = rgbToHex(
    component_data.color[0],
    component_data.color[1],
    component_data.color[2]
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
 * VisualizeComponent 
 */
function VisualizeComponent({
  component_data,
  geometryMode
}: {
  component_data: ComponentData
  geometryMode: GeometryMode
}) {
  if (!component_data.geometry) return null
  
  // Infer visualization type based on geometry content rather than just type field
  const hasExtrusion = component_data.geometry.extrusion && 
                       component_data.geometry.extrusion.profile && 
                       component_data.geometry.extrusion.height
  const hasMesh = component_data.geometry.mesh && 
                  component_data.geometry.mesh.v && 
                  component_data.geometry.mesh.f
  
  if (hasExtrusion) {
    return <VisualizeSheet component_data={component_data} />
  } else if (hasMesh) {
    return <VisualizeMesh component_data={component_data} geometryMode={geometryMode} />
  }
  
  // Fallback to type-based logic if geometry inference fails
  if (component_data.type === 'sheet') {
    return <VisualizeSheet component_data={component_data} />
  } else {
    return <VisualizeMesh component_data={component_data} geometryMode={geometryMode} />
  }
}

/**
 * ComponentViewer
 */
export default function ComponentViewer({ component_data }: { component_data: ComponentData }) {
  // Call ALL hooks FIRST, unconditionally
  const [geometryMode, setGeometryMode] = useState<GeometryMode>('primitive')

  const isSheet = component_data.type === 'sheet'

  const onModeChange: React.ChangeEventHandler<HTMLSelectElement> = (e) => {
    const v = e.target.value as GeometryMode
    setGeometryMode(v)
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
        </div>

        <Canvas camera={{ position: [2, 5, 5], fov: 50 }}>
          <ambientLight intensity={Math.PI / 2} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} decay={0} intensity={Math.PI * 0.75} />
          <pointLight position={[-10, 10, -10]} decay={0} intensity={Math.PI * 0.75} />

          <Bounds fit clip observe margin={1.2} maxDuration={1}>
            <VisualizeComponent component_data={component_data} geometryMode={geometryMode} />
          </Bounds>

          <axesHelper args={[0.1]} />
          <gridHelper args={[2, 20, 'Gray', 'Gainsboro']} />
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </Card>
  )
}
