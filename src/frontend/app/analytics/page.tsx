'use client'

import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2 } from 'lucide-react'
import {
  PieChart, Pie, Cell,
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line,
} from 'recharts'

import CatalogFilterBar from '@/components/catalog/CatalogFilterBar'
import {
  EMPTY_STATS,
  circulationItems,
  functionItems,
  materialItems,
  statsQuery,
  summaryLine,
  topN,
  type StatsResponse,
} from '@/lib/analytics'
import { useMaterials } from '@/lib/lineage'

const COLORS = ['#2563eb', '#d6146f', '#16a34a', '#f59e0b', '#7c3aed', '#0891b2', '#dc2626', '#65a30d']

function MeasuredChartFrame({
  className,
  children,
}: {
  className?: string
  children: (size: { width: number; height: number }) => React.ReactNode
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const element = containerRef.current
    if (!element) return

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      const nextWidth = Math.floor(entry.contentRect.width)
      const nextHeight = Math.floor(entry.contentRect.height)
      setSize((prev) => (
        prev.width === nextWidth && prev.height === nextHeight
          ? prev
          : { width: nextWidth, height: nextHeight }
      ))
    })

    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={containerRef} className={className}>
      {size.width > 0 && size.height > 0 ? children(size) : null}
    </div>
  )
}

type Items = { label: string; count: number }[]

function BarCard({ title, description, items, fill, angled = false, tall = false }: {
  title: string
  description?: string
  items: Items
  fill: string
  angled?: boolean
  tall?: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className={tall ? 'h-80 min-w-0' : 'h-64 min-w-0'}>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing to show.</p>
        ) : (
          <MeasuredChartFrame className="h-full w-full min-w-0">
            {({ width, height }) => (
              <BarChart width={width} height={height} data={items}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" interval={0} {...(angled ? { angle: -25, textAnchor: 'end' as const, height: 60 } : {})} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill={fill} />
              </BarChart>
            )}
          </MeasuredChartFrame>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Analytics (plan P11 stage 2, decision 8.118 C-3): the filter bar of Browse,
 * applied on change and kept in the URL; one line instead of the tiles; the
 * Overview opens with the function and material charts and the Circulation
 * chart; the descriptor keys are in the Descriptors tab. An anonymous visitor
 * sees the public tier.
 */
function Analytics() {
  const search = useSearchParams()
  const query = statsQuery(search)
  const [data, setData] = useState<StatsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('overview')
  const materials = useMaterials(true)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setLoading(true)
    ;(async () => {
      try {
        const res = await fetch(`/api/backend/identities/stats?${query}`, {
          cache: 'no-store',
          credentials: 'include',
          signal: controller.signal,
        })
        if (cancelled) return
        if (res.status === 404) {
          setData(EMPTY_STATS)
          setError(null)
        } else if (!res.ok) {
          throw new Error(`Failed to load stats (${res.status})`)
        } else {
          setData((await res.json()) as StatsResponse)
          setError(null)
        }
      } catch (e: unknown) {
        if (cancelled || (e as Error).name === 'AbortError') return
        setError((e as Error).message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [query])

  const materialLabel = useMemo(() => {
    const byId = new Map(materials.map((m) => [m._id, m.label]))
    return (id: string) => byId.get(id) ?? id
  }, [materials])

  const functions = useMemo(() => functionItems(data?.byOriginalFunction), [data])
  const materialRows = useMemo(
    () => materialItems(topN(data?.byMaterial), materialLabel),
    [data, materialLabel],
  )
  const datasetRows = useMemo(() => topN(data?.byDataset), [data])
  const circulation = useMemo(() => circulationItems(data?.byCirculation), [data])

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-3 p-3 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold sm:text-2xl">Analytics</h1>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground" aria-live="polite">
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
          {data ? summaryLine(data) : ''}
        </p>
      </div>

      <CatalogFilterBar circulation="all" withSize={false} />

      {error && (
        <Card>
          <CardContent className="pt-6 text-sm text-destructive" role="alert">{error}</CardContent>
        </Card>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="max-w-full justify-start gap-1.5 overflow-x-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="types">Functions</TabsTrigger>
          <TabsTrigger value="materials">Materials</TabsTrigger>
          <TabsTrigger value="datasets">Datasets</TabsTrigger>
          <TabsTrigger value="descriptors">Descriptors</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>

        {data && activeTab === 'overview' && (
          <TabsContent value="overview" className="mt-3">
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle className="text-base">Original function</CardTitle></CardHeader>
                <CardContent className="h-64 min-w-0">
                  {functions.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nothing to show.</p>
                  ) : (
                    <MeasuredChartFrame className="h-full w-full min-w-0">
                      {({ width, height }) => (
                        <PieChart width={width} height={height}>
                          <Pie dataKey="count" data={functions} nameKey="label" innerRadius={40} outerRadius={80} label={(d) => String(d.name)}>
                            {functions.map((_, i) => (
                              <Cell key={i} fill={COLORS[i % COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip />
                        </PieChart>
                      )}
                    </MeasuredChartFrame>
                  )}
                </CardContent>
              </Card>
              <BarCard title="Material" description="The ten most frequent, the rest as others" items={materialRows} fill="#2563eb" angled />
              <BarCard title="Circulation" description="Where the pieces are: in place, not in place, out of circulation" items={circulation} fill="#d6146f" />
              <BarCard
                title="Complexity"
                items={(data?.byComplexity ?? []).map((d) => ({ ...d, label: String(d.label) }))}
                fill="#16a34a"
              />
            </div>
          </TabsContent>
        )}

        {data && activeTab === 'types' && (
          <TabsContent value="types" className="mt-3">
            <BarCard title="By original function" description="What the pieces were in their previous life" items={functions} fill="#0891b2" tall />
          </TabsContent>
        )}

        {data && activeTab === 'materials' && (
          <TabsContent value="materials" className="mt-3">
            <BarCard title="Top materials" description="Top 10 plus others" items={materialRows} fill="#f59e0b" angled tall />
          </TabsContent>
        )}

        {data && activeTab === 'datasets' && (
          <TabsContent value="datasets" className="mt-3">
            <BarCard title="Top datasets" description="Top 10 plus others" items={datasetRows} fill="#7c3aed" angled tall />
          </TabsContent>
        )}

        {data && activeTab === 'descriptors' && (
          <TabsContent value="descriptors" className="mt-3">
            <BarCard
              title="Descriptor keys"
              description="How many components carry each descriptor"
              items={topN(data?.descriptorsKeys, 12)}
              fill="#dc2626"
              angled
              tall
            />
          </TabsContent>
        )}

        {data && activeTab === 'timeline' && (
          <TabsContent value="timeline" className="mt-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">New per month</CardTitle>
                <CardDescription>Created date trend</CardDescription>
              </CardHeader>
              <CardContent className="h-80 min-w-0">
                <MeasuredChartFrame className="h-full w-full min-w-0">
                  {({ width, height }) => (
                    <LineChart width={width} height={height} data={data?.createdMonthly ?? []}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" />
                      <YAxis />
                      <Tooltip />
                      <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot={false} />
                    </LineChart>
                  )}
                </MeasuredChartFrame>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}

export default function AnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <Analytics />
    </Suspense>
  )
}
