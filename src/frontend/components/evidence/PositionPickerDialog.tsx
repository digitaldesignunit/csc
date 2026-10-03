'use client'

/**
 * Pick a position on the 3D viewer (decision 8.43): a point on a mesh, a
 * point cloud or an authored prism; or lay a grid on a picked face (origin,
 * two in-plane directions, rows x columns, spacing). Everything is in the
 * stored coordinates of the snapshot on screen, never in the canonical
 * frame. The viewer draws the pick and the grid and flags points closer to
 * an edge than `min_edge_distance_mm`.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Crosshair, Grid3x3, RotateCw } from 'lucide-react'

import ComponentViewer from '@/components/components/ComponentViewer'
import { Field } from '@/components/evidence/controls'
import type { ViewerMark } from '@/components/viewer/EvidenceMarks'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import {
  AXES,
  cross,
  defaultDirections,
  dot,
  edgeWarnings,
  gridCentre,
  gridPoints,
  inPlane,
  originForCentre,
  roundVec,
  scale,
  spacingProblem,
  unit,
  type GridSpec,
  type Vec3,
} from '@/lib/evidence/grid'
import { parseNumber } from '@/lib/evidence/schema'
import type { PickHit } from '@/lib/evidence/pick'

export type PickerMode = 'point' | 'grid'

export type PickerResult =
  | { kind: 'point'; snapshotId: string; point: Vec3 }
  | { kind: 'grid'; snapshotId: string; grid: GridSpec; centre: Vec3; tooClose: number[] }

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  catalog: CatalogComponent
  mode: PickerMode
  /** the grid of a test area being edited, if any */
  initialGrid?: GridSpec | null
  /** A.1 min_spacing_mm / min_edge_distance_mm of the record */
  minSpacingMm?: number
  minEdgeMm?: number
  /** rows, cols and spacing already in the form */
  defaults?: { rows?: number; cols?: number; spacing?: number }
  /** positions of other records, drawn for context */
  context?: ViewerMark[]
  onConfirm: (result: PickerResult) => void
}

export default function PositionPickerDialog(props: Props) {
  const { open, onOpenChange } = props
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92dvh] max-h-[92dvh] w-[calc(100vw-1rem)] max-w-5xl sm:max-w-5xl flex-col gap-3 p-3 sm:p-4">
        {open ? <PickerBody {...props} /> : null}
      </DialogContent>
    </Dialog>
  )
}

