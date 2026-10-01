'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Loader2, PieChart as PieIcon, BarChart2, LineChart as LineIcon, RefreshCcw } from 'lucide-react'
import {
  PieChart, Pie, Cell,
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line,
} from 'recharts'
import { ORIGINAL_FUNCTION_LABELS, vocabLabel } from '@/generated/Vocab'

type DistItem = { label: string; count: number }

type StatsResponse = {
  total: number
  byOriginalFunction: DistItem[]
  byShapeClass: DistItem[]
  byMaterial: DistItem[]
  byDataset: DistItem[]
  byComplexity: DistItem[]
  byStatus: DistItem[]
  byFragment: DistItem[]
  reserved: DistItem[]
  descriptorsKeys: DistItem[]
  createdMonthly: DistItem[]
  bbxX: DistItem[]
}

/** Facet rows with the original function's display label. */
function withFunctionLabels(items: DistItem[] | undefined): DistItem[] {
  return (items || []).map((d) => ({
    ...d,
    label: vocabLabel(ORIGINAL_FUNCTION_LABELS, d.label),
  }))
}

const COLORS = ['#6366f1', '#22c55e', '#f97316', '#06b6d4', '#eab308', '#ef4444', '#a855f7', '#14b8a6']

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

export default function AnalyticsPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<StatsResponse | null>(null)
  const [chartsReady, setChartsReady] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [materialFilter, setMaterialFilter] = useState<string>('')
  const [datasetFilter, setDatasetFilter] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('published')
  const [materialOptions, setMaterialOptions] = useState<{ value: string; label: string }[]>([])
  const [datasetOptions, setDatasetOptions] = useState<string[]>([])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (typeFilter && typeFilter !== 'all') params.set('original_function', typeFilter)
      if (materialFilter) params.set('material', materialFilter)
      if (datasetFilter) params.set('dataset', datasetFilter)
      if (statusFilter) params.set('status', statusFilter)
      params.set('limit_dim', '10')

      const res = await fetch(`/api/backend/identities/stats?${params.toString()}`, { cache: 'no-store' })
      if (res.status === 404) {
        // Graceful: render empty stats rather than erroring
        setData({
          total: 0,
          byOriginalFunction: [],
          byShapeClass: [],
          byMaterial: [],
          byDataset: [],
          byComplexity: [],
          byStatus: [],
          byFragment: [],
          reserved: [],
          descriptorsKeys: [],
          createdMonthly: [],
          bbxX: [],
        })
        setError(null)
        return
      }
      if (!res.ok) throw new Error(`Failed to load stats (${res.status})`)
      const json = (await res.json()) as StatsResponse
      setData(json)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    setChartsReady(true)
  }, [])

  useEffect(() => {
    let cancelled = false
    const loadFilterOptions = async () => {
      try {
        const [materials, datasets] = await Promise.all([
          fetch('/api/backend/materials', { cache: 'no-store' }).then(r => (r.ok ? r.json() : [])),
          fetch('/api/backend/identities/meta/datasets?circulation=all', { cache: 'no-store' }).then(r => (r.ok ? r.json() : [])),
        ])
        if (cancelled) return
        if (Array.isArray(materials)) {
          setMaterialOptions(
            materials
              .filter((m): m is { _id: string; label: string } => typeof m?._id === 'string')
              .map((m) => ({ value: m._id, label: m.label })),
          )
        }
        if (Array.isArray(datasets)) {
          setDatasetOptions(datasets.filter((v): v is string => typeof v === 'string' && v.trim().length > 0))
        }
      } catch {
        if (!cancelled) {
          setMaterialOptions([])
          setDatasetOptions([])
        }
      }
    }
    void loadFilterOptions()
    return () => {
      cancelled = true
    }
  }, [])

  const publishedPct = useMemo(() => {
    if (!data) return 0
    const published = data.byStatus.find(d => d.label === 'published')?.count ?? 0
    return data.total ? Math.round((published / data.total) * 100) : 0
  }, [data])

  return (
    <div className="p-4 md:p-6 lg:p-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <BarChart2 className="h-5 w-5 text-primary" />
            <h1 className="text-xl font-semibold sm:text-2xl">Analytics</h1>
          </div>
          <p className="text-sm text-muted-foreground">Overview and distributions across component attributes</p>
        </div>
        <Button variant="outline" onClick={() => load()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
          <span className="ml-2">Refresh</span>
        </Button>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
          <CardDescription>Filter the population before computing statistics</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Original function (all)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All functions</SelectItem>
                  {Object.entries(ORIGINAL_FUNCTION_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Select value={materialFilter || 'all'} onValueChange={(value) => setMaterialFilter(value === 'all' ? '' : value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Material (any)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any material</SelectItem>
                  {materialOptions.map((material) => (
                    <SelectItem key={material.value} value={material.value}>{material.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Select value={datasetFilter || 'all'} onValueChange={(value) => setDatasetFilter(value === 'all' ? '' : value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Dataset (any)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any dataset</SelectItem>
                  {datasetOptions.map((dataset) => (
                    <SelectItem key={dataset} value={dataset}>{dataset}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="published">published</SelectItem>
                  <SelectItem value="pending">pending</SelectItem>
                  <SelectItem value="any">any status</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <Button onClick={() => load()} disabled={loading}>
              Apply
            </Button>
            <Button variant="ghost" onClick={() => { setTypeFilter('all'); setMaterialFilter(''); setDatasetFilter(''); setStatusFilter('published'); }}>
              Reset
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="mb-6">
          <CardContent className="pt-6 text-destructive text-sm">{error}</CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Total Components</CardTitle>
            <CardDescription>Filtered population size</CardDescription>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {loading && !data ? '...' : (data?.total ?? 0).toLocaleString()}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Published</CardTitle>
            <CardDescription>Share of published current snapshots</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <div className="text-3xl font-semibold">{publishedPct}%</div>
              <Badge variant="secondary">published</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Descriptor Keys</CardTitle>
            <CardDescription>Most common metadata keys</CardDescription>
          </CardHeader>
          <CardContent>
            {data?.descriptorsKeys?.slice(0, 3).map((d) => (
              <div key={d.label} className="flex items-center justify-between text-sm py-1">
                <span className="truncate mr-2">{d.label}</span>
                <span className="text-muted-foreground">{d.count}</span>
              </div>
            )) || <div className="text-sm text-muted-foreground">—</div>}
          </CardContent>
        </Card>
      </div>

      <Separator className="my-6" />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="gap-1.5">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="types">Functions</TabsTrigger>
          <TabsTrigger value="materials">Materials</TabsTrigger>
          <TabsTrigger value="datasets">Datasets</TabsTrigger>
          <TabsTrigger value="descriptors">Descriptors</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>

        {!chartsReady ? (
          <Card className="mt-4">
            <CardContent className="pt-6 text-sm text-muted-foreground">
              Loading charts...
            </CardContent>
          </Card>
        ) : (
          <>
        {activeTab === 'overview' && (
        <TabsContent value="overview" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><PieIcon className="h-4 w-4" /> Original function</CardTitle>
              </CardHeader>
              <CardContent className="h-64 min-w-0">
                <MeasuredChartFrame className="h-full w-full min-w-0">
                  {({ width, height }) => (
                  <PieChart width={width} height={height}>
                    <Pie dataKey="count" data={withFunctionLabels(data?.byOriginalFunction)} nameKey="label" innerRadius={40} outerRadius={80}>
                      {(data?.byOriginalFunction || []).map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                  )}
                </MeasuredChartFrame>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><BarChart2 className="h-4 w-4" /> Complexity</CardTitle>
              </CardHeader>
              <CardContent className="h-64 min-w-0">
                <MeasuredChartFrame className="h-full w-full min-w-0">
                  {({ width, height }) => (
                  <BarChart width={width} height={height} data={(data?.byComplexity || []).map(d => ({ ...d, label: String(d.label) }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" />
                  </BarChart>
                  )}
                </MeasuredChartFrame>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><BarChart2 className="h-4 w-4" /> Status / Reserved</CardTitle>
              </CardHeader>
              <CardContent className="h-64 grid grid-cols-2 gap-2">
                <div className="h-full min-w-0">
                  <MeasuredChartFrame className="h-full w-full min-w-0">
                    {({ width, height }) => (
                    <BarChart width={width} height={height} data={data?.byStatus || []}>
                      <XAxis dataKey="label" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill="#22c55e" />
                    </BarChart>
                    )}
                  </MeasuredChartFrame>
                </div>
                <div className="h-full min-w-0">
                  <MeasuredChartFrame className="h-full w-full min-w-0">
                    {({ width, height }) => (
                    <BarChart width={width} height={height} data={data?.reserved || []}>
                      <XAxis dataKey="label" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill="#f97316" />
                    </BarChart>
                    )}
                  </MeasuredChartFrame>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
        )}

        {activeTab === 'types' && (
        <TabsContent value="types" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>By original function</CardTitle>
              <CardDescription>What the pieces were in their previous life</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <MeasuredChartFrame className="h-full w-full min-w-0">
                {({ width, height }) => (
                <BarChart width={width} height={height} data={withFunctionLabels(data?.byOriginalFunction)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#06b6d4" />
                </BarChart>
                )}
              </MeasuredChartFrame>
            </CardContent>
          </Card>
        </TabsContent>
        )}

        {activeTab === 'materials' && (
        <TabsContent value="materials" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Top Materials</CardTitle>
              <CardDescription>Top 10 plus others</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <MeasuredChartFrame className="h-full w-full min-w-0">
                {({ width, height }) => (
                <BarChart width={width} height={height} data={data?.byMaterial || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#eab308" />
                </BarChart>
                )}
              </MeasuredChartFrame>
            </CardContent>
          </Card>
        </TabsContent>
        )}

        {activeTab === 'datasets' && (
        <TabsContent value="datasets" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Top Datasets</CardTitle>
              <CardDescription>Top 10 plus others</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <MeasuredChartFrame className="h-full w-full min-w-0">
                {({ width, height }) => (
                <BarChart width={width} height={height} data={data?.byDataset || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#a855f7" />
                </BarChart>
                )}
              </MeasuredChartFrame>
            </CardContent>
          </Card>
        </TabsContent>
        )}

        {activeTab === 'descriptors' && (
        <TabsContent value="descriptors" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Descriptor Keys</CardTitle>
              <CardDescription>Frequency of metadata keys</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <MeasuredChartFrame className="h-full w-full min-w-0">
                {({ width, height }) => (
                <BarChart width={width} height={height} data={data?.descriptorsKeys || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#ef4444" />
                </BarChart>
                )}
              </MeasuredChartFrame>
            </CardContent>
          </Card>
        </TabsContent>
        )}

        {activeTab === 'timeline' && (
        <TabsContent value="timeline" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><LineIcon className="h-4 w-4" /> New per month</CardTitle>
              <CardDescription>Created date trend</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <MeasuredChartFrame className="h-full w-full min-w-0">
                {({ width, height }) => (
                <LineChart width={width} height={height} data={data?.createdMonthly || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={2} dot={false} />
                </LineChart>
                )}
              </MeasuredChartFrame>
            </CardContent>
          </Card>
        </TabsContent>
        )}
          </>
        )}
      </Tabs>
    </div>
  )
}


