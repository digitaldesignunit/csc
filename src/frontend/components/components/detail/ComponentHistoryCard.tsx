'use client'

/**
 * The History card (decision 8.102, 8.118): lineage and timeline in one place,
 * as layers. Two renderings of the same data with the same toggles --- List
 * (the timeline with the lineage events; the default on a phone and the
 * accessible form) and Graph (the ELK lineage graph; the default on desktop).
 * Below: the snapshot versions as read-only rows (Correct, Make current and
 * Withdraw are in the Actions menu), the change history (members; it names
 * people, 8.101 M2) and a link to the raw JSON and descriptors.
 */
import { useEffect, useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { Clock, History, Loader2 } from 'lucide-react'

import ComponentChangeHistory from '@/components/lineage/ComponentChangeHistory'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot, type CatalogShallowRow, type ProvenanceGraph } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { BackendError, backendJson } from '@/lib/backend'
import { formatDay, lineageEvents, type Layers } from '@/lib/componentDetail'
import { formatTimestamp } from '@/lib/utils'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { parentIdentityIds } from '../componentDetailShared'
import { useEvidenceData } from './EvidenceData'
import HistoryList, { type TimelineEvent } from './HistoryList'

const ComponentProvenanceGraph = dynamic(() => import('../ComponentProvenanceGraph'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin" />
    </div>
  ),
})

type View = 'list' | 'graph'

const LAYER_LABELS: { key: keyof Layers; label: string; help: string }[] = [
  { key: 'lineage', label: 'Lineage', help: 'The pieces this one was cut from or was cut into' },
  { key: 'states', label: 'States', help: 'The recorded states and their corrections' },
  { key: 'evidence', label: 'Evidence', help: 'The evidence records' },
]

/** The graph with the layers applied: Lineage off leaves this piece, States
 *  off leaves the identities. (The graph has no evidence nodes.) */
function filterGraph(graph: ProvenanceGraph, layers: Layers): ProvenanceGraph {
  const keep = new Set(graph.nodes.filter((node) => {
    if (node.kind === 'identity') return layers.lineage || node.is_root
    if (!layers.states) return false
    return layers.lineage || node.identity_id === graph.root_identity_id
  }).map((node) => node.id))
  return {
    ...graph,
    nodes: graph.nodes.filter((node) => keep.has(node.id)),
    edges: graph.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target)),
  }
}

function useTimeline(identityId: string, reloadKey: number | string) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    backendJson<{ events: TimelineEvent[] }>(`/identities/${encodeURIComponent(identityId)}/timeline`)
      .then((body) => { if (!cancelled) { setEvents(body.events); setError(null) } })
      .catch((err) => {
        if (cancelled) return
        setEvents([])
        setError(err instanceof BackendError ? err.message : 'Could not load the history.')
      })
    return () => { cancelled = true }
  }, [identityId, reloadKey])
  return { events, error }
}

function useGraph(identityId: string, wanted: boolean, stamp: string) {
  const [graph, setGraph] = useState<ProvenanceGraph | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!wanted) return
    let cancelled = false
    backendJson<ProvenanceGraph>(`/identities/${encodeURIComponent(identityId)}/provenance`)
      .then((body) => { if (!cancelled) setGraph(body) })
      .catch(() => { if (!cancelled) setError('Could not load the lineage graph.') })
    return () => { cancelled = true }
  }, [identityId, wanted, stamp])
  return { graph, error }
}

