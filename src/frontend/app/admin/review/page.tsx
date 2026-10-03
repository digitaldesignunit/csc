'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ShieldCheck } from 'lucide-react'

import EvidenceCard from '@/components/evidence/EvidenceCard'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { EvidenceView } from '@/generated'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { backendJson } from '@/lib/backend'
import { UPLOAD_HELP } from '@/lib/evidence/api'
import { useRegistry } from '@/lib/evidence/useRegistry'
import { useMe } from '@/lib/me'

type Row = { record: EvidenceView; piece: Pick<CatalogShallowRow, 'catalog_number' | 'name' | 'dataset'> | null }

/**
 * Verification queue (plan P6, decision 8.12): records a second person can
 * review --- pending ones, and published ones still `unverified` or only
 * `self_attested` --- in the datasets where the caller is a reviewer. A
 * record the caller recorded or performed is left out (four eyes).
 */
export default function ReviewQueuePage() {
  const router = useRouter()
  const { me, loading: meLoading, reviewsAny, isAdmin, rolesIn } = useMe()
  const { registry } = useRegistry()
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!meLoading && me && !reviewsAny) router.push('/')
  }, [me, meLoading, reviewsAny, router])

  const load = useCallback(async () => {
    if (!me) return
    try {
      const [pending, unverified, attested] = await Promise.all([
        backendJson<EvidenceView[]>('/evidence?status=pending&limit=500'),
        backendJson<EvidenceView[]>('/evidence?status=published&verification=unverified&limit=500'),
        backendJson<EvidenceView[]>('/evidence?status=published&verification=self_attested&limit=500'),
      ])
      const records = [...pending, ...unverified, ...attested].filter((r) => 'method' in r)
      const pieces = new Map<string, Row['piece']>()
      for (const id of new Set(records.map((r) => r.identity_id))) {
        pieces.set(id, await backendJson<CatalogShallowRow>(`/identities/${encodeURIComponent(id)}`).catch(() => null))
      }
      const mine = (r: EvidenceView) => r.recorded_by_user_id === me._id
        || (r.performed_by ?? []).some((a) => a.user_id === me._id)
      setRows(records
        .map((record) => ({ record, piece: pieces.get(record.identity_id) ?? null }))
        .filter(({ record, piece }) => piece && (isAdmin || rolesIn(piece.dataset).includes('reviewer')) && !mine(record)))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the queue')
    } finally {
      setLoading(false)
    }
  }, [me, isAdmin, rolesIn])

  useEffect(() => {
    if (reviewsAny) void load()
  }, [reviewsAny, load])

  return (
    <div className="container mx-auto max-w-3xl space-y-4 p-6">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold sm:text-2xl">Verification queue</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Records in your datasets that nobody but the recorder has confirmed. Reviewing needs a second
        person: records you recorded or performed are not listed. Open a record to review it; for an
        accredited result, note what you checked and look up the accreditation.
      </p>
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : rows.length === 0 ? (
        <Card><CardContent className="p-6 text-sm text-muted-foreground">Nothing is waiting for a review.</CardContent></Card>
      ) : (
        <ul className="space-y-3">
          {rows.map(({ record, piece }) => (
            <li key={record._id} className="space-y-1">
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <Link href={`/components/${encodeURIComponent(record.identity_id)}`} className="font-medium underline-offset-4 hover:underline">
                  #{piece?.catalog_number} {piece?.name}
                </Link>
                <Badge variant="outline" className="text-[10px]">{piece?.dataset}</Badge>
              </p>
              <EvidenceCard record={record} dataset={piece?.dataset} onChanged={() => void load()}
                uploadHelp={registry?.help(...UPLOAD_HELP)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
