/**
 * Viewer marks from evidence records: the positions of the published
 * records that were picked on a snapshot (spec 3.3.2) and the impact grids
 * of rebound test areas (A.1: the server derives the points).
 */
import type { ViewerMark } from '@/components/viewer/EvidenceMarks'
import type { Vec3 } from '@/lib/evidence/grid'

const METHOD_COLOR: Record<string, string> = {
  rebound_hammer: '#2563eb',
  core_compression: '#9333ea',
}
const DEFAULT_COLOR = '#ea580c'

function isVec3(value: unknown): value is Vec3 {
  return Array.isArray(value) && value.length === 3 && value.every((v) => typeof v === 'number')
}

type RecordLike = {
  _id?: string
  method?: string
  position?: { kind?: string; snapshot_id?: string | null; point?: unknown; description?: string | null } | null
  payload?: { test_area?: { label?: string | null; grid?: { rows?: number; cols?: number; points?: unknown } | null } }
}

export function marksOfRecord(record: RecordLike, snapshotId: string): ViewerMark | null {
  const position = record.position
  if (!position || position.snapshot_id !== snapshotId) return null
  const id = record._id ?? `${record.method}-${Math.random()}`
  const color = METHOD_COLOR[record.method ?? ''] ?? DEFAULT_COLOR
  const area = record.payload?.test_area
  const grid = area?.grid
  if (grid && Array.isArray(grid.points) && grid.points.every(isVec3) && grid.points.length) {
    return {
      id,
      snapshotId,
      kind: 'grid',
      points: grid.points as Vec3[],
      color,
      label: area?.label ?? undefined,
      grid: { rows: grid.rows ?? 1, cols: grid.cols ?? grid.points.length },
    }
  }
  if (record.method === 'reinforcement_layout') return null // drawn as bars
  if (isVec3(position.point)) {
    return { id, snapshotId, kind: 'point', points: [position.point], color, label: area?.label ?? undefined }
  }
  return null
}

/** Marks of a list of records for the snapshot on screen. */
export function publishedMarks(records: unknown, snapshotId: string): ViewerMark[] {
  if (!Array.isArray(records)) return []
  return records
    .map((record) => marksOfRecord(record as RecordLike, snapshotId))
    .filter((mark): mark is ViewerMark => mark !== null)
}
