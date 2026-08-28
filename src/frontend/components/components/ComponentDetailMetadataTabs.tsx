'use client'

import { useEffect, useState, type ReactNode } from 'react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import {
  componentBounds,
  componentColorString,
  formatTimestamp,
  hexComponentColor,
} from '@/lib/utils'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import ComponentLineageIdentityBadges from './ComponentLineageIdentityBadges'
import {
  conditionBadgeClass,
  conditionLabel,
  isConsumedShallowRow,
  isNonEmptyString,
  parentIdentityIds,
  snapshotAddedByDisplay,
} from './componentDetailShared'

const tabsListClass = cn(
  'grid h-8 w-full min-w-0 grid-cols-4 items-center gap-0.5 overflow-hidden rounded-lg',
  'border border-border bg-background p-0.5 shadow-sm',
)
const tabTriggerClass = cn(
  'min-w-0 rounded-md px-1 py-1 text-[11px] font-medium leading-tight',
  'cursor-pointer text-foreground/80 transition-colors',
  'hover:bg-accent hover:text-foreground',
  'data-[state=active]:bg-primary/15 data-[state=active]:font-semibold data-[state=active]:text-primary data-[state=active]:shadow-sm',
  'dark:data-[state=active]:bg-primary/25',
)

function MetadataTabNav({ children }: { children: ReactNode }) {
  return <div className="w-full min-w-0">{children}</div>
}

function MetadataRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/60 py-1.5 last:border-0">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <div className="min-w-0 text-right text-xs font-medium text-foreground">{children}</div>
    </div>
  )
}

type ValueChipTone = 'primary' | 'secondary' | 'muted'

const chipToneClass: Record<ValueChipTone, string> = {
  primary: 'bg-primary/25 text-foreground font-semibold',
  secondary: 'bg-secondary/25 text-foreground font-semibold',
  muted: 'bg-muted/50 text-foreground',
}

