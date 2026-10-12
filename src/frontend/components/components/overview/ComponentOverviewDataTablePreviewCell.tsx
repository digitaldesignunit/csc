'use client'

/**
 * The name cell of a Browse row: the thumbnail opens the compact preview
 * (decision 8.141 a, shared with the component map), the name opens the
 * component.
 */
import Link from 'next/link'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import ComponentPreviewImage from '../ComponentPreviewImage'
import InPlaceBadge from '../InPlaceBadge'
import { isInPlace } from '../componentDetailShared'
import { usePreview } from '../preview/ComponentPreview'

export default function ComponentOverviewDataTablePreviewCell({
  component_data,
}: {
  component_data: CatalogShallowRow
}) {
  const preview = usePreview()
  const compId = component_data._id
  const compName =
    typeof component_data.name === 'string' && component_data.name.trim().length > 0
      ? component_data.name
      : 'Unnamed component'

  // a row that says it has no preview does not ask for one (no 404 per row)
  const snapshotThumbId =
    component_data.has_preview !== false &&
    typeof component_data.current_snapshot_id === 'string' &&
    component_data.current_snapshot_id.trim().length > 0
      ? component_data.current_snapshot_id
      : null

  const detailHref = `/components/${compId}`
  const active = preview?.activeId === compId

  return (
    <div className="inline-flex items-center gap-2 min-w-0">
      <TooltipProvider>
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => preview?.open(compId as string)}
              className={`relative h-10 w-10 shrink-0 overflow-hidden rounded-md border bg-white focus:outline-none focus:ring-2 focus:ring-ring ${active ? 'ring-2 ring-primary' : ''}`}
              aria-label="Open component preview"
              aria-pressed={active}
            >
              <ComponentPreviewImage
                key={compId}
                snapshot_id={snapshotThumbId}
                alt={compId as string}
                width={40}
                height={40}
                maxHeight={40}
                className="h-full w-full"
              />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="hidden sm:block">
            <div className="text-center text-sm">Click to preview this component</div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <TooltipProvider>
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <Link href={detailHref} className="min-w-0">
              <Button
                variant="ghost"
                className="h-6 px-2 text-xs max-w-[16rem] truncate justify-start"
                title={compName}
              >
                {compName}
              </Button>
            </Link>
          </TooltipTrigger>
          <TooltipContent side="top" className="hidden sm:block">
            <div className="text-center text-sm">Open component details</div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      {isInPlace(component_data) && <InPlaceBadge />}
    </div>
  )
}
