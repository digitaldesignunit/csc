'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
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
import {
  conditionBadgeClass,
  conditionLabel,
  isConsumedShallowRow,
  isNonEmptyString,
  primaryParentIdentityId,
} from './componentDetailShared'

const tabsListClass = cn(
  'inline-flex h-10 w-max min-w-0 flex-nowrap items-center justify-center gap-1.5 rounded-lg',
  'border border-border bg-background p-1 shadow-sm',
)
const tabTriggerClass = cn(
  'flex-none shrink-0 rounded-md px-3.5 py-1.5 text-sm',
  'cursor-pointer text-foreground/80 transition-colors',
  'hover:bg-accent hover:text-foreground',
  'data-[state=active]:bg-primary/15 data-[state=active]:font-semibold data-[state=active]:text-primary data-[state=active]:shadow-sm',
  'dark:data-[state=active]:bg-primary/25',
)

function MetadataTabNav({ children }: { children: ReactNode }) {
  return <div className="flex w-full justify-center overflow-x-auto pb-1">{children}</div>
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

type MetadataPanelsProps = {
  catalog: CatalogComponent
  openingParentComponent: boolean
  parentComponentStatus: 'active' | 'consumed' | null
  onOpenParent: (parentId: string) => void
}

function CatalogMetadataPanel({ catalog }: { catalog: CatalogComponent }) {
  const { identity, snapshot } = catalog
  const componentColorStr = componentColorString(
    Array.isArray(snapshot.color) ? snapshot.color : [],
  )
  const componentColorHex = hexComponentColor(Array.isArray(snapshot.color) ? snapshot.color : [])
  const bounds = componentBounds(snapshot.bbx)

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
  const { identity, snapshot } = catalog
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
  openingParentComponent,
  parentComponentStatus,
  onOpenParent,
}: MetadataPanelsProps) {
  const { identity, snapshot } = catalog
  const parentIdentityId = primaryParentIdentityId(identity)

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
        {isNonEmptyString(parentIdentityId) ? (
          <span className="inline-flex max-w-full flex-wrap items-center justify-end gap-1">
            <button
              type="button"
              onClick={() => onOpenParent(String(parentIdentityId))}
              disabled={openingParentComponent}
              className="font-mono text-[11px] text-primary hover:underline disabled:opacity-70"
              title={`Open parent ${parentIdentityId}`}
            >
              {openingParentComponent ? (
                <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />
              ) : null}
              <span className="break-all">{parentIdentityId}</span>
            </button>
            {parentComponentStatus && (
              <span
                className={`rounded border px-1 py-0 text-[10px] ${
                  parentComponentStatus === 'consumed'
                    ? 'border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200'
                    : 'border-green-300 bg-green-100 text-green-800 dark:border-green-700 dark:bg-green-950/40 dark:text-green-200'
                }`}
              >
                {parentComponentStatus === 'consumed' ? 'Consumed' : 'Active'}
              </span>
            )}
          </span>
        ) : (
          <span className="text-xs italic text-muted-foreground">None</span>
        )}
      </MetadataRow>
    </>
  )
}

function AdvancedMetadataPanel({ catalog }: { catalog: CatalogComponent }) {
  const { snapshot } = catalog

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

function useParentComponentStatus(catalog: CatalogComponent) {
  const parentIdentityId = primaryParentIdentityId(catalog.identity)
  const router = useRouter()
  const [openingParentComponent, setOpeningParentComponent] = useState(false)
  const [parentComponentStatus, setParentComponentStatus] = useState<'active' | 'consumed' | null>(
    null,
  )

  useEffect(() => {
    const parentId = isNonEmptyString(parentIdentityId) ? parentIdentityId : null
    if (!parentId) {
      setParentComponentStatus(null)
      return
    }

    let cancelled = false
    const resolveParentStatus = async () => {
      try {
        setParentComponentStatus(null)
        const res = await fetch(
          `/api/backend/identities/${encodeURIComponent(parentId)}?expand=shallow`,
          { credentials: 'include' },
        )
        if (res.ok) {
          const row = (await res.json()) as CatalogShallowRow
          if (!cancelled) {
            setParentComponentStatus(isConsumedShallowRow(row) ? 'consumed' : 'active')
          }
        }
      } catch (error) {
        console.error('Failed to resolve parent component status:', error)
      }
    }

    resolveParentStatus()
    return () => {
      cancelled = true
    }
  }, [parentIdentityId])

  const handleOpenParentComponent = async (parentId: string) => {
    try {
      setOpeningParentComponent(true)
      if (parentComponentStatus === 'active' || parentComponentStatus === 'consumed') {
        router.push(`/components/${parentId}`)
        return
      }
      const res = await fetch(
        `/api/backend/identities/${encodeURIComponent(parentId)}?expand=shallow`,
        { credentials: 'include' },
      )
      if (res.ok) {
        router.push(`/components/${parentId}`)
        return
      }
      if (res.status === 404) {
        alert('Parent component could not be found.')
        return
      }
      alert('Failed to open parent component. Please try again.')
    } catch (error) {
      console.error('Failed to resolve parent component:', error)
      alert('Failed to open parent component. Please try again.')
    } finally {
      setOpeningParentComponent(false)
    }
  }

  return {
    openingParentComponent,
    parentComponentStatus,
    handleOpenParentComponent,
    panelProps: {
      catalog,
      openingParentComponent,
      parentComponentStatus,
      onOpenParent: handleOpenParentComponent,
    } satisfies MetadataPanelsProps,
  }
}

type ComponentDetailMetadataTabsProps = {
  catalog: CatalogComponent
  mode?: 'all' | 'secondary'
  className?: string
}

export default function ComponentDetailMetadataTabs({
  catalog,
  mode = 'all',
  className,
}: ComponentDetailMetadataTabsProps) {
  const { panelProps } = useParentComponentStatus(catalog)

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
