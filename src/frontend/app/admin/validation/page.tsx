'use client'

import { Suspense, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import EvidenceQueue, { useEvidenceQueue } from '@/components/moderation/EvidenceQueue'
import SnapshotQueue from '@/components/moderation/SnapshotQueue'
import VerificationQueue from '@/components/moderation/VerificationQueue'
import Help from '@/components/ui/help'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useMe } from '@/lib/me'
import { useSnapshotQueue, useVerificationQueue } from '@/lib/moderationQueues'

type Tab = 'snapshots' | 'evidence' | 'verification'

const TAB_HELP: Record<Tab, string> = {
  snapshots:
    'Versions of components waiting in the datasets you moderate, oldest first. Publishing makes a version the current state of its component; a rejection goes back to its author with your reason.',
  evidence:
    'Records waiting in the datasets you moderate, oldest first. Publishing freezes a record and updates the properties of its component; a rejection goes back to its author with your reason.',
  verification:
    'Records in your datasets that nobody but the recorder has confirmed. A review needs a second person: records you recorded or performed are not listed. Review a record in its card or open it first.',
}

/**
 * Moderation (plan P11 stage 2, decision 8.118 S2): one inbox with the tabs
 * Snapshots, Evidence and Verification, a count on each, the explanations
 * behind a "?", one line when empty, and a dataset filter when the caller
 * works in more than one.
 */
function ModerationPage() {
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  const { moderatesAny, reviewsAny } = useMe()
  const snapshots = useSnapshotQueue(moderatesAny)
  const evidence = useEvidenceQueue(moderatesAny)
  const verification = useVerificationQueue(reviewsAny)

  const tabs = useMemo(() => {
    const out: { id: Tab; label: string; count: number }[] = []
    if (moderatesAny) {
      out.push({ id: 'snapshots', label: 'Snapshots', count: snapshots.rows.length })
      out.push({ id: 'evidence', label: 'Evidence', count: evidence.rows.length })
    }
    if (reviewsAny) out.push({ id: 'verification', label: 'Verification', count: verification.rows.length })
    return out
  }, [moderatesAny, reviewsAny, snapshots.rows.length, evidence.rows.length, verification.rows.length])

  const requested = search.get('tab')
  const tab: Tab = (tabs.find((t) => t.id === requested) ?? tabs[0])?.id ?? 'snapshots'
  const dataset = search.get('dataset') ?? ''

  const datasets = useMemo(() => {
    const slugs = new Set<string>()
    for (const r of snapshots.rows) if (r.dataset) slugs.add(r.dataset)
    for (const r of evidence.rows) if (r.dataset) slugs.add(r.dataset)
    for (const r of verification.rows) if (r.piece?.dataset) slugs.add(r.piece.dataset)
    return [...slugs].sort()
  }, [snapshots.rows, evidence.rows, verification.rows])

  const go = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(search.toString())
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    const text = next.toString()
    router.replace(text ? `${pathname}?${text}` : pathname, { scroll: false })
  }

  const keep = (value: string | null | undefined) => !dataset || value === dataset
  const snapshotRows = snapshots.rows.filter((r) => keep(r.dataset))
  const evidenceRows = evidence.rows.filter((r) => keep(r.dataset))
  const verificationRows = verification.rows.filter((r) => keep(r.piece?.dataset))
  const reload = () => {
    void snapshots.load()
    void evidence.load()
    void verification.load()
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 sm:p-6 xl:max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold sm:text-2xl">Moderation</h1>
        {datasets.length > 1 && (
          <select
            aria-label="Dataset"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={dataset}
            onChange={(e) => go({ dataset: e.target.value || null })}
          >
            <option value="">All datasets</option>
            {datasets.map((slug) => (
              <option key={slug} value={slug}>{slug}</option>
            ))}
          </select>
        )}
      </div>

      <div className="flex items-center gap-1">
        <Tabs value={tab} onValueChange={(value) => go({ tab: value })}>
          <TabsList>
            {tabs.map((t) => (
              <TabsTrigger key={t.id} value={t.id}>
                {t.label} ({t.count})
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {tabs.length > 0 && <Help label={tabs.find((t) => t.id === tab)?.label ?? ''} text={TAB_HELP[tab]} />}
      </div>

      {tab === 'snapshots' && (
        <SnapshotQueue rows={snapshotRows} loading={snapshots.loading} error={snapshots.error} onChanged={reload} />
      )}

      {tab === 'evidence' && (
        <EvidenceQueue rows={evidenceRows} loading={evidence.loading} error={evidence.error} onChanged={reload} />
      )}

      {tab === 'verification' && (
        <VerificationQueue rows={verificationRows} loading={verification.loading} error={verification.error} onChanged={reload} />
      )}
    </div>
  )
}

export default function ModerationQueuePage() {
  return (
    <Suspense fallback={null}>
      <ModerationPage />
    </Suspense>
  )
}
