'use client'

import { MapPin } from 'lucide-react'

import { ComponentLocation } from '@/generated/ComponentModel'
import { formatLocation, formatLocationMapsLink } from '@/lib/utils'
import ComponentDetailMap from './ComponentDetailMap'

type ComponentDetailLocationPanelProps = {
  location: ComponentLocation
}

export default function ComponentDetailLocationPanel({
  location,
}: ComponentDetailLocationPanelProps) {
  const lat = location.lat ?? 0
  const lon = location.lon ?? 0
  const label = formatLocation(location)
  const mapsLink = formatLocationMapsLink(location)

  return (
    <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <MapPin className="h-4 w-4" />
        Location
      </h3>
      <a
        href={mapsLink}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs font-medium text-primary hover:underline"
      >
        {label}
      </a>
      <div className="mt-3 h-[200px] lg:h-[260px] w-full overflow-hidden rounded-md">
        <ComponentDetailMap lat={lat} lon={lon} />
      </div>
    </section>
  )
}
