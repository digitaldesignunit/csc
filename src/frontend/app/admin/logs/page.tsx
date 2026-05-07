'use client'

import { useCallback, useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { Logs, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

type LogKey = 'fastapi_log' | 'previewgen_log' | 'descriptors_simple_log'
type LogState = Record<LogKey, string>

const LOG_ENDPOINTS: Array<{ key: LogKey; title: string; description: string }> = [
  {
    key: 'fastapi_log',
    title: 'FastAPI Log',
    description: 'Backend API runtime log.',
  },
  {
    key: 'previewgen_log',
    title: 'Preview Generator Log',
    description: 'Preview generator cronjob log.',
  },
  {
    key: 'descriptors_simple_log',
    title: 'Simple Descriptors',
    description: 'Simple descriptors cronjob log.',
  },
]

export default function AdminLogsPage() {
  const DEFAULT_LINES = 200
  const MIN_LINES = 1
  const MAX_LINES = 5000
  const { data: session, status } = useSession()
  const router = useRouter()
  const [logs, setLogs] = useState<LogState>({
    fastapi_log: '',
    previewgen_log: '',
    descriptors_simple_log: '',
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lineCount, setLineCount] = useState<number>(DEFAULT_LINES)
  const [activeTab, setActiveTab] = useState<LogKey>('fastapi_log')

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
      router.push('/')
    }
  }, [router, session, status])

  const fetchLog = useCallback(async (key: LogKey, lines: number): Promise<string> => {
    const response = await fetch(`/api/backend/${key}?lines=${encodeURIComponent(lines)}`, { cache: 'no-store' })
    if (!response.ok) {
      throw new Error(`Failed to fetch ${key} (${response.status})`)
    }
    return response.text()
  }, [])

  const fetchAllLogs = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [fastapiLog, previewgenLog, descriptorsSimpleLog] = await Promise.all([
        fetchLog('fastapi_log', lineCount),
        fetchLog('previewgen_log', lineCount),
        fetchLog('descriptors_simple_log', lineCount),
      ])

      setLogs({
        fastapi_log: fastapiLog,
        previewgen_log: previewgenLog,
        descriptors_simple_log: descriptorsSimpleLog,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load logs.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [fetchLog, lineCount])

  useEffect(() => {
    if (session?.user?.role === 'admin' && !session.error) {
      fetchAllLogs()
    }
  }, [fetchAllLogs, session])

  if (status === 'loading') {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      </div>
    )
  }

  if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
    return null
  }

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <Logs className="h-6 w-6 sm:h-8 sm:w-8 text-primary" />
            <h1 className="text-2xl sm:text-3xl font-bold">Admin Logs</h1>
          </div>
          <p className="text-muted-foreground text-sm sm:text-base">
            Live backend logs for monitoring and troubleshooting.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 sm:items-center w-full sm:w-auto">
          <Input
            type="number"
            min={MIN_LINES}
            max={MAX_LINES}
            value={lineCount}
            onChange={(event) => {
              const parsedValue = parseInt(event.target.value, 10)
              if (Number.isNaN(parsedValue)) {
                setLineCount(DEFAULT_LINES)
                return
              }
              setLineCount(Math.min(MAX_LINES, Math.max(MIN_LINES, parsedValue)))
            }}
            className="w-full sm:w-36"
            aria-label="Number of log lines to fetch"
          />
          <Button onClick={fetchAllLogs} disabled={loading} variant="outline" className="w-full sm:w-auto">
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as LogKey)}>
        <TabsList className="gap-1.5">
          <TabsTrigger value="fastapi_log">FastAPI</TabsTrigger>
          <TabsTrigger value="previewgen_log">PreviewGen</TabsTrigger>
          <TabsTrigger value="descriptors_simple_log">Simple Descriptors</TabsTrigger>
        </TabsList>

        {LOG_ENDPOINTS.map(({ key, title, description }) => (
          <TabsContent key={key} value={key} className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>{title}</CardTitle>
                <p className="text-sm text-muted-foreground">
                  {description} Showing last {lineCount} lines.
                </p>
              </CardHeader>
              <CardContent>
                <pre className="bg-muted rounded-md p-4 overflow-auto max-h-[420px] text-xs whitespace-pre-wrap break-words">
                  {logs[key] || (loading ? 'Loading...' : 'No log output available.')}
                </pre>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
