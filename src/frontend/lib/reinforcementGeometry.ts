import * as THREE from 'three'
import type { SnapshotGeometry, SnapshotReinforcement } from '@/generated/CatalogModels'

export const REINFORCEMENT_STEEL_COLOR = 0x708090
export const REINFORCEMENT_RADIAL_SEGMENTS = 16

export const reinforcementSteelMaterial = new THREE.MeshStandardMaterial({
  color: REINFORCEMENT_STEEL_COLOR,
  metalness: 0.55,
  roughness: 0.45,
})

type ReinforcementSegment = {
  position: THREE.Vector3
  quaternion: THREE.Quaternion
  height: number
}

export function snapshotReinforcementsFromGeometry(
  geometry: SnapshotGeometry,
): SnapshotReinforcement[] {
  const reinforcements = geometry.reinforcements
  if (!Array.isArray(reinforcements)) return []
  return (reinforcements as SnapshotReinforcement[]).filter((bar) => (
    typeof bar?.spec === 'string'
    && bar.spec.trim().length > 0
    && typeof bar.diameter === 'number'
    && Number.isFinite(bar.diameter)
    && bar.diameter > 0
    && Array.isArray(bar.points)
    && bar.points.length >= 2
    && bar.points.every((pt) => Array.isArray(pt) && pt.length >= 3)
  ))
}

export function buildReinforcementBarMeshes(
  points: number[][],
): { segments: ReinforcementSegment[]; cornerJoints: THREE.Vector3[] } {
  const vertices = points.map(
    ([x, y, z]) => new THREE.Vector3(x, y, z),
  )
  const up = new THREE.Vector3(0, 1, 0)
  const segments: ReinforcementSegment[] = []

  for (let i = 0; i < vertices.length - 1; i += 1) {
    const start = vertices[i]
    const end = vertices[i + 1]
    const direction = new THREE.Vector3().subVectors(end, start)
    const height = direction.length()
    if (height <= 1e-6) continue

    direction.normalize()
    segments.push({
      position: start.clone().add(end).multiplyScalar(0.5),
      quaternion: new THREE.Quaternion().setFromUnitVectors(up, direction),
      height,
    })
  }

  const cornerJoints = vertices.length > 2 ? vertices.slice(1, -1) : []

  return { segments, cornerJoints }
}

export function buildReinforcementBarThreeGroup(
  bar: SnapshotReinforcement,
  name: string,
): THREE.Group | null {
  const { segments, cornerJoints } = buildReinforcementBarMeshes(bar.points)
  const radius = bar.diameter / 2
  if (segments.length === 0) return null

  const group = new THREE.Group()
  group.name = name

  segments.forEach((segment, index) => {
    const geometry = new THREE.CylinderGeometry(
      radius,
      radius,
      segment.height,
      REINFORCEMENT_RADIAL_SEGMENTS,
    )
    const mesh = new THREE.Mesh(geometry, reinforcementSteelMaterial)
    mesh.position.copy(segment.position)
    mesh.quaternion.copy(segment.quaternion)
    mesh.name = `${name}_segment_${index}`
    group.add(mesh)
  })

  cornerJoints.forEach((joint, index) => {
    const geometry = new THREE.SphereGeometry(
      radius,
      REINFORCEMENT_RADIAL_SEGMENTS,
      12,
    )
    const mesh = new THREE.Mesh(geometry, reinforcementSteelMaterial)
    mesh.position.copy(joint)
    mesh.name = `${name}_joint_${index}`
    group.add(mesh)
  })

  return group
}
