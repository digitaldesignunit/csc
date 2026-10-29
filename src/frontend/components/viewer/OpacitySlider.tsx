'use client'

import { MenuSubsection } from '@/components/viewer/ViewerMenu'
import {
  OPACITY_MAX,
  OPACITY_MIN,
  OPACITY_STEP,
  clampOpacityPercent,
} from '@/lib/viewerOpacity'

const HELP = 'Fades the element itself: the mesh with its edges, the proxy and the point cloud. '
  + 'Reinforcement bars, test positions, marker points, capture fixtures and the grid keep their look, '
  + 'so what lies inside the element shows through. 100 % is the normal view.'

/**
 * One slider for the opacity of the piece (decision 8.165 C), 0 to 100 % in
 * steps of 5. A native range input: the arrow keys, Home and End work, and the
 * accent colour follows the theme.
 */
export default function OpacitySlider({
  value,
  onChange,
  nothingShown = false,
}: {
  value: number
  onChange: (percent: number) => void
  /** No part of the piece is on screen: the slider has nothing to fade. */
  nothingShown?: boolean
}) {
  return (
    <MenuSubsection title="Element opacity" help={HELP}>
      <div className="flex items-center gap-2">
        <input
          id="viewer-piece-opacity"
          type="range"
          min={OPACITY_MIN}
          max={OPACITY_MAX}
          step={OPACITY_STEP}
          value={value}
          disabled={nothingShown}
          aria-label="Element opacity"
          aria-valuetext={`${value} %`}
          onChange={(event) => onChange(clampOpacityPercent(Number(event.target.value)))}
          className="h-4 min-w-0 flex-1 cursor-pointer rounded accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        />
        <output
          htmlFor="viewer-piece-opacity"
          className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground"
        >
          {value} %
        </output>
      </div>
      {nothingShown && (
        <p className="text-xs text-muted-foreground">No part of the element is shown.</p>
      )}
    </MenuSubsection>
  )
}