function ValueChip({
  children,
  tone = 'muted',
  className = '',
}: {
  children: ReactNode
  tone?: ValueChipTone
  className?: string
}) {
  return (
    <span
      className={`inline-block max-w-full truncate rounded-md px-2 py-0.5 text-xs ${chipToneClass[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

type LineageStatus = 'active' | 'consumed'

type MetadataPanelsProps = {
  catalog: CatalogComponent
  parentStatuses: Record<string, LineageStatus>
  childIdentities: CatalogShallowRow[]
}

function CatalogMetadataPanel({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const componentColorStr = componentColorString(
    Array.isArray(snapshot.color) ? snapshot.color : [],
  )
  const componentColorHex = hexComponentColor(Array.isArray(snapshot.color) ? snapshot.color : [])
  const bounds = componentBounds(snapshot.bbx)
  const addedBy = snapshotAddedByDisplay(snapshot)

  return (
    <>
      <MetadataRow label="Type">
        <ValueChip tone="primary">{identity.type}</ValueChip>
      </MetadataRow>
      <MetadataRow label="Material">
        <ValueChip tone="secondary">{identity.material}</ValueChip>
      </MetadataRow>
      <MetadataRow label="Color">
        <span className="inline-flex items-center justify-end gap-2">
          <span
            className="inline-block h-4 w-4 shrink-0 rounded-full border-2 border-border shadow-sm"
            style={{ backgroundColor: componentColorHex }}
            title={componentColorStr}
          />
          <ValueChip tone="primary">{componentColorStr}</ValueChip>
        </span>
      </MetadataRow>
      <MetadataRow label="Dataset">
        <ValueChip tone="secondary">{identity.dataset}</ValueChip>
      </MetadataRow>
      <MetadataRow label="Fragment">
        <ValueChip tone="primary">{String(snapshot.fragment)}</ValueChip>
      </MetadataRow>
      <MetadataRow label="Complexity">
        <ValueChip tone="secondary">{snapshot.complexity}</ValueChip>
      </MetadataRow>
      <MetadataRow label="Quantity">
        <ValueChip tone="primary">
          {typeof snapshot.quantity === 'number' && snapshot.quantity >= 1
            ? snapshot.quantity
            : 1}
        </ValueChip>
      </MetadataRow>
      {addedBy && (
        <MetadataRow label="Added by">
          <ValueChip tone="secondary">{addedBy}</ValueChip>
        </MetadataRow>
      )}
      {isNonEmptyString(snapshot.notes) && (
        <MetadataRow label="Notes">
          <ValueChip tone="secondary" className="max-w-[14rem] whitespace-pre-wrap break-words">
            {String(snapshot.notes)}
          </ValueChip>
        </MetadataRow>
      )}
      <div className="border-b border-border/60 py-2 last:border-0">
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Bounding box
        </p>
        <div className="grid grid-cols-3 gap-1.5 text-center">
          {(['X', 'Y', 'Z'] as const).map((axis, i) => (
            <div key={axis} className="rounded-md border border-border/50 bg-muted/30 px-1 py-1">
              <div className="text-[10px] font-medium text-muted-foreground">{axis}</div>
              <div className="font-mono text-xs font-semibold tabular-nums text-foreground">
                {bounds[i].toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

function TimelineMetadataPanel({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const isConsumed = isConsumedShallowRow({
    consumed_at: identity.consumed_at as string | null | undefined,
  })
  const reservedBy = typeof identity.reserved === 'string' ? identity.reserved.trim() : ''

  return (
    <>
      <MetadataRow label="Created">
        <ValueChip tone="secondary">{formatTimestamp(identity.created)}</ValueChip>
      </MetadataRow>
      <MetadataRow label="Last modified">
        <ValueChip tone="primary">{formatTimestamp(snapshot.lastmodified)}</ValueChip>
      </MetadataRow>
      <MetadataRow label="Validated">
        {snapshot.validated ? (
          <span className="rounded-md border border-green-300 bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-800 dark:border-green-700 dark:bg-green-950/50 dark:text-green-200">
            Yes
          </span>
        ) : (
          <ValueChip tone="muted">No</ValueChip>
        )}
      </MetadataRow>
      <MetadataRow label="Reserved">
        <ValueChip tone={reservedBy ? 'primary' : 'muted'}>{reservedBy ? 'Yes' : 'No'}</ValueChip>
      </MetadataRow>
      {isConsumed && (
        <MetadataRow label="Consumed">
          <ValueChip tone="secondary">
            {identity.consumed_at ? formatTimestamp(String(identity.consumed_at)) : 'Yes'}
          </ValueChip>
        </MetadataRow>
      )}
      <MetadataRow label="Snapshot ID">
        <span className="font-mono text-[10px] break-all">{String(snapshot._id ?? '—')}</span>
      </MetadataRow>
    </>
  )
}

function ProvenanceMetadataPanel({
  catalog,
  parentStatuses,
  childIdentities,
}: MetadataPanelsProps) {
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const parentIds = parentIdentityIds(identity)
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

  return (
    <>
      <MetadataRow label="Condition">
        {typeof snapshot.condition === 'number' ? (
          <span
            className={`inline-block rounded-md px-1.5 py-0.5 text-xs font-medium ${conditionBadgeClass(snapshot.condition)}`}
          >
            {conditionLabel(snapshot.condition)}
          </span>
        ) : (
          <span className="text-xs italic text-muted-foreground">Unknown</span>
        )}
      </MetadataRow>
      <MetadataRow label="Manufactured">
        {isNonEmptyString(identity.manufactured_at) ? (
          <ValueChip tone="secondary">
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
          <ValueChip tone="secondary">{formatTimestamp(identity.salvaged_at)}</ValueChip>
        ) : (
          <span className="rounded-md bg-muted/30 px-2 py-0.5 text-xs italic text-muted-foreground">
            Unknown
          </span>
        )}
      </MetadataRow>
      <MetadataRow label="Salvage source">
        {isNonEmptyString(identity.salvage_source) ? (
          <ValueChip tone="secondary" className="max-w-[12rem] whitespace-normal break-words">
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
    </>
  )
}

function AdvancedMetadataPanel({ catalog }: { catalog: CatalogComponent }) {
  const snapshot = primarySnapshot(catalog)

  return (
    <Accordion type="single" collapsible className="w-full rounded-lg border border-border/60">
      <AccordionItem value="descriptors">
        <AccordionTrigger className="px-3 py-2.5 text-sm">Descriptors</AccordionTrigger>
        <AccordionContent className="px-3 pb-3 pt-0">
          <div className="max-h-48 overflow-auto rounded-md border border-border bg-muted/40 p-3">
            {snapshot.descriptors ? (
              <pre className="whitespace-pre-wrap text-xs leading-relaxed text-foreground">
                <code>{JSON.stringify(snapshot.descriptors, null, 2)}</code>
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">No descriptors.</p>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="raw-json">
        <AccordionTrigger className="px-3 py-2.5 text-sm">Raw JSON</AccordionTrigger>
        <AccordionContent className="px-3 pb-3 pt-0">
          <div className="max-h-48 overflow-auto rounded-md border border-border bg-muted/40 p-3">
            <pre className="whitespace-pre-wrap text-xs leading-relaxed text-foreground">
              <code>{JSON.stringify(catalog, null, 2)}</code>
            </pre>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}

export function ComponentDetailCatalogMetadata({ catalog }: { catalog: CatalogComponent }) {
  return <CatalogMetadataPanel catalog={catalog} />
}

function useParentComponentStatus(
  catalog: CatalogComponent,
  childIdentities: CatalogShallowRow[],
) {
  const parentIds = parentIdentityIds(catalog.identity)
  const [parentStatuses, setParentStatuses] = useState<Record<string, LineageStatus>>({})

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

  return {
    panelProps: {
      catalog,
      parentStatuses,
      childIdentities,
    } satisfies MetadataPanelsProps,
  }
}

type ComponentDetailMetadataTabsProps = {
  catalog: CatalogComponent
  mode?: 'all' | 'secondary'
  className?: string
  childIdentities?: CatalogShallowRow[]
}

export default function ComponentDetailMetadataTabs({
  catalog,
  mode = 'all',
  className,
  childIdentities = [],
}: ComponentDetailMetadataTabsProps) {
  const { panelProps } = useParentComponentStatus(catalog, childIdentities)

  if (mode === 'secondary') {
    return (
      <Tabs defaultValue="timeline" className={cn('w-full', className)}>
        <MetadataTabNav>
          <TabsList className={tabsListClass}>
            <TabsTrigger value="timeline" className={tabTriggerClass}>
              Timeline
            </TabsTrigger>
            <TabsTrigger value="provenance" className={tabTriggerClass}>
              Provenance
            </TabsTrigger>
            <TabsTrigger value="advanced" className={tabTriggerClass}>
              Advanced
            </TabsTrigger>
          </TabsList>
        </MetadataTabNav>
        <TabsContent value="timeline" className="mt-3">
          <TimelineMetadataPanel catalog={catalog} />
        </TabsContent>
        <TabsContent value="provenance" className="mt-3">
          <ProvenanceMetadataPanel {...panelProps} />
        </TabsContent>
        <TabsContent value="advanced" className="mt-3">
          <AdvancedMetadataPanel catalog={catalog} />
        </TabsContent>
      </Tabs>
    )
  }

  return (
    <Tabs defaultValue="catalog" className={cn('w-full border-t border-border pt-4', className)}>
      <MetadataTabNav>
        <TabsList className={tabsListClass}>
          <TabsTrigger value="catalog" className={tabTriggerClass}>
            Catalog
          </TabsTrigger>
          <TabsTrigger value="timeline" className={tabTriggerClass}>
            Timeline
          </TabsTrigger>
          <TabsTrigger value="provenance" className={tabTriggerClass}>
            Provenance
          </TabsTrigger>
          <TabsTrigger value="advanced" className={tabTriggerClass}>
            Advanced
          </TabsTrigger>
        </TabsList>
      </MetadataTabNav>
      <TabsContent value="catalog" className="mt-3">
        <CatalogMetadataPanel catalog={catalog} />
      </TabsContent>
      <TabsContent value="timeline" className="mt-3">
        <TimelineMetadataPanel catalog={catalog} />
      </TabsContent>
      <TabsContent value="provenance" className="mt-3">
        <ProvenanceMetadataPanel {...panelProps} />
      </TabsContent>
      <TabsContent value="advanced" className="mt-3">
        <AdvancedMetadataPanel catalog={catalog} />
      </TabsContent>
    </Tabs>
  )
}
