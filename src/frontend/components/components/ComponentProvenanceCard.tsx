'use client'

import { useEffect, useState, type ReactNode } from 'react'
import dynamic from 'next/dynamic'
import { GitFork, Loader2, Pencil } from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import {
  CONNECTION_TYPE_LABELS,
  CONSTRUCTION_METHOD_LABELS,
  DGNB_CLASS_LABELS,
  ORIGIN_KIND_LABELS,
  vocabLabel,
} from '@/generated/Vocab'
import type { CatalogShallowRow, ProvenanceGraph } from '@/generated/catalogExtras'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import InheritedMark from '@/components/lineage/InheritedMark'
import ProvenanceEditDialog from '@/components/lineage/ProvenanceEditDialog'
import { useMe } from '@/lib/me'
import ComponentLineageIdentityBadges from './ComponentLineageIdentityBadges'
import {
  exitSummary,
  formatDateAtPrecision,
  isOutOfCirculation,
  isNonEmptyString,
  parentIdentityIds,
} from './componentDetailShared'

const ComponentProvenanceGraph = dynamic(
  () => import('./ComponentProvenanceGraph'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    ),
  },
)

function MetadataRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/60 py-1.5 last:border-0">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <div className="min-w-0 text-right text-xs font-medium text-foreground">{children}</div>
    </div>
  )
}

function ValueChip({
  children,
  className = '',
  title,
}: {
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={`inline-block max-w-full truncate rounded-md bg-secondary/25 px-2 py-0.5 text-xs font-semibold text-foreground ${className}`}
    >
      {children}
    </span>
  )
}

type LineageStatus = 'active' | 'exited'

const formatDate = formatDateAtPrecision

type ComponentProvenanceCardProps = {
  catalog: CatalogComponent
  childIdentities?: CatalogShallowRow[]
}

