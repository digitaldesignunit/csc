'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Loader2, Map as MapIcon, RotateCcw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import ComponentViewer from '@/components/components/ComponentViewer'
import ComponentViewerSkeleton from '@/components/components/ComponentViewerSkeleton'
import type {
  ComponentMapBasis,
  ComponentMapMethod,
  ComponentMapPoint,
  ComponentMapResponse,
} from '@/generated/catalogExtras'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { cn } from '@/lib/utils'

const PAD_DESKTOP = 28
const PAD_MOBILE = 16
const DOT_R = 5.5
const DOT_HIT_R = 12
const DOT_HIT_R_MOBILE = 16
const POINT_STROKE_ACCENT = 1
const POINT_STROKE_INNER = 0.5
const MIN_ZOOM = 0.35
const MAX_ZOOM = 12
const TRANSITION_MS = 700
const ENTER_STAGGER_MS = 12
const CANVAS_HEIGHT_CLASS =
  'h-[min(42dvh,320px)] md:h-full md:min-h-0 md:flex-1'

type ViewBox = { minX: number; minY: number; width: number; height: number }
type Camera = { x: number; y: number; k: number }

type AnimPoint = {
  id: string
  x: number
  y: number
  fromX: number
  fromY: number
  targetX: number
  targetY: number
  opacity: number
  fromOpacity: number
  targetOpacity: number
  enterDelayMs: number
  meta: ComponentMapPoint
}

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3
}

function computeViewBox(points: Array<{ x: number; y: number }>): ViewBox {
  if (points.length === 0) {
    return { minX: -1, minY: -1, width: 2, height: 2 }
  }
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const p of points) {
    minX = Math.min(minX, p.x)
    maxX = Math.max(maxX, p.x)
    minY = Math.min(minY, p.y)
    maxY = Math.max(maxY, p.y)
  }
  const spanX = Math.max(maxX - minX, 1e-6)
  const spanY = Math.max(maxY - minY, 1e-6)
  const padX = spanX * 0.08
  const padY = spanY * 0.08
  return {
    minX: minX - padX,
    minY: minY - padY,
    width: spanX + padX * 2,
    height: spanY + padY * 2,
  }
}

function rgbFromPoint(point: ComponentMapPoint): string | null {
  const c = point.color
  if (Array.isArray(c) && c.length >= 3) {
    const [r, g, b] = c
    if (typeof r === 'number' && typeof g === 'number' && typeof b === 'number') {
      const toByte = (v: number) => (v <= 1 ? Math.round(v * 255) : Math.round(v))
      return `rgb(${toByte(r)} ${toByte(g)} ${toByte(b)})`
    }
  }
  return null
}

function cssColor(el: Element, variable: string, fallback: string): string {
  const value = getComputedStyle(el).getPropertyValue(variable).trim()
  return value || fallback
}

