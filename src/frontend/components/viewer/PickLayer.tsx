'use client'

/**
 * Click or tap picking inside the viewer canvas (decision 8.43). A press
 * that moves less than a few pixels is a pick; a drag stays an orbit. The
 * hit is reported in the stored coordinates of the snapshot on screen.
 */
import { useEffect, useRef } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

import { pickGeometry, type PickHit } from '@/lib/evidence/pick'

const MOUSE_TOLERANCE_PX = 8
const TOUCH_TOLERANCE_PX = 20
const MAX_MOVE_PX = 6
const MAX_PRESS_MS = 700

export default function PickLayer({
  rootRef,
  enabled,
  onPick,
}: {
  rootRef: React.RefObject<THREE.Object3D | null>
  enabled: boolean
  onPick: (hit: PickHit | null) => void
}) {
  const { gl, camera } = useThree()
  const pickRef = useRef(onPick)
  useEffect(() => {
    pickRef.current = onPick
  }, [onPick])

  useEffect(() => {
    const element = gl.domElement
    element.style.setProperty('cursor', enabled ? 'crosshair' : '')
    if (!enabled) return undefined
    let press: { x: number; y: number; at: number; id: number } | null = null

    const down = (event: PointerEvent) => {
      press = { x: event.clientX, y: event.clientY, at: performance.now(), id: event.pointerId }
    }
    const up = (event: PointerEvent) => {
      const start = press
      press = null
      if (!start || start.id !== event.pointerId) return
      if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > MAX_MOVE_PX) return
      if (performance.now() - start.at > MAX_PRESS_MS) return
      const root = rootRef.current
      if (!root) return
      const rect = element.getBoundingClientRect()
      const ndc = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1,
      )
      root.updateWorldMatrix(true, true)
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(ndc, camera)
      // screen tolerance for cloud points, in world units at the model's depth
      const centre = new THREE.Box3().setFromObject(root).getCenter(new THREE.Vector3())
      const depth = Math.max(camera.position.distanceTo(centre), 1e-6)
      const fov = (camera as THREE.PerspectiveCamera).isPerspectiveCamera
        ? THREE.MathUtils.degToRad((camera as THREE.PerspectiveCamera).fov)
        : 0.8
      const perPixel = (2 * depth * Math.tan(fov / 2)) / Math.max(rect.height, 1)
      const tolerance = (event.pointerType === 'touch' ? TOUCH_TOLERANCE_PX : MOUSE_TOLERANCE_PX) * perPixel
      pickRef.current(pickGeometry(raycaster, root, tolerance))
    }
    element.addEventListener('pointerdown', down)
    element.addEventListener('pointerup', up)
    return () => {
      element.removeEventListener('pointerdown', down)
      element.removeEventListener('pointerup', up)
      element.style.removeProperty('cursor')
    }
  }, [gl, camera, rootRef, enabled])

  return null
}
