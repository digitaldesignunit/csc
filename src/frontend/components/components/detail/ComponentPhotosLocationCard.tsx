'use client'

/**
 * Photos and location in one card (decision 8.118, S4): how the piece looks
 * and where it is, in one place. An empty state is one line; the location is
 * the coordinates with a link to the map instead of a map for a point that
 * hundreds of pieces share. A piece without a location says so (P9).
 */
import { Camera, MapPin } from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import type { GeoLocation } from '@/generated/CatalogSharedTypes'
import { formatLocation, formatLocationMapsLink } from '@/lib/utils'
import ComponentSnapshotPhotoGallery from '../ComponentSnapshotPhotoGallery'

export default function ComponentPhotosLocationCard({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const snapshotId = String(snapshot._id ?? identity.current_snapshot_id ?? '')
  const location = (snapshot.location as GeoLocation | null | undefined) ?? null
  const located = !!location && location.lat != null && location.lon != null

  return (
    <section aria-label="Photos and location" className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Camera className="h-4 w-4" />
        Photos and location
      </h2>
      <ComponentSnapshotPhotoGallery
        snapshotId={snapshotId}
        photoCount={snapshot.photo_count}
        compact
        embedded
        allowUpload={snapshot.status !== 'published'}
        credit={(snapshot as { photo_credit?: unknown }).photo_credit}
      />
      <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-border/60 pt-2 text-xs">
        <MapPin className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        {located && location ? (
          <>
            <span className="font-medium tabular-nums">{formatLocation(location)}</span>
            <a href={formatLocationMapsLink(location)} target="_blank" rel="noopener noreferrer"
              className="text-primary underline underline-offset-2">
              Show on map
            </a>
          </>
        ) : (
          <span className="text-muted-foreground">No location recorded.</span>
        )}
      </p>
    </section>
  )
}