function PickerBody({
  onOpenChange,
  catalog,
  mode,
  initialGrid,
  minSpacingMm = 25,
  minEdgeMm,
  defaults,
  context = [],
  onConfirm,
}: Props) {
  const snapshot = primarySnapshot(catalog)
  const snapshotId = String(snapshot._id ?? '')
  const version = typeof snapshot.version === 'number' ? snapshot.version : null

  const [hit, setHit] = useState<PickHit | null>(null)
  const [miss, setMiss] = useState(false)
  const [rows, setRows] = useState(String(initialGrid?.rows ?? defaults?.rows ?? 3))
  const [cols, setCols] = useState(String(initialGrid?.cols ?? defaults?.cols ?? 3))
  const [spacing, setSpacing] = useState(String(initialGrid?.spacing_mm ?? defaults?.spacing ?? 30))
  const [centred, setCentred] = useState(true)
  // directions of the grid; from the face normal until the user turns them
  const [dirs, setDirs] = useState<{ u: Vec3; v: Vec3 } | null>(
    initialGrid ? { u: initialGrid.u, v: initialGrid.v } : null,
  )
  const [origin, setOrigin] = useState<Vec3 | null>(initialGrid?.origin ?? null)

  const onPick = useCallback((next: PickHit | null) => {
    if (!next) {
      setMiss(true)
      return
    }
    setMiss(false)
    setHit(next)
    if (mode === 'grid') {
      setOrigin(next.point)
      setDirs(next.normal ? defaultDirections(next.normal) : null)
    }
  }, [mode])

  const rowsN = Math.round(parseNumber(rows) ?? 0)
  const colsN = Math.round(parseNumber(cols) ?? 0)
  const spacingN = parseNumber(spacing) ?? 0
  const sizeOk = rowsN >= 1 && colsN >= 1 && rowsN <= 100 && colsN <= 100 && spacingN > 0

  // the grid as the form will store it
  const grid = useMemo<GridSpec | null>(() => {
    if (mode !== 'grid' || !origin || !dirs || !sizeOk) return null
    const base = { u: dirs.u, v: dirs.v, rows: rowsN, cols: colsN, spacing_mm: spacingN }
    return {
      ...base,
      origin: centred && hit ? originForCentre(base, hit.point) : origin,
    }
  }, [mode, origin, dirs, sizeOk, rowsN, colsN, spacingN, centred, hit])

  const points = useMemo(() => (grid ? gridPoints(grid) : []), [grid])
  const edge = useMemo(() => {
    if (mode === 'grid') return edgeWarnings(points, hit?.edges ?? null, minEdgeMm ?? 0)
    if (hit && minEdgeMm) return edgeWarnings([hit.point], hit.edges, minEdgeMm)
    return { distances: [], tooClose: [] as number[] }
  }, [mode, points, hit, minEdgeMm])

  const marks = useMemo<ViewerMark[]>(() => {
    const out: ViewerMark[] = [...context]
    if (mode === 'grid' && grid && points.length) {
      out.push({
        id: 'picker-grid', snapshotId, kind: 'grid', points, color: '#0891b2',
        grid: { rows: grid.rows, cols: grid.cols }, warn: edge.tooClose, numbered: true,
      })
    } else if (mode === 'point' && hit) {
      out.push({
        id: 'picker-point', snapshotId, kind: 'point', points: [hit.point], color: '#ea580c',
        warn: edge.tooClose,
      })
    } else if (hit) {
      out.push({ id: 'picker-pick', snapshotId, kind: 'point', points: [hit.point], color: '#ea580c' })
    }
    return out
  }, [context, mode, grid, points, hit, snapshotId, edge.tooClose])

  const turn = () => {
    if (!dirs || !hit?.normal) return
    const n = hit.normal
    const u = unit(cross(n, dirs.u))
    const v = u && unit(cross(n, u))
    if (u && v) setDirs({ u, v })
  }
  const flip = (which: 'u' | 'v') => {
    if (dirs) setDirs({ ...dirs, [which]: scale(dirs[which], -1) })
  }
  const alongAxis = (id: string) => {
    if (!hit?.normal) return
    const axis = AXES.find((a) => a.id === id)
    const u = axis && inPlane(axis.vec, hit.normal)
    const v = u && unit(cross(hit.normal, u))
    if (u && v) setDirs({ u, v })
  }

  const spacingMessage = mode === 'grid' && sizeOk ? spacingProblem(spacingN, minSpacingMm) : null
  const canConfirm = mode === 'point'
    ? hit !== null
    : grid !== null && spacingMessage === null && points.length > 0

  // keep the numbers in the form stable while typing: nothing to sync here
  useEffect(() => {
    if (initialGrid && !hit) setOrigin(initialGrid.origin)
  }, [initialGrid, hit])

  const confirm = () => {
    if (mode === 'point' && hit) {
      onConfirm({ kind: 'point', snapshotId, point: roundVec(hit.point, 2) })
    } else if (mode === 'grid' && grid) {
      const safe: GridSpec = {
        ...grid,
        origin: roundVec(grid.origin, 3),
        u: roundVec(unit(grid.u) ?? grid.u, 6),
        v: roundVec(unit(grid.v) ?? grid.v, 6),
      }
      onConfirm({
        kind: 'grid', snapshotId, grid: safe, centre: roundVec(gridCentre(safe), 3),
        tooClose: edge.tooClose,
      })
    }
    onOpenChange(false)
  }

  const patchNote = hit?.patch === 'face'
    ? 'Edge distance is measured to the boundary of the flat face you picked on.'
    : hit?.patch === 'estimated-plane'
      ? 'A point cloud has no faces: the plane is estimated from the points around the pick, and edge distance cannot be checked.'
      : hit?.kind === 'mesh'
        ? 'The surface here is not a flat face (a scan, or too few triangles): edge distance is not checked.'
        : null

  return (
    <>
      <DialogHeader className="space-y-1">
        <DialogTitle className="flex items-center gap-2 text-base">
          {mode === 'grid' ? <Grid3x3 className="h-4 w-4" /> : <Crosshair className="h-4 w-4" />}
          {mode === 'grid' ? 'Lay a grid on a face' : 'Pick a point on the model'}
        </DialogTitle>
        <DialogDescription className="text-xs">
          {mode === 'grid'
            ? 'Tap or click a face: that point becomes the centre of the grid. Turn the grid with the buttons, then set rows, columns and spacing.'
            : 'Tap or click the model. A drag still turns the view.'}
          {' '}Stored coordinates of {version !== null ? `version ${version}` : 'this version'} (mm).
        </DialogDescription>
      </DialogHeader>

      <div className="min-h-0 flex-1">
        <ComponentViewer
          catalog={catalog}
          fill
          picking={{ enabled: true, onPick }}
          marks={marks}
        />
      </div>

      <div className="max-h-[34dvh] space-y-2 overflow-y-auto text-sm">
        {miss && (
          <p className="text-xs text-amber-700 dark:text-amber-300" role="status">
            Nothing there: tap the model itself (for a point cloud, near a point).
          </p>
        )}
        {hit ? (
          <p className="font-mono text-xs text-muted-foreground">
            {hit.kind === 'cloud' ? 'Point cloud' : 'Surface'}: {roundVec(hit.point, 1).join(', ')} mm
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">No pick yet.</p>
        )}

        {mode === 'grid' && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <Field id="grid-rows" label="Rows" help="Number of rows of impact points.">
                <Input id="grid-rows" inputMode="numeric" value={rows} onChange={(e) => setRows(e.target.value)} />
              </Field>
              <Field id="grid-cols" label="Columns" help="Impacts per row. Rows x columns must equal the number of readings.">
                <Input id="grid-cols" inputMode="numeric" value={cols} onChange={(e) => setCols(e.target.value)} />
              </Field>
              <Field id="grid-spacing" label="Spacing (mm)" help={`Distance between neighbouring points; at least ${minSpacingMm} mm.`}>
                <Input id="grid-spacing" inputMode="decimal" value={spacing} onChange={(e) => setSpacing(e.target.value)} />
              </Field>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={turn} disabled={!dirs || !hit?.normal}>
                <RotateCw className="mr-1 h-3.5 w-3.5" />Turn 90 deg
              </Button>
              <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => flip('u')} disabled={!dirs}>
                Flip rows
              </Button>
              <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => flip('v')} disabled={!dirs}>
                Flip columns
              </Button>
              <div className="flex items-center gap-1">
                <Label htmlFor="grid-axis" className="text-xs">Rows run along</Label>
                <select
                  id="grid-axis"
                  className="h-8 rounded-md border border-input bg-transparent px-1 text-xs"
                  value={dirs ? (AXES.find((a) => Math.abs(dot(a.vec, dirs.u)) > 0.999)?.id ?? '') : ''}
                  onChange={(event) => alongAxis(event.target.value)}
                  disabled={!hit?.normal}
                >
                  <option value="">any</option>
                  {AXES.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                </select>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="grid-centred" checked={centred} onCheckedChange={(c) => setCentred(c === true)} />
              <Label htmlFor="grid-centred" className="text-xs font-normal">The pick is the centre of the grid (else its first point)</Label>
            </div>
            {spacingMessage && <p className="text-xs text-destructive" role="alert">{spacingMessage}</p>}
            {!sizeOk && <p className="text-xs text-destructive" role="alert">Rows and columns: 1 to 100; spacing above 0.</p>}
            {hit && !hit.normal && (
              <p className="text-xs text-destructive" role="alert">No face direction here: pick another spot.</p>
            )}
          </div>
        )}

        {minEdgeMm ? (
          edge.tooClose.length > 0 ? (
            <p className="rounded-md border border-red-300 bg-red-50 px-2 py-1.5 text-xs text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100" role="status">
              {mode === 'grid'
                ? `${edge.tooClose.length} of ${points.length} points are closer than ${minEdgeMm} mm to an edge (shown red). Move or shrink the grid, or record the deviation.`
                : `This point is closer than ${minEdgeMm} mm to an edge.`}
            </p>
          ) : hit && patchNote ? (
            <p className="text-xs text-muted-foreground">{patchNote}</p>
          ) : null
        ) : null}
        {minEdgeMm && hit && edge.tooClose.length > 0 && patchNote ? (
          <p className="text-xs text-muted-foreground">{patchNote}</p>
        ) : null}
      </div>

      <DialogFooter className="flex-row justify-end gap-2">
        <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button onClick={confirm} disabled={!canConfirm}>
          {mode === 'grid' ? 'Use this grid' : 'Use this point'}
        </Button>
      </DialogFooter>
    </>
  )
}
