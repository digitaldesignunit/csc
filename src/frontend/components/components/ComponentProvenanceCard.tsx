'use client'

import { useEffect, useState, type ReactNode } from 'react'
import dynamic from 'next/dynamic'
import { GitFork, Loader2 } from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import type { CatalogShallowRow, ProvenanceGraph } from '@/generated/catalogExtras'
import { formatTimestamp } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import ComponentLineageIdentityBadges from './ComponentLineageIdentityBadges'
import {
  isConsumedShallowRow,
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
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-block max-w-full truncate rounded-md bg-secondary/25 px-2 py-0.5 text-xs font-semibold text-foreground ${className}`}
    >
      {children}
    </span>
  )
}

type LineageStatus = 'active' | 'consumed'

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
        status: isConsumedShallowRow(row) ? ('consumed' as const) : ('active' as const),
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
              { credentials: 'include' },
            )
            if (!res.ok) {
              return null
            }
            const row = (await res.json()) as CatalogShallowRow
            return [
              parentId,
              isConsumedShallowRow(row) ? 'consumed' : 'active',
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
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <GitFork className="h-4 w-4" />
          Provenance
        </h3>
        <MetadataRow label="Manufactured">
          {isNonEmptyString(identity.manufactured_at) ? (
            <ValueChip>
              {formatTimestamp(identity.manufactured_at)}
              {isNonEmptyString(identity.manufactured_precision)
                ? ` (${identity.manufactured_precision})`
                : ''}
            </ValueChip>
          ) : (
            <span className="rounded-md bg-muted/30 px-2 py-0.5 text-xs italic text-muted-foreground">
              Unknown
            </span>
          )}
        </MetadataRow>
        <MetadataRow label="Salvaged">
          {isNonEmptyString(identity.salvaged_at) ? (
            <ValueChip>{formatTimestamp(identity.salvaged_at)}</ValueChip>
          ) : (
            <span className="rounded-md bg-muted/30 px-2 py-0.5 text-xs italic text-muted-foreground">
              Unknown
            </span>
          )}
        </MetadataRow>
        <MetadataRow label="Salvage source">
          {isNonEmptyString(identity.salvage_source) ? (
            <ValueChip className="max-w-[12rem] whitespace-normal break-words">
              {identity.salvage_source}
            </ValueChip>
          ) : (
            <span className="text-xs italic text-muted-foreground">Unknown</span>
          )}
        </MetadataRow>
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

      <Dialog open={graphOpen} onOpenChange={setGraphOpen}>
        <DialogContent className="flex h-[85vh] w-[min(96vw,1120px)] max-w-none flex-col gap-3 p-4 sm:max-w-none">
          <DialogHeader>
            <DialogTitle>Lineage graph</DialogTitle>
            <DialogDescription>
              Identities and snapshot versions related to this component. Green is
              active, amber is consumed. Click a node to open it.
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
