'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import ComponentViewer from '../ComponentViewer'
import ComponentViewerSkeleton from '../ComponentViewerSkeleton'
import { ComponentModel } from '@/generated/ComponentModel'
import type { CatalogComponent } from '@/generated/CatalogModels'
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

async function fetchCatalogComposePreview(
  identityId: string,
): Promise<CatalogComponent> {
  const res = await fetch(
    `/api/backend/identities/${encodeURIComponent(identityId)}/compose`,
    { method: 'GET', credentials: 'include', cache: 'no-store' },
  )
  if (res.status === 401) throw new Error('unauthorized')
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to fetch compose: ${res.status} ${body}`)
  }
  return (await res.json()) as CatalogComponent
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

  const detailBasePath = isArchived ? '/archive/components' : '/components'
  const showFindComponent = !isArchived
  const router = useRouter()
  const compId = component_data._id
  const compName =
    typeof component_data.name === 'string' && component_data.name.trim().length > 0
      ? component_data.name
      : 'Unnamed component'

  const shallowRow = component_data as ComponentModel & {
    current_snapshot_id?: string
  }
  const snapshotThumbId =
    typeof shallowRow.current_snapshot_id === 'string' && shallowRow.current_snapshot_id.trim().length > 0
      ? shallowRow.current_snapshot_id
      : null

  const [open, setOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [catalogPreview, setCatalogPreview] = useState<CatalogComponent | null>(
    null,
  )

  useEffect(() => {
    setOpen(false)
    setIsLoading(false)
    setCatalogPreview(null)
  }, [compId])

  const handleOpenPreview = async () => {
    setOpen(true)
    if (catalogPreview) return
    setIsLoading(true)
    try {
      const compose = await fetchCatalogComposePreview(compId as string)
      setCatalogPreview(compose)
    } catch (e: unknown) {
      console.error('Error fetching compose for preview:', e)
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
      <div className="inline-flex items-center gap-2 min-w-0">
        <TooltipProvider>
          <Tooltip delayDuration={200}>
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
                    snapshot_id={snapshotThumbId}
                    alt={compId as string}
                    width={40}
                    height={40}
                    maxHeight={40}
                  />
                </button>
              </SheetTrigger>
            </TooltipTrigger>

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
      </div>

      <SheetContent side="bottom" className="sm:max-w-none">
        <SheetHeader>
          <SheetTitle className="text-center text-base">Component Preview</SheetTitle>
          <SheetDescription>
            <span className="block text-center text-sm font-semibold">{compName}</span>
            <span className="block text-center text-xs font-bold">{compId}</span>
          </SheetDescription>
        </SheetHeader>

        {isLoading && <ComponentViewerSkeleton message="Loading Geometry..." />}
        {!isLoading && catalogPreview && (
          <ComponentViewer catalog={catalogPreview} />
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
                  <Link href={`/locate-by-id?reference_id=${compId}`} className="w-full sm:w-[200px]">
                    <Button variant="outline" className="h-8 w-full">
                      Locate by ID
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
