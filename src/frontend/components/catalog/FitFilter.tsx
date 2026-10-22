'use client'

/**
 * The "Fits" section of the "More filters" panel of Browse (decision 8.169):
 * three boxes for the size you look for (mm, any order), the switch between
 * "About this size" and "Can hold this size", and the tolerance of the first
 * (mm or %, 10 % by default). It writes `fit_mode`, `fit_size` and `fit_tol`
 * to the URL when the three sizes are complete, and removes them when all
 * three boxes are empty.
 */
import { useEffect, useRef, useState } from 'react'

import Help from '@/components/ui/help'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { ParamsLike } from '@/lib/browse'
import {
  DEFAULT_TOLERANCE,
  FIT_HELP,
  FIT_MODES,
  FIT_MODE_LABELS,
  fitChanges,
  parseFit,
  parseFitSize,
  parseFitTolerance,
  type FitMode,
} from '@/lib/fit'

const SELECT_CLASS =
  'h-8 min-w-0 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

type Go = (changes: Record<string, string | null>) => void

/** The boxes' texts for a fit in the URL; empty boxes without one. */
function fromUrl(search: ParamsLike) {
  const fit = parseFit(search)
  const tolerance = /^(\d+(?:\.\d+)?)(%|mm)$/.exec(fit?.tolerance ?? DEFAULT_TOLERANCE)
  return {
    sizes: fit ? fit.size.map(String) : ['', '', ''],
    mode: (fit?.mode ?? 'about') as FitMode,
    tolValue: tolerance?.[1] ?? '10',
    tolUnit: tolerance?.[2] ?? '%',
  }
}

export default function FitFilter({ search, go }: { search: ParamsLike; go: Go }) {
  const urlKey = ['fit_mode', 'fit_size', 'fit_tol'].map((k) => search.get(k) ?? '').join('|')
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
      if (next.sizes.every((s) => s.trim() === '')) {
        if (search.get('fit_mode')) go(fitChanges(null, true))
        return
      }
      const size = parseFitSize(next.sizes.map((s) => s.trim()).join(','))
      if (!size) return                       // incomplete: wait for the rest
      const tolerance = parseFitTolerance(`${next.tolValue.trim() || '10'}${next.tolUnit}`)
      if (next.mode === 'about' && !tolerance) return
      go(fitChanges({ mode: next.mode, size, tolerance: next.mode === 'about' ? tolerance : null },
        parseFit(search) !== null))
    }
    if (immediately) run()
    else timer.current = window.setTimeout(run, 500)
  }

  const sizeProblem = state.sizes.every((s) => s.trim() !== '')
    && !parseFitSize(state.sizes.map((s) => s.trim()).join(','))

  return (
    <div className="space-y-1.5 border-t pt-3">
      <div className="flex items-center gap-1">
        <p className="text-xs font-medium">Fits: size you look for in mm</p>
        <Help label="Fits" text={FIT_HELP} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        {state.sizes.map((value, index) => (
          <Input
            key={index}
            type="number"
            inputMode="decimal"
            min={0}
            aria-label={`Fits: side ${index + 1} in mm`}
            placeholder={['longest', 'middle', 'shortest'][index]}
            className="h-8"
            value={value}
            onChange={(e) => {
              const sizes = [...state.sizes]
              sizes[index] = e.target.value
              apply({ ...state, sizes }, false)
            }}
          />
        ))}
      </div>
      {sizeProblem && (
        <p className="text-xs text-destructive">Three sizes above 0 and up to 100000 mm.</p>
      )}
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        value={state.mode}
        onValueChange={(value) => {
          if (value) apply({ ...state, mode: value as FitMode }, true)
        }}
        aria-label="Fits: mode"
        className="w-full"
      >
        {FIT_MODES.map((mode) => (
          <ToggleGroupItem key={mode} value={mode} className="flex-1 px-2 text-xs">
            {FIT_MODE_LABELS[mode]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {state.mode === 'about' && (
        <div className="flex items-center gap-2">
          <Label htmlFor="fit-tol" className="text-xs">Tolerance</Label>
          <Input
            id="fit-tol"
            type="number"
            inputMode="decimal"
            min={0}
            className="h-8 w-20"
            value={state.tolValue}
            onChange={(e) => apply({ ...state, tolValue: e.target.value }, false)}
          />
          <select
            aria-label="Fits: tolerance unit"
            className={SELECT_CLASS}
            value={state.tolUnit}
            onChange={(e) => apply({ ...state, tolUnit: e.target.value }, true)}
          >
            <option value="%">%</option>
            <option value="mm">mm</option>
          </select>
        </div>
      )}
    </div>
  )
}
