'use client'

import { useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Loader2, PieChart as PieIcon, BarChart2, LineChart as LineIcon, RefreshCcw } from 'lucide-react'
import {
  ResponsiveContainer,
  PieChart, Pie, Cell,
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line,
} from 'recharts'

type DistItem = { label: string; count: number }

type StatsResponse = {
  total: number
  byType: DistItem[]
  byMaterial: DistItem[]
  byDataset: DistItem[]
  byComplexity: DistItem[]
  byValidated: DistItem[]
  byFragment: DistItem[]
  byAssembly: DistItem[]
  reserved: DistItem[]
  descriptorsKeys: DistItem[]
  createdMonthly: DistItem[]
  bbxX: DistItem[]
}

const COLORS = ['#6366f1', '#22c55e', '#f97316', '#06b6d4', '#eab308', '#ef4444', '#a855f7', '#14b8a6']

export default function AnalyticsPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<StatsResponse | null>(null)

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [materialFilter, setMaterialFilter] = useState<string>('')
  const [datasetFilter, setDatasetFilter] = useState<string>('')
  const [validatedFilter, setValidatedFilter] = useState<string>('1')

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (typeFilter && typeFilter !== 'all') params.set('comptype', typeFilter)
      if (materialFilter) params.set('material', materialFilter)
      if (datasetFilter) params.set('dataset', datasetFilter)
      if (validatedFilter) params.set('validated', validatedFilter)
      params.set('limit_dim', '10')

      const res = await fetch(`/api/backend/components/stats?${params.toString()}`, { cache: 'no-store' })
      if (res.status === 404) {
        // Graceful: render empty stats rather than erroring
        setData({
          total: 0,
          byType: [],
          byMaterial: [],
          byDataset: [],
          byComplexity: [],
          byValidated: [],
          byFragment: [],
          byAssembly: [],
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

  const validatedPct = useMemo(() => {
    if (!data) return 0
    const trueCount = data.byValidated.find(d => d.label === 'true')?.count ?? 0
    return data.total ? Math.round((trueCount / data.total) * 100) : 0
  }, [data])

  return (
    <div className="p-4 md:p-6 lg:p-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-semibold">Analytics</h1>
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
                  <SelectValue placeholder="Type (all)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="sheet">sheet</SelectItem>
                  <SelectItem value="beam">beam</SelectItem>
                  <SelectItem value="slab">slab</SelectItem>
                  <SelectItem value="rubble">rubble</SelectItem>
                  <SelectItem value="column">column</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Input placeholder="Material (exact)" value={materialFilter} onChange={(e) => setMaterialFilter(e.target.value)} />
            </div>
            <div>
              <Input placeholder="Dataset (exact)" value={datasetFilter} onChange={(e) => setDatasetFilter(e.target.value)} />
            </div>
            <div>
              <Select value={validatedFilter} onValueChange={setValidatedFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Validated" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">validated</SelectItem>
                  <SelectItem value="-1">not validated</SelectItem>
                  <SelectItem value="0">any</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <Button onClick={() => load()} disabled={loading}>
              Apply
            </Button>
            <Button variant="ghost" onClick={() => { setTypeFilter('all'); setMaterialFilter(''); setDatasetFilter(''); setValidatedFilter('1'); }}>
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
            {loading && !data ? '…' : (data?.total ?? 0).toLocaleString()}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Validation Rate</CardTitle>
            <CardDescription>Share of validated items</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <div className="text-3xl font-semibold">{validatedPct}%</div>
              <Badge variant="secondary">validated</Badge>
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

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="types">Types</TabsTrigger>
          <TabsTrigger value="materials">Materials</TabsTrigger>
          <TabsTrigger value="datasets">Datasets</TabsTrigger>
          <TabsTrigger value="descriptors">Descriptors</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><PieIcon className="h-4 w-4" /> Type distribution</CardTitle>
              </CardHeader>
              <CardContent className="h-64 min-w-0">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <PieChart>
                    <Pie dataKey="count" data={data?.byType || []} nameKey="label" innerRadius={40} outerRadius={80}>
                      {(data?.byType || []).map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><BarChart2 className="h-4 w-4" /> Complexity</CardTitle>
              </CardHeader>
              <CardContent className="h-64 min-w-0">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <BarChart data={(data?.byComplexity || []).map(d => ({ ...d, label: String(d.label) }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><BarChart2 className="h-4 w-4" /> Validated / Reserved</CardTitle>
              </CardHeader>
              <CardContent className="h-64 grid grid-cols-2 gap-2">
                <div className="h-full min-w-0">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <BarChart data={data?.byValidated || []}>
                      <XAxis dataKey="label" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill="#22c55e" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="h-full min-w-0">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <BarChart data={data?.reserved || []}>
                      <XAxis dataKey="label" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill="#f97316" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="types" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>By Type</CardTitle>
              <CardDescription>Distribution of component types</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <BarChart data={data?.byType || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#06b6d4" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="materials" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Top Materials</CardTitle>
              <CardDescription>Top 10 plus others</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <BarChart data={data?.byMaterial || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#eab308" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="datasets" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Top Datasets</CardTitle>
              <CardDescription>Top 10 plus others</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <BarChart data={data?.byDataset || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#a855f7" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="descriptors" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Descriptor Keys</CardTitle>
              <CardDescription>Frequency of metadata keys</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <BarChart data={data?.descriptorsKeys || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><LineIcon className="h-4 w-4" /> New per month</CardTitle>
              <CardDescription>Created date trend</CardDescription>
            </CardHeader>
            <CardContent className="h-80 min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <LineChart data={data?.createdMonthly || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}