function useParents(parentIds: string[]) {
  const key = parentIds.join('|')
  const [parents, setParents] = useState<{ id: string; catalogNumber?: number | null }[]>([])
  useEffect(() => {
    if (parentIds.length === 0) { setParents([]); return }
    let cancelled = false
    Promise.all(parentIds.map(async (id) => {
      try {
        const row = await backendJson<CatalogShallowRow>(`/identities/${encodeURIComponent(id)}?expand=shallow`)
        return { id, catalogNumber: row.catalog_number }
      } catch {
        return { id, catalogNumber: null }
      }
    })).then((rows) => { if (!cancelled) setParents(rows) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return parents
}

function VersionRows({ identityId, snapshots, activeSnapshotId }: {
  identityId: string
  snapshots: SnapshotSummaryItem[]
  activeSnapshotId: string
}) {
  if (snapshots.length === 0) return null
  const pending = snapshots.some((row) => row.status === 'pending' && !row.is_current)
  return (
    <div className="space-y-1.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Versions</h3>
      {pending && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100" role="status">
          A newer version is awaiting moderation; the current one stays until it is published.
        </p>
      )}
      <ul className="space-y-1">
        {snapshots.map((row) => {
          const active = row._id === activeSnapshotId
          const href = row.is_current
            ? `/components/${encodeURIComponent(identityId)}`
            : `/components/${encodeURIComponent(identityId)}?${new URLSearchParams({ snapshots: row._id })}`
          const stamps = [`created ${formatTimestamp(row.created)}`, `changed ${formatTimestamp(row.lastmodified)}`].join('; ')
          return (
            <li key={row._id}>
              <Link href={href} title={stamps}
                className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md border px-2 py-1 text-xs transition-colors ${
                  active ? 'border-primary bg-primary/5 ring-1 ring-primary/30' : 'border-border bg-muted/20 hover:bg-muted/40'}`}>
                <span className="font-medium">v{row.version}</span>
                {row.is_current && <Badge variant="default" className="text-[10px]">Current</Badge>}
                {active && !row.is_current && <Badge variant="outline" className="text-[10px]">Viewing</Badge>}
                <Badge variant={row.status === 'published' ? 'secondary' : 'outline'} className="text-[10px]">{row.status}</Badge>
                {row.superseded_by && <Badge variant="outline" className="text-[10px]">Corrected</Badge>}
                {row.geometry_failed && (
                  <Badge variant="outline" className="border-red-400 text-[10px] text-red-800 dark:text-red-200"
                    title="The geometry of this version could not be processed">Geometry not processed</Badge>
                )}
                <span className="ml-auto flex items-center gap-1 text-muted-foreground" title="When this state began">
                  <Clock className="h-3 w-3 shrink-0" />since {formatDay(row.effective_from, row.effective_from_precision)}
                </span>
                {row.added_by_username && (
                  <span className="basis-full text-muted-foreground">added by {row.added_by_username}</span>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function RawDataDialog({ catalog, open, onOpenChange }: {
  catalog: CatalogComponent
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const snapshot = primarySnapshot(catalog)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Raw JSON and descriptors</DialogTitle>
          <DialogDescription>The passport as the backend serves it, and the descriptors of this state.</DialogDescription>
        </DialogHeader>
        <h4 className="text-sm font-medium">Descriptors</h4>
        <pre className="max-h-56 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
          <code>{snapshot.descriptors ? JSON.stringify(snapshot.descriptors, null, 2) : 'No descriptors.'}</code>
        </pre>
        <h4 className="text-sm font-medium">Component passport</h4>
        <pre className="max-h-72 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
          <code>{JSON.stringify(catalog, null, 2)}</code>
        </pre>
      </DialogContent>
    </Dialog>
  )
}

export default function ComponentHistoryCard({ catalog, snapshots, childIdentities, activeSnapshotId }: {
  catalog: CatalogComponent
  snapshots: SnapshotSummaryItem[]
  childIdentities: CatalogShallowRow[]
  activeSnapshotId: string
}) {
  const { identity } = catalog
  const identityId = String(identity._id ?? '')
  const desktop = useMediaQuery('(min-width: 1024px)')
  const [chosen, setChosen] = useState<View | null>(null)
  const view: View = chosen ?? (desktop ? 'graph' : 'list')
  const [layers, setLayers] = useState<Layers>({ lineage: true, states: true, evidence: true })
  const [rawOpen, setRawOpen] = useState(false)
  const { reloadKey } = useEvidenceData()
  // an action on the piece (deinstall, exit, re-enter, state) refreshes the
  // identity: the history follows it without a reload of the page
  const stamp = `${reloadKey}:${identity.lastmodified ?? ''}`
  const { events, error } = useTimeline(identityId, stamp)
  const { graph, error: graphError } = useGraph(identityId, view === 'graph', stamp)
  const parents = useParents(parentIdentityIds(identity))

  const startedAt = useMemo(
    () => snapshots.map((s) => s.effective_from).filter(Boolean).sort()[0] ?? identity.created ?? null,
    [snapshots, identity.created],
  )
  const lineage = useMemo(() => lineageEvents({
    startedAt,
    parents,
    children: childIdentities.map((row) => ({
      id: String(row._id), catalogNumber: row.catalog_number, at: row.created ?? row.effective_from ?? null,
    })),
  }), [startedAt, parents, childIdentities])
  const versions = Object.fromEntries(snapshots.map((s) => [String(s._id), s.version]))
  const filtered = useMemo(() => (graph ? filterGraph(graph, layers) : null), [graph, layers])

  return (
    <section aria-label="History" className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><History className="h-4 w-4" />History</h2>
        <ToggleGroup type="single" variant="outline" size="sm" spacing={0} value={view}
          onValueChange={(next) => next && setChosen(next as View)} aria-label="How to show the history">
          <ToggleGroupItem value="list" className="h-7 px-3 text-xs">List</ToggleGroupItem>
          <ToggleGroupItem value="graph" className="h-7 px-3 text-xs">Graph</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Layers">
        {LAYER_LABELS.map(({ key, label, help }) => {
          const unavailable = view === 'graph' && key === 'evidence'
          return (
            <Button key={key} type="button" size="sm" variant={layers[key] && !unavailable ? 'default' : 'outline'}
              className="h-6 rounded-full px-2.5 text-[11px]" aria-pressed={layers[key]} disabled={unavailable}
              title={unavailable ? 'The graph shows identities and states; evidence is in the list' : help}
              onClick={() => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}>
              {label}
            </Button>
          )
        })}
      </div>

      {view === 'list' ? (
        events === null ? (
          <div className="flex justify-center py-4 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : error ? (
          <p className="text-sm text-destructive" role="alert">{error}</p>
        ) : (
          <HistoryList events={events} lineage={lineage} layers={layers} />
        )
      ) : (
        <div className="h-[26rem] overflow-hidden rounded-md border border-border">
          {graphError ? (
            <p className="p-3 text-sm text-destructive">{graphError}</p>
          ) : filtered ? (
            filtered.nodes.length > 0
              ? <ComponentProvenanceGraph graph={filtered} onNavigate={() => undefined} />
              : <p className="p-3 text-sm text-muted-foreground">Nothing to show with these layers.</p>
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
          )}
        </div>
      )}

      <div className="mt-4 space-y-3 border-t border-border pt-3">
        <VersionRows identityId={identityId} snapshots={snapshots} activeSnapshotId={activeSnapshotId} />
        <ComponentChangeHistory identityId={identityId} dataset={identity.dataset} versions={versions} />
        <button type="button" onClick={() => setRawOpen(true)}
          className="text-xs text-primary underline underline-offset-2">
          Raw JSON / descriptors
        </button>
      </div>
      {rawOpen && <RawDataDialog catalog={catalog} open onOpenChange={setRawOpen} />}
    </section>
  )
}
