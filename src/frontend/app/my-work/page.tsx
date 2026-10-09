'use client'

import { Suspense, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { Check, Send, X } from 'lucide-react'

import ChipView from '@/components/common/ChipView'
import ComponentPreviewImage from '@/components/components/ComponentPreviewImage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import type { EvidenceView } from '@/generated'
import type { MySnapshotItem } from '@/generated/SnapshotModels'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { backendJson } from '@/lib/backend'
import { evidenceAction } from '@/lib/evidence/api'
import { cardLine, rowName, rowNumber } from '@/lib/browse'
import { statusChip } from '@/lib/componentDetail'
import { useMaterials } from '@/lib/lineage'
import { useMe } from '@/lib/me'
import { useSnapshotQueue, useVerificationQueue } from '@/lib/moderationQueues'
import {
  isSubmittable,
  mergeMyRecords,
  recordKey,
  submitRecords,
  submittableKeys,
  waitingLines,
  type MyRecord,
  type Piece,
  type SubmitResult,
} from '@/lib/myWork'
import { formatDay } from '@/lib/componentDetail'
import { useRecentComponents, useRecentUserId } from '@/lib/recentComponents'
import { useEvidenceQueue } from '@/components/moderation/EvidenceQueue'

const UNFINISHED = ['draft', 'pending', 'rejected'] as const

/**
 * My work (plan P11 stage 2, decision 8.118 Q4): what is waiting for me, my
 * reservations, my drafts, pending and rejected records --- snapshots and
 * evidence together --- and the components I opened last. It replaces the
 * Dashboard and Reserved. Own drafts are submitted together (decision 8.127):
 * a robot scan or a layout run from Grasshopper creates many at once.
 */
function MyWork() {
  const { me, moderatesAny, reviewsAny } = useMe()
  const snapshotQueue = useSnapshotQueue(moderatesAny)
  const evidenceQueue = useEvidenceQueue(moderatesAny)
  const verificationQueue = useVerificationQueue(reviewsAny)
  const waiting = waitingLines({
    snapshots: snapshotQueue.rows.length,
    evidence: evidenceQueue.rows.length,
    verification: verificationQueue.rows.length,
  })
  const waitingLoaded = !snapshotQueue.loading && !evidenceQueue.loading && !verificationQueue.loading

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-3 sm:p-6">
      <h1 className="text-xl font-bold sm:text-2xl">My work</h1>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
        <div className="min-w-0 space-y-4">
          {(moderatesAny || reviewsAny) && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base">Waiting for you</CardTitle></CardHeader>
              <CardContent className="text-sm">
                {!waitingLoaded ? (
                  <p className="text-muted-foreground">Loading...</p>
                ) : waiting.length === 0 ? (
                  <p className="text-muted-foreground">Nothing is waiting for you.</p>
                ) : (
                  <ul className="space-y-1">
                    {waiting.map((line) => (
                      <li key={line.key}>
                        <Link
                          href={`/admin/validation?tab=${line.tab}`}
                          className="font-medium text-primary underline-offset-4 hover:underline"
                        >
                          {line.text}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          )}
          <Reservations userId={me?._id ?? null} />
        </div>
        <div className="min-w-0 space-y-4">
          <MyRecords enabled={Boolean(me)} />
          <Recent />
        </div>
      </div>
    </div>
  )
}

function Reservations({ userId }: { userId: string | null }) {
  const [rows, setRows] = useState<CatalogShallowRow[] | null>(null)
  const materials = useMaterials(true)
  const load = useCallback(async () => {
    if (!userId) return
    try {
      const data = await backendJson<{ components?: CatalogShallowRow[] }>(
        `/identities/reserved/${encodeURIComponent(userId)}`,
      )
      setRows(Array.isArray(data.components) ? data.components : [])
    } catch {
      setRows([])
    }
  }, [userId])
  useEffect(() => {
    void load()
  }, [load])

  const release = async (id: string) => {
    try {
      await backendJson(`/identities/${encodeURIComponent(id)}/reserve`, { method: 'DELETE' })
      setRows((prev) => (prev ?? []).filter((r) => r._id !== id))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not release the component')
    }
  }
  const materialLabel = (id: string | null | undefined) => materials.find((m) => m._id === id)?.label ?? id ?? ''

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">My reservations{rows ? ` (${rows.length})` : ''}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        {rows === null ? (
          <p className="text-muted-foreground">Loading...</p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground">You have not reserved a component.</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((row) => (
              <li key={row._id} className="flex items-center gap-2.5">
                <Link href={`/components/${row._id}`} className="flex min-w-0 flex-1 items-center gap-2.5">
                  <span className="h-11 w-11 shrink-0 overflow-hidden rounded-md border bg-white">
                    <ComponentPreviewImage
                      snapshot_id={row.has_preview === false ? null : row.current_snapshot_id}
                      alt=""
                      width={44}
                      height={44}
                      maxHeight={44}
                      className="h-full w-full"
                    />
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-baseline gap-1.5">
                      <span className="truncate font-medium">{rowName(row)}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{rowNumber(row)}</span>
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {cardLine(row, materialLabel(row.material))}
                    </span>
                  </span>
                </Link>
                <Button type="button" variant="outline" size="sm" onClick={() => void release(row._id)}>
                  Release
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

/** Submits one own draft; the new status. The server refuses with its reason. */
async function submitOwn(row: MyRecord): Promise<string> {
  if (row.kind === 'snapshot') {
    const snapshot = await backendJson<{ status?: string }>(
      `/snapshots/${encodeURIComponent(row.id)}/submit`, { method: 'POST' })
    return snapshot?.status ?? 'pending'
  }
  const record = await evidenceAction(row.id, 'submit')
  return record?.status ?? 'pending'
}

function MyRecords({ enabled }: { enabled: boolean }) {
  const [rows, setRows] = useState<MyRecord[] | null>(null)
  const [chosen, setChosen] = useState<Set<string>>(() => new Set())
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<SubmitResult[]>([])

  const load = useCallback(async (cancelled: () => boolean = () => false) => {
    try {
      const [snapshots, ...evidenceLists] = await Promise.all([
        backendJson<MySnapshotItem[]>(`/snapshots?mine=1&status=${UNFINISHED.join(',')}`),
        ...UNFINISHED.map((status) =>
          backendJson<EvidenceView[]>(`/evidence?recorded_by=me&status=${status}&order=newest&limit=50`),
        ),
      ])
      const evidence = evidenceLists.flat().filter((r) => 'method' in r)
      const pieces = new Map<string, Piece | null>()
      for (const id of new Set(evidence.map((r) => r.identity_id))) {
        // the identity first: a piece that is not published yet has no catalog
        // row (a request for it would be a 404), its number and dataset will do
        const identity = await backendJson<CatalogShallowRow>(
          `/identities/${encodeURIComponent(id)}?expand=none`,
        ).catch(() => null)
        pieces.set(
          id,
          identity?.current_snapshot_id
            ? await backendJson<CatalogShallowRow>(`/identities/${encodeURIComponent(id)}`).catch(() => identity)
            : identity,
        )
      }
      if (!cancelled()) setRows(mergeMyRecords(snapshots, evidence, pieces))
    } catch {
      if (!cancelled()) setRows([])
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    void load(() => cancelled)
    return () => {
      cancelled = true
    }
  }, [enabled, load])

  const drafts = rows ? submittableKeys(rows) : []
  const selected = drafts.filter((key) => chosen.has(key)).length
  const toggle = (key: string) =>
    setChosen((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const submitChosen = async () => {
    if (!rows || selected === 0) return
    setBusy(true)
    setResults([])
    try {
      const done = await submitRecords(rows, chosen, submitOwn)
      setResults(done)
      const sent = done.filter((r) => r.ok).length
      const refused = done.length - sent
      if (sent > 0) toast.success(`${sent} submitted: a moderator of the dataset publishes them`)
      if (refused > 0) toast.error(`${refused} could not be submitted, see the list`)
      setChosen(new Set())
      await load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">My drafts, pending and rejected{rows ? ` (${rows.length})` : ''}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        {rows === null ? (
          <p className="text-muted-foreground">Loading...</p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground">No drafts, pending or rejected records.</p>
        ) : (
          <>
            {drafts.length > 0 && (
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" size="sm" disabled={busy}
                  onClick={() => setChosen(new Set(drafts))}>
                  Select all drafts
                </Button>
                <Button type="button" variant="ghost" size="sm" disabled={busy || selected === 0}
                  onClick={() => setChosen(new Set())}>
                  None
                </Button>
                <Button type="button" size="sm" disabled={busy || selected === 0} onClick={() => void submitChosen()}>
                  <Send className="mr-1 h-3.5 w-3.5" />
                  Submit selected ({selected})
                </Button>
              </div>
            )}
            {results.length > 0 && (
              <ul className="mb-2 space-y-1 rounded-md border border-border p-2 text-xs" aria-label="Result of the submit">
                {results.map((result) => (
                  <li key={result.key} className="flex items-start gap-1.5">
                    {result.ok
                      ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                      : <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />}
                    <span className={result.ok ? undefined : 'text-destructive'}>
                      {result.title}{result.piece ? ` (${result.piece})` : ''}: {result.ok ? 'submitted' : result.message}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <ul className="divide-y">
              {rows.map((row) => {
                const key = recordKey(row)
                return (
                  <li key={key} className="flex items-start gap-2 py-2 first:pt-0 last:pb-0">
                    <Checkbox
                      className="mt-1"
                      checked={chosen.has(key) && isSubmittable(row)}
                      disabled={busy || !isSubmittable(row)}
                      onCheckedChange={() => toggle(key)}
                      aria-label={`Select ${row.title}${row.piece ? `, ${row.piece}` : ''}`}
                    />
                    <div className="min-w-0 flex-1">
                      <Link href={row.href} className="block space-y-0.5 hover:underline">
                        <span className="flex flex-wrap items-center gap-1.5">
                          <ChipView chip={statusChip({ status: row.status })} />
                          <span className="font-medium">{row.title}</span>
                          <span className="text-xs text-muted-foreground">{formatDay(row.at)}</span>
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {[row.piece, row.dataset].filter(Boolean).join(' / ')}
                        </span>
                      </Link>
                      {row.status === 'rejected' && row.reason && (
                        <p className="mt-0.5 text-xs text-red-800 dark:text-red-300">Reason: {row.reason}</p>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Recent() {
  const { items } = useRecentComponents(useRecentUserId())
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Recent components</CardTitle></CardHeader>
      <CardContent className="text-sm">
        {items.length === 0 ? (
          <p className="text-muted-foreground">Components you open appear here.</p>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/components/${encodeURIComponent(item.id)}`}
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export default function MyWorkPage() {
  return (
    <Suspense fallback={null}>
      <MyWork />
    </Suspense>
  )
}
