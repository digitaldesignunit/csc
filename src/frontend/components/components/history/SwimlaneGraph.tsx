'use client'

/**
 * The swimlane graph of the History card (decision 8.140): the piece in the
 * middle, its parents above, its children below, events along a time axis
 * (sections by year, not to scale). A version click shows that version on the
 * page, an evidence group opens into its records, a record click scrolls to
 * its card, a lane's header opens that piece. The page scrolls sideways; the
 * events take the keyboard. The export (an SVG or a PNG of the whole timeline
 * with a legend, or the data as JSON) is in the menu next to the depth.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Download, FileJson, FileImage, Loader2, Minus, Plus } from 'lucide-react'
import { toast } from 'sonner'

import SwimlaneSvg from '@/components/components/history/SwimlaneSvg'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { BackendError, backendJson } from '@/lib/backend'
import { downloadBlob, exportFileName, svgText, svgToPng } from '@/lib/history/export'
import {
  GEOMETRY,
  applyLayers,
  describeEvent,
  expandGroups,
  groupKey,
  laneTitle,
  layoutSwimlane,
  type Layout,
  type PlacedEvent,
} from '@/lib/history/swimlane'
import type { HistoryEvent, HistoryLayers, HistoryResponse } from '@/lib/history/types'

/** the legend needs about 870 px; the lane names take 190 of them */
const EXPORT_MIN_WIDTH = 700

type Tip = { placed: PlacedEvent; left: number; top: number }

const path = (id: string, depth: number, expand: 'groups' | 'all') =>
  `/identities/${encodeURIComponent(id)}/history?depth=${depth}&expand=${expand}`

/** Every evidence record of the lanes, by id (from the `expand=all` answer). */
function recordsOf(history: HistoryResponse): Map<string, HistoryEvent> {
  const out = new Map<string, HistoryEvent>()
  for (const lane of history.lanes) {
    for (const event of lane.events ?? []) if (event.kind === 'evidence' && event.id) out.set(event.id, event)
  }
  return out
}