async function fetchCatalogPassportPreview(identityId: string): Promise<CatalogComponent> {
  const res = await fetch(
    `/api/backend/identities/${encodeURIComponent(identityId)}/compose`,
    { method: 'GET', credentials: 'include', cache: 'no-store' },
  )
  if (res.status === 401) throw new Error('unauthorized')
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to fetch passport: ${res.status} ${body}`)
  }
  return (await res.json()) as CatalogComponent
}

function ComponentMapCanvas({
  points,
  method,
  transitioning,
  onSelect,
}: {
  points: ComponentMapPoint[]
  method: string
  transitioning: boolean
  onSelect: (point: ComponentMapPoint) => void
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const sizeRef = useRef({ width: 0, height: 0 })
  const cameraRef = useRef<Camera>({ x: 0, y: 0, k: 1 })
  const hoverIdRef = useRef<string | null>(null)
  const viewRef = useRef<ViewBox>(computeViewBox(points))
  const padRef = useRef(PAD_DESKTOP)
  const hitRRef = useRef(DOT_HIT_R)
  const onSelectRef = useRef(onSelect)
  const drawRef = useRef<() => void>(() => {})

  const [size, setSize] = useState({ width: 0, height: 0 })
  const [hoverId, setHoverId] = useState<string | null>(null)
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, k: 1 })
  const animRef = useRef<AnimPoint[]>([])
  const animStartRef = useRef(0)
  const rafRef = useRef<number | null>(null)
  const dragRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    originX: number
    originY: number
  } | null>(null)
  const pendingSelectRef = useRef<{
    pointerId: number
    point: AnimPoint
  } | null>(null)
  const pointersRef = useRef(
    new Map<number, { x: number; y: number }>(),
  )
  const pinchRef = useRef<{
    distance: number
    k: number
    midX: number
    midY: number
    originX: number
    originY: number
  } | null>(null)
  const [dragging, setDragging] = useState(false)

  const isCompact = size.width > 0 && size.width < 640
  const pad = isCompact ? PAD_MOBILE : PAD_DESKTOP
  const hitR = isCompact ? DOT_HIT_R_MOBILE : DOT_HIT_R
  const view = useMemo(() => computeViewBox(points), [points])

  cameraRef.current = camera
  hoverIdRef.current = hoverId
  viewRef.current = view
  padRef.current = pad
  hitRRef.current = hitR
  onSelectRef.current = onSelect

  const project = useCallback((x: number, y: number, cam: Camera = cameraRef.current) => {
    const { width, height } = sizeRef.current
    const v = viewRef.current
    const p = padRef.current
    if (width <= 0 || height <= 0) return { cx: 0, cy: 0 }
    const sx = (width - p * 2) / v.width
    const sy = (height - p * 2) / v.height
    const bx = p + (x - v.minX) * sx
    const by = height - p - (y - v.minY) * sy
    return {
      cx: bx * cam.k + cam.x,
      cy: by * cam.k + cam.y,
    }
  }, [])

  const hitTest = useCallback((mx: number, my: number): AnimPoint | null => {
    const r2 = hitRRef.current * hitRRef.current
    const pts = animRef.current
    for (let i = pts.length - 1; i >= 0; i--) {
      const p = pts[i]
      if (p.opacity <= 0.05) continue
      const { cx, cy } = project(p.x, p.y)
      const dx = mx - cx
      const dy = my - cy
      if (dx * dx + dy * dy <= r2) return p
    }
    return null
  }, [project])

  drawRef.current = () => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { width, height } = sizeRef.current
    if (width <= 0 || height <= 0) return

    const dpr = window.devicePixelRatio || 1
    const nextW = Math.max(1, Math.round(width * dpr))
    const nextH = Math.max(1, Math.round(height * dpr))
    if (canvas.width !== nextW || canvas.height !== nextH) {
      canvas.width = nextW
      canvas.height = nextH
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'

    const cam = cameraRef.current
    const accent = cssColor(container, '--ring', '#888888')
    const background = cssColor(container, '--background', '#ffffff')
    const primary = cssColor(container, '--primary', '#888888')
    const hover = hoverIdRef.current

    const paint = (p: AnimPoint, active: boolean) => {
      const alpha = Math.max(0, Math.min(1, p.opacity))
      if (alpha <= 0) return
      const { cx, cy } = project(p.x, p.y, cam)

      ctx.globalAlpha = alpha * (active ? 1 : 0.9)
      ctx.beginPath()
      ctx.arc(cx, cy, active ? DOT_R + 3 : DOT_R + 1.5, 0, Math.PI * 2)
      ctx.strokeStyle = accent
      ctx.lineWidth = active ? POINT_STROKE_ACCENT + 0.5 : POINT_STROKE_ACCENT
      ctx.stroke()

      ctx.globalAlpha = alpha
      ctx.beginPath()
      ctx.arc(cx, cy, active ? DOT_R + 2 : DOT_R, 0, Math.PI * 2)
      ctx.fillStyle = rgbFromPoint(p.meta) || primary
      ctx.fill()
      ctx.strokeStyle = background
      ctx.lineWidth = POINT_STROKE_INNER
      ctx.stroke()
    }

    for (const p of animRef.current) {
      if (p.id === hover) continue
      paint(p, false)
    }
    if (hover) {
      const hp = animRef.current.find((p) => p.id === hover)
      if (hp) paint(hp, true)
    }
    ctx.globalAlpha = 1
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const applySize = (width: number, height: number) => {
      const next = {
        width: Math.max(0, Math.floor(width)),
        height: Math.max(0, Math.floor(height)),
      }
      const prev = sizeRef.current
      if (prev.width === next.width && prev.height === next.height) return
      sizeRef.current = next
      setSize(next)
    }

    applySize(el.clientWidth, el.clientHeight)
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      applySize(entry.contentRect.width, entry.contentRect.height)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Retarget animation whenever the layout payload changes.
  useEffect(() => {
    const prevById = new Map(animRef.current.map((p) => [p.id, p]))
    const nextIds = new Set(points.map((p) => p.id))
    const nextAnim: AnimPoint[] = []
    const hasExisting = prevById.size > 0

    points.forEach((p, index) => {
      const prev = prevById.get(p.id)
      if (prev) {
        nextAnim.push({
          id: p.id,
          x: prev.x,
          y: prev.y,
          fromX: prev.x,
          fromY: prev.y,
          targetX: p.x,
          targetY: p.y,
          opacity: prev.opacity,
          fromOpacity: prev.opacity,
          targetOpacity: 1,
          enterDelayMs: 0,
          meta: p,
        })
      } else {
        nextAnim.push({
          id: p.id,
          x: p.x,
          y: p.y,
          fromX: p.x,
          fromY: p.y,
          targetX: p.x,
          targetY: p.y,
          opacity: 0,
          fromOpacity: 0,
          targetOpacity: 1,
          enterDelayMs: Math.min(
            index * ENTER_STAGGER_MS,
            hasExisting ? 500 : 800,
          ),
          meta: p,
        })
      }
    })

    for (const prev of animRef.current) {
      if (nextIds.has(prev.id)) continue
      nextAnim.push({
        ...prev,
        fromX: prev.x,
        fromY: prev.y,
        targetX: prev.x,
        targetY: prev.y,
        fromOpacity: prev.opacity,
        targetOpacity: 0,
        enterDelayMs: 0,
      })
    }

    animRef.current = nextAnim
    animStartRef.current = performance.now()
    cameraRef.current = { x: 0, y: 0, k: 1 }
    setCamera({ x: 0, y: 0, k: 1 })

    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)

    const tick = (now: number) => {
      const start = animStartRef.current
      let stillMoving = false
      const updated: AnimPoint[] = []

      for (const p of animRef.current) {
        const local = Math.max(0, now - start - p.enterDelayMs)
        const t = Math.min(1, local / TRANSITION_MS)
        const e = easeOutCubic(t)
        const ax = p.fromX + (p.targetX - p.fromX) * e
        const ay = p.fromY + (p.targetY - p.fromY) * e
        const aop = p.fromOpacity + (p.targetOpacity - p.fromOpacity) * e
        const done = t >= 1
        if (!done) stillMoving = true
        if (done && p.targetOpacity <= 0) continue
        updated.push({
          ...p,
          x: ax,
          y: ay,
          opacity: aop,
        })
      }

      animRef.current = updated
      drawRef.current()
      if (stillMoving) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        rafRef.current = null
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [points])

  useEffect(() => {
    drawRef.current()
  }, [camera, size, hoverId, view, pad])

  useEffect(() => {
    const root = document.documentElement
    const obs = new MutationObserver(() => drawRef.current())
    obs.observe(root, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  const zoomAt = useCallback((mx: number, my: number, factor: number) => {
    setCamera((prev) => {
      const nextK = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev.k * factor))
      const scale = nextK / prev.k
      return {
        k: nextK,
        x: mx - (mx - prev.x) * scale,
        y: my - (my - prev.y) * scale,
      }
    })
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = canvas.getBoundingClientRect()
      zoomAt(
        event.clientX - rect.left,
        event.clientY - rect.top,
        event.deltaY < 0 ? 1.12 : 1 / 1.12,
      )
    }
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [zoomAt, size.width, size.height])

  const localPoint = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    }
  }

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      if (event.button !== 0 && event.pointerType === 'mouse') return
      pointersRef.current.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      })

      if (pointersRef.current.size >= 2) {
        dragRef.current = null
        pendingSelectRef.current = null
        setDragging(false)
        const pts = [...pointersRef.current.values()]
        const dx = pts[0].x - pts[1].x
        const dy = pts[0].y - pts[1].y
        const rect = event.currentTarget.getBoundingClientRect()
        pinchRef.current = {
          distance: Math.hypot(dx, dy) || 1,
          k: cameraRef.current.k,
          midX: (pts[0].x + pts[1].x) / 2 - rect.left,
          midY: (pts[0].y + pts[1].y) / 2 - rect.top,
          originX: cameraRef.current.x,
          originY: cameraRef.current.y,
        }
        return
      }

      const { x, y } = localPoint(event)
      const hit = hitTest(x, y)
      if (hit) {
        pendingSelectRef.current = { pointerId: event.pointerId, point: hit }
        setHoverId(hit.id)
        return
      }

      event.currentTarget.setPointerCapture(event.pointerId)
      dragRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: cameraRef.current.x,
        originY: cameraRef.current.y,
      }
      setHoverId(null)
      setDragging(true)
    },
    [hitTest],
  )

  const onPointerMove = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (pointersRef.current.has(event.pointerId)) {
      pointersRef.current.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      })
    }

    if (pointersRef.current.size >= 2 && pinchRef.current) {
      const pts = [...pointersRef.current.values()]
      const dx = pts[0].x - pts[1].x
      const dy = pts[0].y - pts[1].y
      const distance = Math.hypot(dx, dy) || 1
      const pinch = pinchRef.current
      const nextK = Math.min(
        MAX_ZOOM,
        Math.max(MIN_ZOOM, pinch.k * (distance / pinch.distance)),
      )
      const scale = nextK / pinch.k
      setCamera({
        k: nextK,
        x: pinch.midX - (pinch.midX - pinch.originX) * scale,
        y: pinch.midY - (pinch.midY - pinch.originY) * scale,
      })
      return
    }

    const drag = dragRef.current
    if (drag && drag.pointerId === event.pointerId) {
      setCamera((prev) => ({
        ...prev,
        x: drag.originX + (event.clientX - drag.startX),
        y: drag.originY + (event.clientY - drag.startY),
      }))
      return
    }

    if (pendingSelectRef.current) return

    const { x, y } = localPoint(event)
    const hit = hitTest(x, y)
    const nextId = hit?.id ?? null
    setHoverId((prev) => (prev === nextId ? prev : nextId))
  }, [hitTest])

  const onPointerUp = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    pointersRef.current.delete(event.pointerId)
    if (pointersRef.current.size < 2) pinchRef.current = null

    const pending = pendingSelectRef.current
    if (pending && pending.pointerId === event.pointerId) {
      pendingSelectRef.current = null
      const { x, y } = localPoint(event)
      const hit = hitTest(x, y)
      if (hit && hit.id === pending.point.id) {
        onSelectRef.current(hit.meta)
      }
    }

    const drag = dragRef.current
    if (drag && drag.pointerId === event.pointerId) {
      dragRef.current = null
      setDragging(false)
      try {
        event.currentTarget.releasePointerCapture(event.pointerId)
      } catch {
        // ignore
      }
    }
  }, [hitTest])

  const onPointerLeave = useCallback(() => {
    if (dragRef.current || pinchRef.current) return
    setHoverId(null)
  }, [])

  const hoverPoint = hoverId
    ? points.find((p) => p.id === hoverId) ?? null
    : null

  return (
    <div
      ref={containerRef}
      className={cn('relative w-full overflow-hidden rounded-md border bg-muted/20', CANVAS_HEIGHT_CLASS)}
    >
      {size.width > 0 && size.height > 0 && (
        <canvas
          ref={canvasRef}
          className="absolute inset-0 touch-none"
          role="img"
          aria-label={`Component map (${method})`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={onPointerLeave}
          style={{
            width: size.width,
            height: size.height,
            cursor: dragging ? 'grabbing' : hoverId ? 'pointer' : 'grab',
          }}
        />
      )}

      {transitioning && (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex justify-center pt-3">
          <Badge variant="secondary" className="gap-1.5 shadow-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Updating layout…
          </Badge>
        </div>
      )}

      {hoverPoint && (
        <div className="pointer-events-none absolute left-2 top-2 z-10 max-w-[calc(100%-1rem)] rounded-md border bg-background/95 px-2 py-1.5 text-xs shadow-sm sm:left-3 sm:top-3 sm:max-w-xs">
          <div className="truncate font-medium">{hoverPoint.name || hoverPoint.id}</div>
          <div className="truncate text-muted-foreground">
            {[hoverPoint.type, hoverPoint.catalog_number != null ? `#${hoverPoint.catalog_number}` : null]
              .filter(Boolean)
              .join(' · ')}
          </div>
        </div>
      )}
      <div className="absolute bottom-2 right-2 z-10 flex flex-col items-end gap-1.5 sm:bottom-3 sm:right-3 sm:flex-row sm:items-center sm:gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-8 gap-1 px-2 text-xs sm:h-7"
          onClick={() => setCamera({ x: 0, y: 0, k: 1 })}
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </Button>
        <Badge variant="secondary" className="uppercase tracking-wide">
          {method} · {camera.k.toFixed(1)}×
        </Badge>
      </div>
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 hidden max-w-[45%] text-[10px] leading-tight text-muted-foreground sm:bottom-3 sm:left-3 sm:block sm:max-w-none sm:text-[11px]">
        Scroll to zoom · drag to pan · click a point to preview
      </div>
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 max-w-[42%] text-[10px] leading-tight text-muted-foreground sm:hidden">
        Pinch zoom · drag · tap preview
      </div>
    </div>
  )
}

