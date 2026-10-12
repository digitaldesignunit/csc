'use client'

/**
 * The compact component preview, one panel for Browse and the component map
 * (decision 8.141 a): a side sheet of about 420 px on a desktop, a bottom sheet
 * of about 60 % of the height on a phone. It holds the viewer without toolbar
 * or menus (rotate and zoom), a slim header with the name, the catalogue
 * number and the dataset, "Open" and an icon for "Find via QR code". The
 * previous and next buttons and the arrow keys step through the items the
 * page shows. The page behind stays usable (no dimming layer), so a click on
 * another thumbnail changes the preview.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { ChevronLeft, ChevronRight, QrCode } from 'lucide-react'

import ComponentViewer from '@/components/components/ComponentViewer'
import ComponentViewerSkeleton from '@/components/components/ComponentViewerSkeleton'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { stepIndex } from '@/lib/previewStep'

export type PreviewItem = {
  id: string
  name?: string | null
  number?: number | null
  dataset?: string | null
}

type PreviewApi = { open: (id: string) => void; close: () => void; activeId: string | null }

const PreviewContext = createContext<PreviewApi | null>(null)

/** The preview of the page, or null outside a PreviewProvider. */
export function usePreview(): PreviewApi | null {
  return useContext(PreviewContext)
}

async function fetchCompose(identityId: string): Promise<CatalogComponent> {
  const res = await fetch(
    `/api/backend/identities/${encodeURIComponent(identityId)}/compose`,
    { method: 'GET', credentials: 'include', cache: 'no-store' },
  )
  if (res.status === 401) throw new Error('unauthorized')
  if (!res.ok) throw new Error(`Failed to fetch the component: ${res.status}`)
  return (await res.json()) as CatalogComponent
}

const isTyping = (target: EventTarget | null) => {
  const el = target as HTMLElement | null
  if (!el || !el.tagName) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable
}

export function PreviewProvider({
  items,
  children,
}: {
  /** what the page shows, in order: the arrow keys step through it */
  items: PreviewItem[]
  children: React.ReactNode
}) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const open = useCallback((id: string) => setActiveId(id), [])
  const close = useCallback(() => setActiveId(null), [])
  const api = useMemo(() => ({ open, close, activeId }), [open, close, activeId])
  return (
    <PreviewContext.Provider value={api}>
      {children}
      <PreviewPanel items={items} activeId={activeId} onActive={setActiveId} />
    </PreviewContext.Provider>
  )
}

function PreviewPanel({
  items,
  activeId,
  onActive,
}: {
  items: PreviewItem[]
  activeId: string | null
  onActive: (id: string | null) => void
}) {
  const router = useRouter()
  const pathname = usePathname()
  const desktop = useMediaQuery('(min-width: 768px)')
  const cache = useRef(new Map<string, CatalogComponent>())
  const [catalog, setCatalog] = useState<CatalogComponent | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!activeId) return undefined
    const known = cache.current.get(activeId)
    if (known) {
      setCatalog(known)
      setFailed(false)
      return undefined
    }
    let cancelled = false
    setCatalog(null)
    setFailed(false)
    fetchCompose(activeId)
      .then((body) => {
        cache.current.set(activeId, body)
        if (!cancelled) setCatalog(body)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof Error && err.message === 'unauthorized') {
          router.push(`/auth/signin?callbackUrl=${encodeURIComponent(pathname)}`)
          onActive(null)
          return
        }
        setFailed(true)
      })
    return () => { cancelled = true }
  }, [activeId, router, pathname, onActive])

  const position = activeId ? items.findIndex((item) => item.id === activeId) : -1
  const step = useCallback((delta: 1 | -1) => {
    const next = stepIndex(position, items.length, delta)
    if (next !== null) onActive(items[next].id)
  }, [position, items, onActive])

  useEffect(() => {
    if (!activeId) return undefined
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || isTyping(event.target)) return
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') { event.preventDefault(); step(1) }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') { event.preventDefault(); step(-1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeId, step])

  if (!activeId) return null
  const item = items.find((i) => i.id === activeId)
  const identity = catalog?.identity
  const snapshot = catalog ? primarySnapshot(catalog) : null
  const name = (snapshot?.name && String(snapshot.name).trim()) || item?.name || 'Unnamed component'
  const number = identity?.catalog_number ?? item?.number ?? null
  const dataset = identity?.dataset ?? item?.dataset ?? null
  const href = `/components/${encodeURIComponent(activeId)}`
  const canPrev = stepIndex(position, items.length, -1) !== null
  const canNext = stepIndex(position, items.length, 1) !== null

  return (
    <Sheet open modal={false} onOpenChange={(next) => { if (!next) onActive(null) }}>
      <SheetContent
        side={desktop ? 'right' : 'bottom'}
        overlay={false}
        onInteractOutside={(event) => event.preventDefault()}
        onOpenAutoFocus={(event) => event.preventDefault()}
        aria-label="Component preview"
        className={desktop
          ? 'w-[420px] gap-2 p-3 sm:max-w-[420px]'
          : 'h-[60dvh] gap-2 rounded-t-xl p-3'}
      >
        <SheetHeader className="space-y-0.5 p-0 pr-8">
          <SheetTitle className="truncate text-sm font-semibold" title={name}>{name}</SheetTitle>
          <SheetDescription className="truncate text-xs">
            {number !== null && number !== undefined ? `#${number}` : 'No number yet'}
            {dataset ? ` - ${dataset}` : ''}
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1">
          {catalog ? (
            <ComponentViewer key={activeId} catalog={catalog} fill bare />
          ) : failed ? (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground" role="alert">
              The preview could not be loaded. Open the component to see it.
            </p>
          ) : (
            <ComponentViewerSkeleton message="Loading geometry..." />
          )}
        </div>

        <TooltipProvider>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="icon" className="h-8 w-8" disabled={!canPrev}
              onClick={() => step(-1)} aria-label="Previous component">
              <ChevronLeft className="h-4 w-4" aria-hidden />
            </Button>
            <Button type="button" variant="outline" size="icon" className="h-8 w-8" disabled={!canNext}
              onClick={() => step(1)} aria-label="Next component">
              <ChevronRight className="h-4 w-4" aria-hidden />
            </Button>
            <Button asChild size="sm" className="h-8 flex-1">
              <Link href={href}>Open</Link>
            </Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button asChild variant="outline" size="icon" className="h-8 w-8">
                  <Link href={`/scan?mode=locate&reference_id=${encodeURIComponent(activeId)}`}
                    aria-label="Find via QR code">
                    <QrCode className="h-4 w-4" aria-hidden />
                  </Link>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Find via QR code</TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
      </SheetContent>
    </Sheet>
  )
}
