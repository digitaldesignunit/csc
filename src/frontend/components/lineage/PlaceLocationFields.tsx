'use client'

/**
 * The coordinates of the origin place (decision 8.170): the shared pair of
 * latitude and longitude boxes next to the address. Both empty means no
 * location. While the two boxes are not a point (one is empty, or a text is no
 * number on the globe) the form holds `INVALID_LOCATION`, which the save paths
 * refuse with the message shown under the pair; it is never the old point,
 * which would be saved without a word.
 */
import { useEffect, useRef, useState } from 'react'

import LatLonFields, { LAT_LON_HINT } from '@/components/common/LatLonFields'
import {
  INVALID_LOCATION,
  coordinateText,
  locationFromBoxes,
  type LatLonBoxes,
  type PlaceLocation,
} from '@/lib/near'

const boxesOf = (location: PlaceLocation | null | undefined): LatLonBoxes =>
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
  const emitted = useRef(keyOf(location))

  // the form was reset or reloaded from elsewhere: show its point
  useEffect(() => {
    if (keyOf(location) === emitted.current) return
    emitted.current = keyOf(location)
    setBoxes(boxesOf(location))
  }, [location])

  const set = (next: LatLonBoxes) => {
    setBoxes(next)
    const { location: found, problem } = locationFromBoxes(next.lat, next.lon)
    const value = problem ? INVALID_LOCATION : found
    emitted.current = keyOf(value)
    onChange(value)
  }

  return (
    <LatLonFields
      idPrefix={idPrefix}
      lat={boxes.lat}
      lon={boxes.lon}
      onChange={set}
      disabled={disabled}
      problem={locationFromBoxes(boxes.lat, boxes.lon).problem}
      hint={`${LAT_LON_HINT} Empty both boxes to remove the location.`}
    />
  )
}
