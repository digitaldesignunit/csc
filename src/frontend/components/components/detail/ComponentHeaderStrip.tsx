'use client'

/**
 * The header strip of the component page (decision 8.118, Q2): number and
 * name, chips for what the piece is and where it stands (dataset, status,
 * circulation, condition), the identifier small with its copy buttons, and on
 * the right Reserve and the Actions menu. It replaces the heading, the status
 * badges and the action stack of the old identity card.
 */
import { useState } from 'react'
import { Check, Copy, FileText } from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import ChipView from '@/components/common/ChipView'
import { circulationChip, conditionChip, statusChip } from '@/lib/componentDetail'
import { conditionBadge } from '@/lib/evidence/format'
import { generateGrasshopperPanelXML } from '@/lib/utils'
import { isReserved, snapshotDisplayName } from '../componentDetailShared'
import ComponentActionsMenu, { ReserveButton } from './ComponentActionsMenu'

function CopyButton({ label, done, onCopy, icon: Icon }: {
  label: string
  done: string
  onCopy: () => Promise<void>
  icon: typeof Copy
}) {
  const [copied, setCopied] = useState(false)
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="outline" size="sm" className="h-6 w-6 p-0" aria-label={label}
            onClick={async () => {
              try {
                await onCopy()
                setCopied(true)
                setTimeout(() => setCopied(false), 2000)
              } catch (err) {
                console.error('Copy failed:', err)
              }
            }}>
            {copied ? <Check className="h-3 w-3 text-green-600" /> : <Icon className="h-3 w-3" />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{copied ? done : label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export default function ComponentHeaderStrip({ catalog, snapshots }: {
  catalog: CatalogComponent
  snapshots: SnapshotSummaryItem[]
}) {
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const identityId = String(identity._id ?? '')
  const condition = conditionBadge(snapshot.properties)
  const reserved = isReserved(identity)

  return (
    <header className="rounded-lg border border-border bg-card px-3 py-2.5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1 basis-56">
          <h1 className="break-words text-lg font-semibold leading-tight sm:text-xl">
            <span className="text-muted-foreground">#{identity.catalog_number}</span> {snapshotDisplayName(snapshot)}
          </h1>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <ChipView chip={{ label: identity.dataset, tone: 'neutral', title: 'Dataset' }} />
            <ChipView chip={statusChip(snapshot)} />
            <ChipView chip={circulationChip(identity)} />
            {reserved && <ChipView chip={{ label: 'Reserved', tone: 'neutral', title: 'Reserved for a project' }} />}
            <ChipView chip={conditionChip(condition.grade)} href="#properties" />
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <ReserveButton catalog={catalog} />
          <ComponentActionsMenu catalog={catalog} snapshots={snapshots} />
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5">
        <p className="min-w-0 break-all font-mono text-[11px] text-muted-foreground">{identityId}</p>
        <CopyButton label="Copy ID" done="Copied!" icon={Copy}
          onCopy={() => navigator.clipboard.writeText(identityId)} />
        <CopyButton label="Copy as Grasshopper panel" done="Copied!" icon={FileText}
          onCopy={() => navigator.clipboard.writeText(generateGrasshopperPanelXML('ComponentID', identityId))} />
      </div>
    </header>
  )
}
