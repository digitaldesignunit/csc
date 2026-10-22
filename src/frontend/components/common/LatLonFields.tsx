'use client'

/**
 * The pair of latitude and longitude boxes shared by every location form (the
 * version's location, the origin place; decision 8.170). The boxes hold the
 * text as typed; the rules are in `lib/near.ts` (`latLonEdit`, `pairFromText`):
 * a pair pasted or typed into either box fills both, a comma typed after the
 * latitude moves on to the longitude, a single number is a normal paste.
 * `inputMode` is text: the numeric pads of iOS and some Android keyboards have
 * no minus sign (western and southern coordinates) and, in an English locale,
 * no comma.
 */
import { useRef } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { latLonEdit, pairFromText, type LatLonBoxes } from '@/lib/near'

export const LAT_LON_HINT =
  'Latitude, longitude as a map shows them, for example 49.8728, 8.6512. Paste both into either box, '
  + 'or type a comma after the latitude. Use a point for decimals: a comma separates the two.'

export default function LatLonFields({ idPrefix, lat, lon, onChange, disabled, problem, hint = LAT_LON_HINT }: {
  idPrefix: string
  lat: string
  lon: string
  onChange: (boxes: LatLonBoxes) => void
  disabled?: boolean
  /** Said under the pair in red while the two boxes are no location. */
  problem?: string | null
  /** The hint under the pair; the shared one by default. */
  hint?: string
}) {
  const lonBox = useRef<HTMLInputElement>(null)

  const edit = (box: 'lat' | 'lon', value: string) => {
    const next = latLonEdit(box, { lat, lon }, value)
    onChange(next.boxes)
    // the comma is not inserted: on to the longitude, whose old text is selected
    // so that what is typed next replaces it (at once, not after the render:
    // a fast typist's next key must find the focus moved)
    if (next.focus === 'lon') {
      lonBox.current?.focus()
      lonBox.current?.select()
    }
  }
  // a pair typed with spaces only ("49.8728 8.6512") fills both boxes once the box is left
  const leave = (value: string) => {
    const pair = pairFromText(value)
    if (pair) onChange(pair)
  }
  // a pair pasted into a box replaces both boxes instead of landing in one
  const paste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    const pair = pairFromText(event.clipboardData.getData('text'))
    if (!pair) return
    event.preventDefault()
    onChange(pair)
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-lat`}>Latitude</Label>
          <Input
            id={`${idPrefix}-lat`}
            inputMode="text"
            autoComplete="off"
            value={lat}
            disabled={disabled}
            aria-invalid={problem ? true : undefined}
            placeholder="49.8728"
            onChange={(event) => edit('lat', event.target.value)}
            onBlur={(event) => leave(event.target.value)}
            onPaste={paste}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-lon`}>Longitude</Label>
          <Input
            id={`${idPrefix}-lon`}
            ref={lonBox}
            inputMode="text"
            autoComplete="off"
            value={lon}
            disabled={disabled}
            aria-invalid={problem ? true : undefined}
            placeholder="8.6512"
            onChange={(event) => edit('lon', event.target.value)}
            onBlur={(event) => leave(event.target.value)}
            onPaste={paste}
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
      {problem && <p className="text-xs text-destructive" role="alert">{problem}</p>}
    </div>
  )
}