export default function ComponentMapPageClient() {
  const router = useRouter()
  const [basis, setBasis] = useState<ComponentMapBasis>('radial_signature')
  const [method, setMethod] = useState<ComponentMapMethod>('umap')
  const [data, setData] = useState<ComponentMapResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [switching, setSwitching] = useState(false)
  const hasMapRef = useRef(false)

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewPoint, setPreviewPoint] = useState<ComponentMapPoint | null>(null)
  const [previewCatalog, setPreviewCatalog] = useState<CatalogComponent | null>(null)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    async function load() {
      const isSwitch = hasMapRef.current
      if (isSwitch) {
        setSwitching(true)
      } else {
        setLoading(true)
      }
      setError(null)

      const params = new URLSearchParams({
        basis,
        method,
        source: 'cache',
        consumed_filter: 'active',
        validated: '1',
      })

      try {
        const res = await fetch(`/api/backend/identities/map?${params}`, {
          cache: 'no-store',
          credentials: 'include',
          signal: controller.signal,
        })
        if (!res.ok) {
          throw new Error(
            res.status === 404
              ? `No cached ${method.toUpperCase()} layout. Run main_component_map.py, then reload.`
              : `Map request failed (${res.status})`,
          )
        }
        const json = (await res.json()) as ComponentMapResponse
        if (cancelled) return
        setData(json)
        hasMapRef.current = json.points.length > 0
        if (json.requested_method !== json.method) {
          setError(
            `Requested ${json.requested_method.toUpperCase()} but cache served ${json.method.toUpperCase()}`,
          )
        } else {
          setError(null)
        }
      } catch (err) {
        if (cancelled || (err as Error).name === 'AbortError') return
        setError((err as Error).message)
        if (!hasMapRef.current) setData(null)
      } finally {
        if (!cancelled) {
          setLoading(false)
          setSwitching(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [basis, method])

  const openPreview = useCallback(
    async (point: ComponentMapPoint) => {
      setPreviewPoint(point)
      setPreviewCatalog(null)
      setPreviewOpen(true)
      setPreviewLoading(true)
      try {
        const passport = await fetchCatalogPassportPreview(point.id)
        setPreviewCatalog(passport)
      } catch (e: unknown) {
        console.error('Error fetching passport for map preview:', e)
        if (e instanceof Error && e.message.toLowerCase().includes('unauthorized')) {
          router.push(`/auth/signin?callbackUrl=/components/map`)
        }
        setPreviewOpen(false)
      } finally {
        setPreviewLoading(false)
      }
    },
    [router],
  )

  const coverage = data
    ? `Displaying ${data.displayed}/${data.total} components with ${data.basis_label}`
    : null

  const cacheNote = data?.computed_at
    ? `Cached ${new Date(data.computed_at).toLocaleString()}`
    : data?.source === 'live'
      ? 'Live compute'
      : null

  const previewName =
    (previewPoint?.name && String(previewPoint.name).trim()) ||
    previewPoint?.id ||
    'Component'
  const previewId = previewPoint?.id || ''

  return (
    <div className="mx-auto flex max-w-full flex-col overflow-x-hidden p-3 md:h-[calc(100dvh-6.5rem)] md:min-h-0 md:p-4">
      <div className="mb-2 flex shrink-0 items-center gap-2">
        <MapIcon className="h-5 w-5 shrink-0 text-primary" />
        <h1 className="text-lg font-bold sm:text-xl">Component Map</h1>
        <p className="hidden min-w-0 truncate text-sm text-muted-foreground md:block">
          Arranged by descriptor similarity
        </p>
      </div>

      <Card className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden py-0">
        <CardHeader className="flex flex-col gap-2 space-y-0 px-3 py-2.5 sm:px-4 md:flex-row md:flex-wrap md:items-center md:gap-x-4 md:gap-y-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <CardTitle className="text-sm sm:text-base">Layout</CardTitle>
            <ToggleGroup
              type="single"
              value={method}
              onValueChange={(value) => {
                if (value === 'umap' || value === 'pca') setMethod(value)
              }}
              variant="outline"
              size="sm"
              className="w-full justify-start sm:w-auto"
            >
              <ToggleGroupItem value="umap" aria-label="UMAP layout" className="flex-1 sm:flex-none">
                UMAP
              </ToggleGroupItem>
              <ToggleGroupItem value="pca" aria-label="PCA layout" className="flex-1 sm:flex-none">
                PCA
              </ToggleGroupItem>
            </ToggleGroup>
            <Select
              value={basis}
              onValueChange={(value) => setBasis(value as ComponentMapBasis)}
            >
              <SelectTrigger className="h-8 w-full sm:w-[200px]">
                <SelectValue placeholder="Feature basis" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="radial_signature">Radial signature</SelectItem>
                <SelectItem value="scalars">Scalar descriptors</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-0 flex-1 md:text-right">
            {(loading || switching) ? (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {switching ? 'Switching layout…' : 'Loading map…'}
              </span>
            ) : (
              <CardDescription
                className={cn(
                  'text-xs',
                  error && 'text-amber-700 dark:text-amber-300',
                )}
              >
                {error
                  ? `${coverage ? `${coverage}. ` : ''}${error}`
                  : [coverage, cacheNote].filter(Boolean).join(' · ') ||
                    'Loading coverage…'}
              </CardDescription>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col px-3 pb-3 pt-0 sm:px-4 sm:pb-4">
          {data && data.points.length > 0 ? (
            <ComponentMapCanvas
              points={data.points}
              method={data.method}
              transitioning={switching}
              onSelect={openPreview}
            />
          ) : (
            <div
              className={cn(
                'flex items-center justify-center rounded-md border border-dashed px-3 text-center text-sm text-muted-foreground',
                CANVAS_HEIGHT_CLASS,
              )}
            >
              {loading
                ? 'Loading map…'
                : data
                  ? coverage
                  : error || 'No points to display'}
            </div>
          )}
        </CardContent>
      </Card>

      <Sheet
        open={previewOpen}
        onOpenChange={(open) => {
          setPreviewOpen(open)
          if (!open) {
            setPreviewCatalog(null)
            setPreviewPoint(null)
            setPreviewLoading(false)
          }
        }}
      >
        <SheetContent side="bottom" className="sm:max-w-none">
          <SheetHeader>
            <SheetTitle className="text-center text-base">Component Preview</SheetTitle>
            <SheetDescription>
              <span className="block text-center text-sm font-semibold">{previewName}</span>
              <span className="block text-center text-xs font-bold">{previewId}</span>
            </SheetDescription>
          </SheetHeader>

          {previewLoading && <ComponentViewerSkeleton message="Loading Geometry..." />}
          {!previewLoading && previewCatalog && (
            <ComponentViewer catalog={previewCatalog} />
          )}

          <SheetFooter className="mt-4 flex flex-col items-center justify-center gap-2 sm:flex-row">
            <Link
              href={`/components/${encodeURIComponent(previewId)}`}
              className="w-full sm:w-[200px]"
            >
              <Button variant="outline" className="h-8 w-full">
                Open Detail Page
              </Button>
            </Link>
            <Link
              href={`/locate-by-id?reference_id=${encodeURIComponent(previewId)}`}
              className="w-full sm:w-[200px]"
            >
              <Button variant="outline" className="h-8 w-full">
                Locate by ID
              </Button>
            </Link>
            <SheetClose asChild className="w-full sm:w-[200px]">
              <Button variant="outline" className="h-8 w-full">
                Close Preview
              </Button>
            </SheetClose>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  )
}
