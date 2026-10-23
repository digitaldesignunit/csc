'use client'

import { formatLocation, formatLocationMapsLink } from '@/lib/utils'
import { GeoLocation } from '@/generated/CatalogSharedTypes'

/**
 * A location in the table: a plain link that opens Google Maps in a new tab
 * on a click. There is no map preview on hover (decision 8.176): an embedded
 * map sent every visitor who pointed at a location to Google.
 */
export default function ComponentOverviewDataTableLocationCell({ coords }: { coords: GeoLocation }) {
  return (
    <a
      href={formatLocationMapsLink(coords)}
      target='_blank'
      rel='noopener noreferrer'
      title='Open in Google Maps'
      className='hover:text-gray-500'
    >
      {formatLocation(coords)}
    </a>
  )
}
