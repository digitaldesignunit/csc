'use client'

import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import React from 'react'
import ComponentDetailMap from '../ComponentDetailMap';
import { formatLocation, formatLocationMapsLink } from '@/lib/utils'
import { ComponentLocation } from '@/generated/ComponentModel'

export default function ComponentOverviewDataTableLocationCell({ coords }: { coords: ComponentLocation }) {
  const location: string = formatLocation(coords)
  const locationlink: string = formatLocationMapsLink(coords)
  const { lat, lon } = coords;
  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <a
              href={locationlink}
              target='_blank'
              rel='noopener noreferrer'
              className='hover:text-gray-500'
            >
              {location}
            </a>
          </TooltipTrigger>
          <TooltipContent>
              <ComponentDetailMap lat={lat} lon={lon} />
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </>
  )
}
