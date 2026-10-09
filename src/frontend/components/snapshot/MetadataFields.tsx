'use client'

/**
 * The colour and location fields of a snapshot, shared by the snapshot form
 * and the edit page (spec 3.2.2: mutable metadata).
 */
import { useState } from 'react'
import { Loader2, MapPin } from 'lucide-react'

import { Field } from '@/components/lineage/fields'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { hexToRgb, type SnapshotFields } from '@/lib/snapshotForm'
import { hexComponentColor } from '@/lib/utils'

type Props = {
  fields: Pick<SnapshotFields, 'color' | 'lat' | 'lon'>
  setFields: (patch: Partial<SnapshotFields>) => void
  idPrefix?: string
}

export function ColourField({ fields, setFields, idPrefix = 'sf' }: Props) {
  const colourHex = hexComponentColor(fields.color)
  return (
    <Field label="Colour" htmlFor={`${idPrefix}-colour`}>
      <div className="flex gap-2">
        <Input id={`${idPrefix}-colour`} type="color" value={colourHex}
          onChange={(event) => {
            const rgb = hexToRgb(event.target.value)
            if (rgb) setFields({ color: rgb })
          }}
          className="h-10 w-14 shrink-0 cursor-pointer p-1" />
        <Input value={colourHex} readOnly className="font-mono text-sm" aria-label="Colour hex value" />
      </div>
    </Field>
  )
}

export function LocationFields({ fields, setFields, idPrefix = 'sf' }: Props) {
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState<string | null>(null)

  const locate = () => {
    if (!navigator.geolocation) {
      setLocationError('Geolocation is not supported in this browser.')
      return
    }
    setLocating(true)
    setLocationError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setFields({ lat: pos.coords.latitude.toFixed(6), lon: pos.coords.longitude.toFixed(6) })
        setLocating(false)
      },
      (err) => {
        setLocationError(err.message || 'Could not read your location.')
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Label>Location (optional)</Label>
        <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" disabled={locating}
          onClick={locate}>
          {locating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MapPin className="mr-2 h-4 w-4" />}
          Use my current location
        </Button>
      </div>
      {locationError && <p className="text-sm text-destructive" role="alert">{locationError}</p>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Latitude" htmlFor={`${idPrefix}-lat`}>
          <Input id={`${idPrefix}-lat`} inputMode="decimal" value={fields.lat}
            onChange={(event) => setFields({ lat: event.target.value })} />
        </Field>
        <Field label="Longitude" htmlFor={`${idPrefix}-lon`}>
          <Input id={`${idPrefix}-lon`} inputMode="decimal" value={fields.lon}
            onChange={(event) => setFields({ lon: event.target.value })} />
        </Field>
      </div>
    </div>
  )
}
