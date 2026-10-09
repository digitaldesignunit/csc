'use client'

/**
 * The versions waiting for moderation (plan P3, P11 stage 3): one
 * ModerationItemCard each, with what the moderator decides on (size, shape
 * class, capture, and what a correction changes) read from the version
 * itself. Publish, reject (with a reason, in the card) and delete.
 */
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Check, Trash2, X } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import type { PendingSnapshotItem } from '@/generated/SnapshotModels'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'
import {
  isOwnRecord,
  snapshotChanges,
  snapshotFacts,
  snapshotKind,
  submittedLine,
  type SnapshotLike,
} from '@/lib/moderationCard'
import ModerationItemCard, { type CardAction } from './ModerationItemCard'
import { useDetails } from './useDetails'

type Detail = {
  snapshot: (SnapshotLike & { notes?: string | null }) | null
  previous: SnapshotLike | null
  parents: number
  drawn: boolean
}

const get = <T,>(path: string) => backendJson<T>(path).catch(() => null)

async function loadDetail(row: PendingSnapshotItem): Promise<Detail> {
  const [snapshot, identity, previous] = await Promise.all([
    get<SnapshotLike>(`/snapshots/${encodeURIComponent(row._id)}`),
    get<{ parent_identities?: string[] | null }>(`/identities/${encodeURIComponent(row.identity_id)}?expand=none`),
    row.supersedes ? get<SnapshotLike>(`/snapshots/${encodeURIComponent(row.supersedes)}`) : Promise.resolve(null),
  ])
  const parents = identity?.parent_identities ?? []
  let drawn = false
  if (parents.length === 1) {
    const parent = await get<{ remaining?: number | null }>(`/identities/${encodeURIComponent(parents[0])}?expand=none`)
    drawn = typeof parent?.remaining === 'number'
  }
  return { snapshot, previous, parents: parents.length, drawn }
}

export default function SnapshotQueue({ rows, loading, error, onChanged }: {
  rows: PendingSnapshotItem[]
  loading: boolean
  error: string | null
  onChanged: () => void
}) {
  const router = useRouter()
  const { me } = useMe()
  const details = useDetails(rows, (row) => row._id, loadDetail)

  const act = async (row: PendingSnapshotItem, label: string, path: string, body?: unknown) => {
    try {
      await backendJson(path, { method: 'POST', body })
      toast.success(`v${row.version}: ${label}`)
      onChanged()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `${label} failed`)
      throw err
    }
  }

  const actionsOf = (row: PendingSnapshotItem): CardAction[] => [
    {
      key: 'delete', label: `Delete v${row.version}`, icon: Trash2, kind: 'icon',
      confirm: `Delete v${row.version} and its files? This cannot be undone.`,
      run: async () => {
        try {
          await backendJson(`/snapshots/${row._id}`, { method: 'DELETE' })
          toast.success(`v${row.version} deleted`)
          onChanged()
          router.refresh()
        } catch (err) {
          toast.error(err instanceof Error ? err.message : 'Delete failed')
          throw err
        }
      },
    },
    {
      key: 'reject', label: 'Reject', icon: X, kind: 'destructive',
      text: { label: 'Reason (the author sees it)', placeholder: 'Why? The author can turn it back into a draft.', required: true },
      run: (reason) => act(row, 'rejected', `/snapshots/${row._id}/reject`, { reason }),
    },
    {
      key: 'publish', label: 'Publish', icon: Check, kind: 'primary',
      run: () => act(row, 'published', `/snapshots/${row._id}/publish?promote=1`),
    },
  ]

  return (
    <section aria-label="Snapshots waiting for moderation" className="space-y-3">
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : rows.length === 0 ? (
        <Card><CardContent className="p-4 text-sm text-muted-foreground">Nothing is waiting for moderation.</CardContent></Card>
      ) : (
        <ul className="grid gap-3 xl:grid-cols-2">
          {rows.map((row) => {
            const detail = details[row._id]
            const kind = snapshotKind({
              version: row.version, supersedes: row.supersedes,
              parents: detail?.parents ?? 0, drawn: detail?.drawn ?? false,
            })
            const changes = snapshotChanges(detail?.previous, detail?.snapshot)
            return (
              <li key={row._id} className="min-w-0">
                <ModerationItemCard
                  title={`${row.catalog_number != null ? `#${row.catalog_number} ` : ''}${row.name || row.identity_id}`}
                  sub={`v${row.version}`}
                  chips={[
                    { label: kind, variant: 'secondary' },
                    ...(row.dataset ? [{ label: row.dataset }] : []),
                    { label: row.status === 'pending' ? 'Pending' : row.status },
                    ...(isOwnRecord(me?.username, row.added_by_username) ? [{ label: 'Own record' }] : []),
                  ]}
                  openHref={`/components/${encodeURIComponent(row.identity_id)}?snapshots=${encodeURIComponent(row._id)}`}
                  meta={submittedLine('Submitted', row.added_by_username, row.created)}
                  facts={snapshotFacts(row, detail?.snapshot ?? null, changes)}
                  note={detail?.snapshot?.notes}
                  actions={actionsOf(row)}
                />
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
