'use client'

/**
 * The queues of the Moderation page and the counts of My work (plan P3, P6,
 * P11 stage 2): pending snapshots and pending evidence of the datasets the
 * caller moderates, and the records a reviewer can verify. The backend limits
 * each list; these hooks only load them.
 */
import { useCallback, useEffect, useState } from 'react'

import type { EvidenceView } from '@/generated'
import type { PendingSnapshotItem } from '@/generated/SnapshotModels'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'

export function useSnapshotQueue(enabled: boolean) {
  const [rows, setRows] = useState<PendingSnapshotItem[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try {
      setRows(await backendJson<PendingSnapshotItem[]>('/snapshots/pending'))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the queue')
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    if (enabled) void load()
  }, [enabled, load])
  return { rows, loading, error, load }
}

export type VerificationRow = {
  record: EvidenceView
  piece: Pick<CatalogShallowRow, 'catalog_number' | 'name' | 'dataset'> | null
}

/**
 * Records a second person can review (decision 8.12): pending ones, and
 * published ones still `unverified` or only `self_attested`, in the datasets
 * where the caller is a reviewer. A record the caller recorded or performed is
 * left out (four eyes).
 */
export function useVerificationQueue(enabled: boolean) {
  const { me, isAdmin, rolesIn } = useMe()
  const [rows, setRows] = useState<VerificationRow[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!me) return
    try {
      const [pending, unverified, attested] = await Promise.all([
        backendJson<EvidenceView[]>('/evidence?status=pending&limit=500'),
        backendJson<EvidenceView[]>('/evidence?status=published&verification=unverified&limit=500'),
        backendJson<EvidenceView[]>('/evidence?status=published&verification=self_attested&limit=500'),
      ])
      const records = [...pending, ...unverified, ...attested].filter((r) => 'method' in r)
      const pieces = new Map<string, VerificationRow['piece']>()
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
    if (enabled) void load()
  }, [enabled, load])
  return { rows, loading, error, load }
}
