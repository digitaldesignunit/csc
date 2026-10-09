'use client'

/**
 * Positions of evidence drawn on the viewer (spec 3.3.2, decision 8.43):
 * picked points, the impact grid of a rebound test area, a layout of test
 * locations. Everything is in the stored coordinates of one snapshot and is
 * drawn only on that snapshot. Marks are never picked.
 */
import { useMemo } from 'react'
import * as THREE from 'three'
import { Html } from '@react-three/drei'

import { storedToLocal } from '@/lib/evidence/pick'
import type { Vec3 } from '@/lib/evidence/grid'

export type ViewerMark = {
  id: string
  snapshotId: string
  kind: 'point' | 'grid' | 'layout'
  points: Vec3[]
  color: string
  /** short text beside the first point */
  label?: string
  /** grid rows and columns, to draw the lines between the points */
  grid?: { rows: number; cols: number }
  /** indices drawn in the warning colour (closer to an edge than allowed) */
  warn?: number[]
  /** number the points 1... (kept to small sets) */
  numbered?: boolean
}

const WARN_COLOR = '#dc2626'
const FIRST_COLOR = '#16a34a'
const MAX_LABELS = 36

function pointsGeometry(points: Vec3[]): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(points.flatMap((p) => storedToLocal(p)), 3),
  )
  return geometry
}

function gridLines(points: Vec3[], rows: number, cols: number): THREE.BufferGeometry | null {
  if (rows * cols !== points.length || rows * cols < 2) return null
  const at = (r: number, c: number) => storedToLocal(points[r * cols + c])
  const positions: number[] = []
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      if (c + 1 < cols) positions.push(...at(r, c), ...at(r, c + 1))
      if (r + 1 < rows) positions.push(...at(r, c), ...at(r + 1, c))
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  return geometry
}

function Mark({ mark }: { mark: ViewerMark }) {
  const warn = useMemo(() => new Set(mark.warn ?? []), [mark.warn])
  const normal = useMemo(
    () => pointsGeometry(mark.points.filter((_, i) => !warn.has(i) && i !== 0)),
    [mark.points, warn],
  )
  const flagged = useMemo(
    () => pointsGeometry(mark.points.filter((_, i) => warn.has(i))),
    [mark.points, warn],
  )
  const first = useMemo(() => pointsGeometry(mark.points.slice(0, 1)), [mark.points])
  const lines = useMemo(
    () => (mark.grid ? gridLines(mark.points, mark.grid.rows, mark.grid.cols) : null),
    [mark.points, mark.grid],
  )
  const labelled = mark.numbered && mark.points.length <= MAX_LABELS

  return (
    <group userData={{ noPick: true }} renderOrder={20}>
      {lines && (
        <lineSegments geometry={lines}>
          <lineBasicMaterial color={mark.color} depthTest={false} transparent opacity={0.7} />
        </lineSegments>
      )}
      <points geometry={normal}>
        <pointsMaterial size={9} sizeAttenuation={false} color={mark.color} depthTest={false} />
      </points>
      <points geometry={flagged}>
        <pointsMaterial size={11} sizeAttenuation={false} color={WARN_COLOR} depthTest={false} />
      </points>
      {mark.points.length > 0 && !warn.has(0) && (
        <points geometry={first}>
          <pointsMaterial size={11} sizeAttenuation={false} color={FIRST_COLOR} depthTest={false} />
        </points>
      )}
      {mark.points.length > 0 && warn.has(0) && (
        <points geometry={first}>
          <pointsMaterial size={11} sizeAttenuation={false} color={WARN_COLOR} depthTest={false} />
        </points>
      )}
      {labelled
        && mark.points.map((point, index) => (
          <Html
            key={index}
            position={storedToLocal(point)}
            center
            style={{ pointerEvents: 'none' }}
            zIndexRange={[10, 0]}
          >
            <span className="translate-y-3 rounded bg-background/80 px-1 text-[10px] font-medium leading-none text-foreground shadow-sm">
              {index + 1}
            </span>
          </Html>
        ))}
      {!labelled && mark.label && mark.points.length > 0 && (
        <Html position={storedToLocal(mark.points[0])} center style={{ pointerEvents: 'none' }} zIndexRange={[10, 0]}>
          <span className="translate-y-3 whitespace-nowrap rounded bg-background/80 px-1 text-[10px] font-medium leading-none text-foreground shadow-sm">
            {mark.label}
          </span>
        </Html>
      )}
    </group>
  )
}

/** The marks of the snapshot on screen. */
export default function EvidenceMarks({
  marks,
  snapshotId,
}: {
  marks: ViewerMark[]
  snapshotId: string
}) {
  const here = marks.filter((mark) => mark.snapshotId === snapshotId && mark.points.length > 0)
  if (here.length === 0) return null
  return (
    <group userData={{ noPick: true }}>
      {here.map((mark) => (
        <Mark key={mark.id} mark={mark} />
      ))}
    </group>
  )
}