export default function ComponentProvenanceCard({
  catalog,
  childIdentities = [],
}: ComponentProvenanceCardProps) {
  const { identity } = catalog
  const identityId = String(identity._id ?? '')
  const parentIds = parentIdentityIds(identity)
  const origin = identity.origin
  const { me, moderates } = useMe()
  const [editOpen, setEditOpen] = useState(false)
  // moderator(D); the creator while it is unpublished (8.9) --- the backend decides
  const canEdit = !!me && (moderates(identity.dataset)
    || (!identity.current_snapshot_id && me._id === identity.created_by_user_id))
  const [parentStatuses, setParentStatuses] = useState<Record<string, LineageStatus>>({})
  const [graphOpen, setGraphOpen] = useState(false)
  const [graph, setGraph] = useState<ProvenanceGraph | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphError, setGraphError] = useState<string | null>(null)

  const childBadges = childIdentities.flatMap((row) => {
    const id = String(row._id ?? '').trim()
    if (!id) {
      return []
    }
    return [
      {
        id,
        status: isOutOfCirculation(row) ? ('exited' as const) : ('active' as const),
      },
    ]
  })

  useEffect(() => {
    if (parentIds.length === 0) {
      setParentStatuses({})
      return
    }

    let cancelled = false
    const resolveParentStatuses = async () => {
      const entries = await Promise.all(
        parentIds.map(async (parentId) => {
          try {
            const res = await fetch(
              `/api/backend/identities/${encodeURIComponent(parentId)}?expand=shallow`,
              { credentials: 'include', cache: 'no-store' },
            )
            if (!res.ok) {
              return null
            }
            const row = (await res.json()) as CatalogShallowRow
            return [
              parentId,
              isOutOfCirculation(row) ? 'exited' : 'active',
            ] as const
          } catch (error) {
            console.error('Failed to resolve parent component status:', error)
            return null
          }
        }),
      )
      if (cancelled) {
        return
      }
      const next: Record<string, LineageStatus> = {}
      for (const entry of entries) {
        if (entry) {
          next[entry[0]] = entry[1]
        }
      }
      setParentStatuses(next)
    }

    resolveParentStatuses()
    return () => {
      cancelled = true
    }
  }, [parentIds.join('|')])

  useEffect(() => {
    if (!graphOpen || !identityId) {
      return
    }

    let cancelled = false
    const loadGraph = async () => {
      setGraphLoading(true)
      setGraphError(null)
      try {
        const res = await fetch(
          `/api/backend/identities/${encodeURIComponent(identityId)}/provenance`,
          { credentials: 'include' },
        )
        if (!res.ok) {
          throw new Error(`Provenance request failed (${res.status})`)
        }
        const body = (await res.json()) as ProvenanceGraph
        if (!cancelled) {
          setGraph(body)
        }
      } catch (error) {
        console.error('Failed to load provenance graph:', error)
        if (!cancelled) {
          setGraph(null)
          setGraphError('Could not load the lineage graph.')
        }
      } finally {
        if (!cancelled) {
          setGraphLoading(false)
        }
      }
    }

    void loadGraph()
    return () => {
      cancelled = true
    }
  }, [graphOpen, identityId])

  return (
    <>
      <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <GitFork className="h-4 w-4" />
            Provenance
          </h3>
          {canEdit && (
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-4 hover:underline"
            >
              <Pencil className="h-3 w-3" />
              Edit
            </button>
          )}
        </div>
        <MetadataRow label="Manufactured">
          {isNonEmptyString(identity.manufactured_at) ? (
            <ValueChip>
              {formatDate(identity.manufactured_at, identity.manufactured_precision)}
            </ValueChip>
          ) : (
            <span className="rounded-md bg-muted/30 px-2 py-0.5 text-xs italic text-muted-foreground">
              Unknown
            </span>
          )}
          <InheritedMark identity={identity} unit="manufactured_at" />
        </MetadataRow>
        {isNonEmptyString(identity.manufacturer) && (
          <MetadataRow label="Manufacturer">
            <ValueChip>{identity.manufacturer}</ValueChip>
            <InheritedMark identity={identity} unit="manufacturer" />
          </MetadataRow>
        )}
        {identity.material_separability && (
          <MetadataRow label="Material separability">
            <ValueChip title={identity.material_separability.note ?? undefined}>
              {vocabLabel(DGNB_CLASS_LABELS, identity.material_separability.class)}
            </ValueChip>
            <InheritedMark identity={identity} unit="material_separability" />
          </MetadataRow>
        )}
        {isNonEmptyString(identity.connection_features) && (
          <MetadataRow label="Connection features">
            <ValueChip className="max-w-[12rem] whitespace-normal break-words">
              {identity.connection_features}
            </ValueChip>
          </MetadataRow>
        )}
        <MetadataRow label="Origin">
          <ValueChip>
            {vocabLabel(ORIGIN_KIND_LABELS, origin?.kind ?? 'unknown')}
          </ValueChip>
          <InheritedMark identity={identity} unit="origin" />
        </MetadataRow>
        {isNonEmptyString(origin?.at) && (
          <MetadataRow label="Left previous context">
            <ValueChip>{formatDate(String(origin?.at), origin?.at_precision)}</ValueChip>
          </MetadataRow>
        )}
        {(origin?.place?.name || origin?.place?.address) && (
          <MetadataRow label="Place">
            <ValueChip className="max-w-[12rem] whitespace-normal break-words">
              {[origin?.place?.name, origin?.place?.address]
                .filter(Boolean)
                .join(', ')}
            </ValueChip>
          </MetadataRow>
        )}
        {origin?.construction_work && (
          <MetadataRow label="Construction work">
            <ValueChip className="max-w-[12rem] whitespace-normal break-words">
              {[
                origin.construction_work.name,
                origin.construction_work.year_built ? `built ${origin.construction_work.year_built}` : null,
                origin.construction_work.construction_method
                  ? vocabLabel(CONSTRUCTION_METHOD_LABELS, origin.construction_work.construction_method).toLowerCase()
                  : null,
              ].filter(Boolean).join(', ')}
            </ValueChip>
          </MetadataRow>
        )}
        {isNonEmptyString(origin?.position_in_work) && (
          <MetadataRow label="Position in the works">
            <ValueChip className="max-w-[12rem] whitespace-normal break-words">
              {origin?.position_in_work}
            </ValueChip>
          </MetadataRow>
        )}
        {(origin?.connection_types ?? []).length > 0 && (
          <MetadataRow label="Connections">
            <ValueChip className="max-w-[12rem] whitespace-normal break-words">
              {(origin?.connection_types ?? [])
                .map((c) => vocabLabel(CONNECTION_TYPE_LABELS, c))
                .join(', ')}
            </ValueChip>
          </MetadataRow>
        )}
        {origin?.detachability && (
          <MetadataRow label="Detachability">
            <ValueChip title={origin.detachability.note ?? undefined}>
              {vocabLabel(DGNB_CLASS_LABELS, origin.detachability.class)}
            </ValueChip>
          </MetadataRow>
        )}
        {(identity.past_cycles ?? []).length > 0 && (
          <MetadataRow label="Earlier cycles">
            <ul className="space-y-0.5">
              {(identity.past_cycles ?? []).map((cycle, index) => (
                <li key={index}>
                  <ValueChip className="max-w-[12rem] whitespace-normal break-words">
                    {vocabLabel(ORIGIN_KIND_LABELS, cycle.origin?.kind ?? 'unknown')}
                    {' --> '}
                    {exitSummary(cycle.exit)}
                  </ValueChip>
                </li>
              ))}
            </ul>
          </MetadataRow>
        )}
        <MetadataRow label="Parent">
          <ComponentLineageIdentityBadges
            kind="parent"
            identities={parentIds.map((id) => ({
              id,
              status: parentStatuses[id] ?? null,
            }))}
          />
        </MetadataRow>
        <MetadataRow label="Children">
          <ComponentLineageIdentityBadges kind="child" identities={childBadges} />
        </MetadataRow>
        <MetadataRow label="Graph">
          <button
            type="button"
            onClick={() => setGraphOpen(true)}
            className="text-xs font-medium text-primary underline underline-offset-4 hover:no-underline"
          >
            View lineage graph
          </button>
        </MetadataRow>
      </section>

      {canEdit && (
        <ProvenanceEditDialog identity={identity} open={editOpen} onOpenChange={setEditOpen} />
      )}

      <Dialog open={graphOpen} onOpenChange={setGraphOpen}>
        <DialogContent className="flex h-[85vh] w-[min(96vw,1120px)] max-w-none flex-col gap-3 p-4 sm:max-w-none">
          <DialogHeader>
            <DialogTitle>Lineage graph</DialogTitle>
            <DialogDescription>
              Identities and snapshot versions related to this component. Green is
              in circulation, amber has left it. Click a node to open it.
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-border">
            {graphLoading ? (
              <div className="flex h-full items-center justify-center text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : graphError ? (
              <p className="p-4 text-sm text-destructive">{graphError}</p>
            ) : graph ? (
              <ComponentProvenanceGraph
                graph={graph}
                onNavigate={() => setGraphOpen(false)}
              />
            ) : (
              <p className="p-4 text-sm text-muted-foreground">No lineage graph.</p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
