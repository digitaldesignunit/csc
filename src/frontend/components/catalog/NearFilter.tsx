'use client'

/**
 * The "Near" section of the "More filters" panel of Browse (decision 8.170):
 * one field for the point (a pasted "lat, lon"), the layer (the current place
 * of a piece or its origin) and a radius in km (empty = the nearest first).
 * It writes `near_lat`, `near_lon`, `near_layer` and `radius_km` to the URL
 * once the point is a whole pair on the globe, and removes them when the point
 * field is emptied.
 */
import { useEffect, useRef, useState } from 'react'

import Help from '@/components/ui/help'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { ParamsLike } from '@/lib/browse'
import {
  NEAR_HELP,
  NEAR_LAYERS,
  NEAR_LAYER_LABELS,
  latLonText,
  nearChanges,
  parseLatLon,
  parseNear,
  parseRadius,
  type NearLayer,
} from '@/lib/near'

type Go = (changes: Record<string, string | null>) => void

/** The boxes' texts for a search in the URL; empty boxes without one. */
function fromUrl(search: ParamsLike) {
  const near = parseNear(search)
  return {
    point: near ? latLonText(near.lat, near.lon) : '',
    layer: (near?.layer ?? 'current') as NearLayer,
    radius: near?.radiusKm != null ? String(near.radiusKm) : '',
  }
}

export default function NearFilter({ search, go }: { search: ParamsLike; go: Go }) {
  const urlKey = ['near_lat', 'near_lon', 'near_layer', 'radius_km'].map((k) => search.get(k) ?? '').join('|')
  const [state, setState] = useState(() => fromUrl(search))
  const timer = useRef<number | null>(null)

  // the URL changed from elsewhere (a chip removed, "Clear all", a link)
  useEffect(() => setState(fromUrl(search)), [urlKey]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])

  const apply = (next: typeof state, immediately: boolean) => {
    setState(next)
    if (timer.current) window.clearTimeout(timer.current)
    const run = () => {
      if (next.point.trim() === '') {
        if (parseNear(search)) go(nearChanges(null, true))
        return
      }
      const point = parseLatLon(next.point)
      if (!point) return                       // not a point yet: wait for the rest
      const radiusKm = next.radius.trim() === '' ? null : parseRadius(next.radius)
      if (next.radius.trim() !== '' && radiusKm === null) return
      go(nearChanges({ ...point, layer: next.layer, radiusKm }, parseNear(search) !== null))
    }
    if (immediately) run()
    else timer.current = window.setTimeout(run, 500)
  }

  const pointProblem = state.point.trim() !== '' && !parseLatLon(state.point)
  const radiusProblem = state.radius.trim() !== '' && parseRadius(state.radius) === null

  return (
    <div className="space-y-1.5 border-t pt-3">
      <div className="flex items-center gap-1">
        <p className="text-xs font-medium">Near: a point on the map</p>
        <Help label="Near" text={NEAR_HELP} />
      </div>
      <Input
        type="text"
        inputMode="text"
        autoComplete="off"
        aria-label="Near: latitude, longitude"
        aria-invalid={pointProblem || undefined}
        placeholder="49.8728, 8.6512"
        className="h-8"
        value={state.point}
        onChange={(e) => apply({ ...state, point: e.target.value }, false)}
      />
      {pointProblem && (
        <p className="text-xs text-destructive">
          Two numbers, latitude (-90 to 90) and longitude (-180 to 180), for example 49.8728, 8.6512.
        </p>
      )}
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        value={state.layer}
        onValueChange={(value) => {
          if (value) apply({ ...state, layer: value as NearLayer }, true)
        }}
        aria-label="Near: which place"
        className="w-full"
      >
        {NEAR_LAYERS.map((layer) => (
          <ToggleGroupItem key={layer} value={layer} className="flex-1 px-2 text-xs">
            {NEAR_LAYER_LABELS[layer]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <div className="flex items-center gap-2">
        <Label htmlFor="near-radius" className="text-xs">Radius</Label>
        <Input
          id="near-radius"
          type="number"
          inputMode="decimal"
          min={0}
          placeholder="nearest"
          aria-invalid={radiusProblem || undefined}
          className="h-8 w-24"
          value={state.radius}
          onChange={(e) => apply({ ...state, radius: e.target.value }, false)}
        />
        <span className="text-xs text-muted-foreground">km</span>
      </div>
      {radiusProblem && <p className="text-xs text-destructive">A distance above 0 km, or empty.</p>}
    </div>
  )
}