export default function SwimlaneGraph({
  identityId,
  catalogNumber,
  layers,
  activeSnapshotId,
  reloadStamp,
}: {
  identityId: string
  catalogNumber?: number | null
  layers: HistoryLayers
  activeSnapshotId: string
  /** changes when the piece changed (an action on it): the graph reloads */
  reloadStamp: string
}) {
  const router = useRouter()
  const [depth, setDepth] = useState<1 | 2>(1)
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [full, setFull] = useState<HistoryResponse | null>(null)
  const [opened, setOpened] = useState<Set<string>>(new Set())
  const [tip, setTip] = useState<Tip | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [job, setJob] = useState<{ kind: 'svg' | 'png'; layout: Layout } | null>(null)
  const frame = useRef<HTMLDivElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const [reach, setReach] = useState(320)
  const exportRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    let cancelled = false
    setHistory(null)
    setFull(null)
    setOpened(new Set())
    backendJson<HistoryResponse>(path(identityId, depth, 'groups'))
      .then((body) => { if (!cancelled) { setHistory(body); setError(null) } })
      .catch((err) => {
        if (!cancelled) setError(err instanceof BackendError ? err.message : 'Could not load the history graph.')
      })
    return () => { cancelled = true }
  }, [identityId, depth, reloadStamp])

  const loadFull = useCallback(async (): Promise<HistoryResponse> => {
    if (full) return full
    const body = await backendJson<HistoryResponse>(path(identityId, depth, 'all'))
    setFull(body)
    return body
  }, [full, identityId, depth])

  const records = useMemo(() => (full ? recordsOf(full) : new Map<string, HistoryEvent>()), [full])
  const layout = useMemo(() => {
    if (!history) return null
    return layoutSwimlane(applyLayers(expandGroups(history, opened, records), layers), reach)
  }, [history, opened, records, layers, reach])

  // the bands reach the right edge of the frame when the graph is narrower
  const ready = history !== null
  useEffect(() => {
    const element = scroller.current
    if (!element) return undefined
    const update = () => setReach(Math.max(320, Math.floor(element.clientWidth)))
    update()
    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [ready])

  const toggleGroup = useCallback(async (key: string) => {
    if (opened.has(key)) {
      setOpened((prev) => { const next = new Set(prev); next.delete(key); return next })
      return
    }
    setBusy(key)
    try {
      await loadFull()
      setOpened((prev) => new Set(prev).add(key))
    } catch {
      toast.error('Could not load the records')
    } finally {
      setBusy(null)
    }
  }, [opened, loadFull])

  const onEvent = (placed: PlacedEvent) => {
    const { event, laneId } = placed
    if (event.kind === 'version' && event.id) {
      router.push(`/components/${encodeURIComponent(laneId)}?snapshot=${encodeURIComponent(event.id)}`)
    } else if (event.kind === 'evidence_group') {
      void toggleGroup(groupKey(laneId, event))
    } else if (event.kind === 'evidence' && event.id) {
      if (laneId !== identityId) {
        router.push(`/components/${encodeURIComponent(laneId)}#record-${encodeURIComponent(event.id)}`)
        return
      }
      const card = document.getElementById(`record-${event.id}`)
      if (card) {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' })
        card.classList.add('ring-2', 'ring-primary')
        window.setTimeout(() => card.classList.remove('ring-2', 'ring-primary'), 1800)
      } else {
        toast.message('That record is not on this version of the page.')
      }
    }
  }

  const onHover = (placed: PlacedEvent | null, target: Element | null) => {
    if (!placed || !target || !frame.current) { setTip(null); return }
    const box = target.getBoundingClientRect()
    const host = frame.current.getBoundingClientRect()
    // kept 100 px from both edges, so that the 15 rem tooltip stays inside the frame
    const left = Math.min(Math.max(box.left - host.left + box.width / 2, 100), Math.max(100, host.width - 100))
    setTip({ placed, left, top: box.top - host.top })
  }

  // the export: the whole timeline, every record its own event, with a legend
  const startExport = async (kind: 'svg' | 'png' | 'json') => {
    setBusy(kind)
    try {
      const all = await loadFull()
      if (kind === 'json') {
        downloadBlob(
          new Blob([`${JSON.stringify(all, null, 2)}\n`], { type: 'application/json' }),
          exportFileName(catalogNumber, identityId, 'json'),
        )
        setBusy(null)
        return
      }
      // wide enough for the legend
      setJob({ kind, layout: layoutSwimlane(all, EXPORT_MIN_WIDTH) })
    } catch (err) {
      toast.error(err instanceof BackendError ? err.message : 'Could not prepare the export')
      setBusy(null)
    }
  }

  useEffect(() => {
    if (!job) return
    let cancelled = false
    const run = async () => {
      // one frame so that the hidden drawing is in the document
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
      const svg = exportRef.current
      if (!svg || cancelled) return
      try {
        const text = svgText(svg)
        if (job.kind === 'svg') {
          downloadBlob(new Blob([text], { type: 'image/svg+xml;charset=utf-8' }), exportFileName(catalogNumber, identityId, 'svg'))
        } else {
          const width = Number(svg.getAttribute('width'))
          const height = Number(svg.getAttribute('height'))
          downloadBlob(await svgToPng(text, width, height), exportFileName(catalogNumber, identityId, 'png'))
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'The export failed')
      } finally {
        if (!cancelled) { setJob(null); setBusy(null) }
      }
    }
    void run()
    return () => { cancelled = true }
  }, [job, catalogNumber, identityId])

  if (error) return <p className="p-3 text-sm text-destructive" role="alert">{error}</p>
  if (!history || !layout) {
    return <div className="flex h-40 items-center justify-center text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
  }

  const title = `History of #${catalogNumber ?? ''}, ${new Date().toISOString().slice(0, 10)}`
  const tipText = tip ? describeEvent(tip.placed.event) : null
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1" role="group" aria-label="Generations shown">
          <Button type="button" size="sm" variant="outline" className="h-7 gap-1 px-2 text-xs"
            disabled={depth === 1 && history.lanes.length <= 1}
            onClick={() => setDepth(depth === 1 ? 2 : 1)}
            title={depth === 1 ? 'Also the grandparents and the grandchildren' : 'Only parents and children'}>
            {depth === 1 ? <Plus className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
            {depth === 1 ? 'Show more' : 'Show less'}
          </Button>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" size="sm" variant="outline" className="h-7 gap-1 px-2 text-xs" disabled={busy === 'svg' || busy === 'png' || busy === 'json'}>
              {busy === 'svg' || busy === 'png' || busy === 'json'
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Download className="h-3.5 w-3.5" />}
              Export
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="text-xs">
            <DropdownMenuItem onSelect={() => void startExport('svg')}>
              <FileImage className="mr-2 h-3.5 w-3.5" aria-hidden />Image, SVG (print, papers)
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void startExport('png')}>
              <FileImage className="mr-2 h-3.5 w-3.5" aria-hidden />Image, PNG
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void startExport('json')}>
              <FileJson className="mr-2 h-3.5 w-3.5" aria-hidden />Data, JSON (lanes, events, links)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <p className="text-xs text-muted-foreground">
          Time is in sections and not to scale. Click a version to show it, a number to open its records.
        </p>
      </div>

      <div ref={frame} className="relative">
      <div className="flex overflow-hidden rounded-md border border-border bg-card">
        <ul className="w-32 shrink-0 border-r border-border text-xs sm:w-44" style={{ paddingTop: layout.headerHeight }} aria-label="Pieces">
          {layout.lanes.map(({ lane }) => (
            <li key={lane.id} className="flex flex-col justify-center border-b border-border px-2" style={{ height: GEOMETRY.rowHeight }}>
              {lane.visible && lane.role !== 'piece' ? (
                <Link href={`/components/${encodeURIComponent(lane.id)}`} className="line-clamp-2 font-medium underline underline-offset-2">
                  {laneTitle(lane)}
                </Link>
              ) : (
                <span className={lane.role === 'piece' ? 'line-clamp-2 font-semibold' : 'text-muted-foreground italic'}>
                  {laneTitle(lane)}
                </span>
              )}
              <span className="truncate text-[10px] text-muted-foreground">
                {lane.role === 'parent' ? 'parent' : lane.role === 'child' ? 'child' : 'this piece'}
                {lane.visible && lane.dataset ? ` - ${lane.dataset}` : ''}
              </span>
            </li>
          ))}
        </ul>
        <div ref={scroller} className="min-w-0 flex-1 overflow-x-auto" tabIndex={-1}>
          <SwimlaneSvg
            layout={layout}
            activeVersionId={activeSnapshotId}
            focusKey={tip?.placed.key ?? null}
            onEvent={onEvent}
            onHover={onHover}
            onCollapse={(key) => void toggleGroup(key)}
          />
        </div>
      </div>
        {tip && tipText && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-20 max-w-60 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-popover px-2 py-1.5 text-xs text-popover-foreground shadow-md"
            style={{ left: tip.left, top: tip.top - 6 }}
          >
            <p className="font-medium">{tipText.title}</p>
            {tipText.lines.map((line) => <p key={line} className="text-muted-foreground">{line}</p>)}
          </div>
        )}
      </div>
      {history.more > 0 && (
        <p className="text-xs text-muted-foreground">
          <span className="rounded-full border border-border px-2 py-0.5">+{history.more} more</span>{' '}
          {history.more === 1 ? 'piece is' : 'pieces are'} not drawn (twelve lanes at most). The JSON export lists what the lanes hold.
        </p>
      )}
      {busy && busy.includes('|') && <p className="text-xs text-muted-foreground" role="status">Loading the records...</p>}

      {job && (
        <div aria-hidden className="pointer-events-none fixed left-[-100000px] top-0">
          <SwimlaneSvg layout={job.layout} palette="print" withLabels legend title={title} svgRef={exportRef} />
        </div>
      )}
    </div>
  )
}
