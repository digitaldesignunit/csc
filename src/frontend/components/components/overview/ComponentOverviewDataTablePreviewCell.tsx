'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import ComponentViewer from '../ComponentViewer'
import ComponentViewerSkeleton from '../ComponentViewerSkeleton'
import { ComponentModel } from '@/generated/ComponentModel'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import ComponentPreviewImage from '../ComponentPreviewImage'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

type Geometry = ComponentModel['geometry']

async function fetch_component_geometry(
  component_id: string,
  apiBasePath: string = '/api/backend'
): Promise<{ geometry: Geometry }> {
  const res = await fetch(
    `${apiBasePath}/components/${encodeURIComponent(component_id)}/geometry`,
    { method: 'GET', credentials: 'include', cache: 'no-store' }
  )
  if (res.status === 401) throw new Error('unauthorized')
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to fetch component geometry: ${res.status} ${body}`)
  }
  return res.json() as Promise<{ geometry: Geometry }>
}

export interface PreviewCellConfig {
  /** Whether this is for archived components */
  isArchived?: boolean
}

export default function ComponentOverviewDataTablePreviewCell({
  component_data,
  config = {},
}: {
  component_data: ComponentModel
  config?: PreviewCellConfig
}) {
  const { isArchived = false } = config

  // Derive paths based on whether this is archived or not
  const detailBasePath = isArchived ? '/admin/archive' : '/components'
  const apiBasePath = isArchived ? '/api/backend/archived' : '/api/backend'
  const showFindComponent = !isArchived
  const router = useRouter()
  const compId = component_data._id

  const [open, setOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [geometry, setGeometry] = useState<Geometry | null>(null)

  // Reset state when the row changes (sorting/filtering)
  useEffect(() => {
    setOpen(false)
    setIsLoading(false)
    setGeometry(null)
  }, [compId])

  const handleOpenPreview = async () => {
    setOpen(true)
    if (geometry) return
    setIsLoading(true)
    try {
      const data = await fetch_component_geometry(compId as string, apiBasePath)
      setGeometry(data.geometry)
    } catch (e: unknown) {
      console.error('Error fetching Component Geometry:', e)
      if (e instanceof Error && e.message.toLowerCase().includes('unauthorized')) {
        router.push(`/auth/signin?callbackUrl=${detailBasePath}`)
      }
      setOpen(false)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {/* Compact inline preview cell: 40px thumb + clipped id button */}
      <div className="inline-flex items-center gap-2 min-w-0">
        <TooltipProvider>
          <Tooltip delayDuration={200}>
            {/* Compose triggers: TooltipTrigger wraps SheetTrigger, both asChild,
              so they attach to the SAME <button> element */}
            <TooltipTrigger asChild>
              <SheetTrigger asChild>
                <button
                  type="button"
                  onClick={handleOpenPreview}
                  className="h-10 w-10 shrink-0 overflow-hidden rounded-md border bg-white focus:outline-none focus:ring-2 focus:ring-ring"
                  aria-label="Open component preview"
                >
                  <ComponentPreviewImage
                    key={compId}
                    comp_id={compId as string}
                    alt={compId as string}
                    width={40}
                    height={40}
                    maxHeight={40}
                  />
                </button>
              </SheetTrigger>
            </TooltipTrigger>

            {/* show on desktop; hide on mobile */}
            <TooltipContent side="top" className="hidden sm:block">
              <div className="text-center text-sm">Click to preview this component</div>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider>
          <Tooltip delayDuration={200}>
            <TooltipTrigger asChild>
              <Link href={`${detailBasePath}/${compId}`} className="min-w-0">
                <Button
                  variant="ghost"
                  className="h-6 px-2 text-xs max-w-[16rem] truncate"
                  title={compId}
                >
                  {compId}
                </Button>
              </Link>
            </TooltipTrigger>
            <TooltipContent side="top" className="hidden sm:block">
              <div className="text-center text-sm">Open component details</div>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Bottom sheet preview */}
      <SheetContent side="bottom" className="sm:max-w-none">
        <SheetHeader>
          <SheetTitle className="text-center text-base">Component Preview</SheetTitle>
          {/* prevent <p> inside <p> nesting (SheetDescription renders <p>) */}
          <SheetDescription>
            <span className="block text-center text-sm font-bold">{compId}</span>
          </SheetDescription>
        </SheetHeader>

        {isLoading && <ComponentViewerSkeleton message="Loading Geometry..." />}
        {!isLoading && geometry && (
          <ComponentViewer
            component_data={{ ...component_data, geometry }}
            geometryEndpoint={isArchived ? `${apiBasePath}/components/${compId}/geometry_reduced` : undefined}
          />
        )}

        <SheetFooter className="mt-4 flex flex-col items-center justify-center gap-2 sm:flex-row">
          <Link href={`${detailBasePath}/${compId}`} className="w-full sm:w-[200px]">
            <Button variant="outline" className="h-8 w-full">
              Open Detail Page
            </Button>
          </Link>

          {showFindComponent && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link href={`/findcomponent?reference_id=${compId}`} className="w-full sm:w-[200px]">
                    <Button variant="outline" className="h-8 w-full">
                      Find Component
                    </Button>
                  </Link>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="text-center">Find via QR code</div>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}

          <SheetClose asChild className="w-full sm:w-[200px]">
            <Button variant="outline" className="h-8 w-full">
              Close Preview
            </Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
