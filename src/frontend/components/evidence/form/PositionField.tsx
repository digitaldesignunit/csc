'use client'

/**
 * Where on the piece (spec 3.3.2): words are always enough; optionally a
 * point picked on the 3D viewer (decision 8.43) or, for a rebound test
 * area, the impact grid. The picked point is in the stored coordinates of
 * the snapshot it was picked on.
 */
import { Crosshair, Trash2 } from 'lucide-react'

import { Field } from '@/components/evidence/controls'
import type { PositionState } from '@/components/evidence/form/state'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { roundVec } from '@/lib/evidence/grid'

export default function PositionField({
  id,
  position,
  onChange,
  onPick,
  gridCentre,
  required,
  errors,
  noPoint,
  help,
}: {
  id: string
  position: PositionState
  onChange: (next: PositionState) => void
  /** opens the picker for a point */
  onPick: () => void
  /** a rebound grid is a region: the point is the server's, shown for orientation */
  gridCentre?: boolean
  required?: boolean
  errors?: string[]
  /** a method with no point to pick (the layout: only words here) */
  noPoint?: boolean
  /** the backend's description of `position.description` */
  help?: string
}) {
  const hasPoint = position.kind === 'point' && position.point
  return (
    <div className="space-y-2">
      <Field
        id={id}
        label="Where on the piece"
        help={help}
        required={required && !hasPoint && !gridCentre}
        errors={errors}
      >
        <Input
          id={id}
          value={position.description}
          placeholder="north face, mid-span"
          onChange={(event) => onChange({ ...position, description: event.target.value })}
        />
      </Field>
      {!noPoint && !gridCentre && (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={onPick}>
            <Crosshair className="mr-1 h-3.5 w-3.5" />
            {hasPoint ? 'Pick again on the model' : 'Pick on the 3D model'}
          </Button>
          {hasPoint && position.point && (
            <>
              <span className="font-mono text-xs text-muted-foreground">
                {roundVec(position.point, 1).join(', ')} mm
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-muted-foreground"
                onClick={() => onChange({ ...position, kind: 'none', point: null, snapshotId: null })}
              >
                <Trash2 className="mr-1 h-3 w-3" />Clear point
              </Button>
            </>
          )}
        </div>
      )}
      {gridCentre && (
        <p className="text-xs text-muted-foreground">
          A test area with a grid is a region on the model; the server sets its centre.
        </p>
      )}
    </div>
  )
}
