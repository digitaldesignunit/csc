'use client'

/**
 * The coordinates of the origin place (decision 8.170): latitude and
 * longitude next to the address, and one field that takes a pasted "lat, lon"
 * and fills both. Both empty means no location. While the two boxes are not
 * a point (one is empty, or a text is no number on the globe) the form holds
 * `INVALID_LOCATION`, which the save paths refuse with the message shown
 * here; it is never the old point, which would be saved without a word.
 */
import { useEffect, useRef, useState } from 'react'

import { Input } from '@/components/ui/input'
import {
  INVALID_LOCATION,
  boxesFromPaste,
  coordinateText,
  locationFromBoxes,
  parseLatLon,
  type PlaceLocation,
} from '@/lib/near'
import { Field } from './fields'

const boxesOf = (location: PlaceLocation | null | undefined) =>
  location && Number.isFinite(location.lat) && Number.isFinite(location.lon)
    ? { lat: coordinateText(location.lat), lon: coordinateText(location.lon) }
    : { lat: '', lon: '' }

const keyOf = (location: PlaceLocation | null | undefined) =>
  location ? `${location.lat}|${location.lon}` : ''

export default function PlaceLocationFields({ idPrefix, location, onChange, disabled }: {
  idPrefix: string
  location: PlaceLocation | null | undefined
  onChange: (location: PlaceLocation | null) => void
  disabled?: boolean
}) {
  const [boxes, setBoxes] = useState(() => boxesOf(location))
  const [paste, setPaste] = useState('')
  const [pasting, setPasting] = useState(false)
  const emitted = useRef(keyOf(location))

  // the form was reset or reloaded from elsewhere: show its point
  useEffect(() => {
    if (keyOf(location) === emitted.current) return
    emitted.current = keyOf(location)
    setBoxes(boxesOf(location))
  }, [location])

  const set = (next: { lat: string; lon: string }, fromPaste = false) => {
    setBoxes(next)
    if (!fromPaste) setPaste('')              // typed boxes no longer match a pasted text
    const { location: found, problem } = locationFromBoxes(next.lat, next.lon)
    const value = problem ? INVALID_LOCATION : found
    emitted.current = keyOf(value)
    onChange(value)
  }

  const problem = locationFromBoxes(boxes.lat, boxes.lon).problem
  // said once the typing stops, not on the way to a whole pair
  const pasteProblem = !pasting && paste.trim() !== '' && !parseLatLon(paste)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Latitude" htmlFor={`${idPrefix}-lat`}>
          <Input
            id={`${idPrefix}-lat`}
            inputMode="decimal"
            autoComplete="off"
            value={boxes.lat}
            disabled={disabled}
            aria-invalid={problem ? true : undefined}
            placeholder="49.8728"
            onChange={(event) => set({ ...boxes, lat: event.target.value })}
          />
        </Field>
        <Field label="Longitude" htmlFor={`${idPrefix}-lon`}>
          <Input
            id={`${idPrefix}-lon`}
            inputMode="decimal"
            autoComplete="off"
            value={boxes.lon}
            disabled={disabled}
            aria-invalid={problem ? true : undefined}
            placeholder="8.6512"
            onChange={(event) => set({ ...boxes, lon: event.target.value })}
          />
        </Field>
      </div>
      <Field
        label="Or paste both"
        htmlFor={`${idPrefix}-latlon`}
        hint="Latitude, longitude as a map shows them, for example 49.8728, 8.6512. Empty both boxes to remove the location."
      >
        <Input
          id={`${idPrefix}-latlon`}
          autoComplete="off"
          value={paste}
          disabled={disabled}
          aria-invalid={pasteProblem || undefined}
          placeholder="49.8728, 8.6512"
          onFocus={() => setPasting(true)}
          onBlur={() => setPasting(false)}
          onChange={(event) => {
            // the field keeps its text; every change that reads as a pair
            // fills both boxes, so the last state wins (typing "49.8728, 8.6512"
            // passes through longitude 8 and ends on 8.6512)
            const text = event.target.value
            setPaste(text)
            const next = boxesFromPaste(text, boxes)
            if (next !== boxes) set(next, true)
          }}
        />
      </Field>
      {pasteProblem && (
        <p className="text-xs text-destructive">
          Two numbers, latitude (-90 to 90) and longitude (-180 to 180), for example 49.8728, 8.6512.
        </p>
      )}
      {problem && <p className="text-xs text-destructive" role="alert">{problem}</p>}
    </div>
  )
}
