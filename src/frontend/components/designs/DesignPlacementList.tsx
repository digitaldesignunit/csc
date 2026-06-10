'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { DesignComponent } from '@/generated/DesignModel'
import type { ComponentSnapshot } from '@/generated/CatalogModels'
import { fetchSnapshot } from '@/lib/designViewerGeometry'

type PlacementMeta = {
  identityId: string
  version: number
  name: string
}

type DesignPlacementListProps = {
  placements: DesignComponent[]
}

export default function DesignPlacementList({ placements }: DesignPlacementListProps) {
  const [metaBySnapshot, setMetaBySnapshot] = useState<Record<string, PlacementMeta>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      const next: Record<string, PlacementMeta> = {}

      await Promise.all(
        placements.map(async (placement) => {
          const snapshot = (await fetchSnapshot(placement.snapshot)) as ComponentSnapshot | null
          if (!snapshot) return
          next[placement.snapshot] = {
            identityId: snapshot.identity_id,
            version: snapshot.version,
            name:
              typeof snapshot.name === 'string' && snapshot.name.trim()
                ? snapshot.name
                : `v${snapshot.version}`,
          }
        }),
      )

      if (!cancelled) {
        setMetaBySnapshot(next)
        setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [placements])

  return (
    <div className="space-y-2">
      {placements.map((placement, index) => {
        const meta = metaBySnapshot[placement.snapshot]
        const href = meta
          ? `/components/${meta.identityId}?snapshots=${encodeURIComponent(placement.snapshot)}`
          : undefined

        return (
          <div
            key={placement.snapshot}
            className="flex items-center justify-between p-3 border rounded-lg gap-3"
          >
            <div className="flex items-center space-x-3 min-w-0">
              <span className="text-sm text-muted-foreground shrink-0">#{index + 1}</span>
              <div className="min-w-0">
                <div className="font-small font-mono break-all">{placement.snapshot}</div>
                <div className="text-sm text-muted-foreground">
                  {loading
                    ? 'Loading snapshot…'
                    : meta
                      ? `${meta.name} (identity ${meta.identityId.slice(0, 8)}…)`
                      : 'Snapshot metadata unavailable'}
                </div>
                <div className="text-sm text-muted-foreground">
                  o: [{placement.iframe.o.map((v) => v.toFixed(2)).join(', ')}]
                </div>
              </div>
            </div>
            {href ? (
              <Link href={href}>
                <Button variant="outline" size="sm">
                  View snapshot
                </Button>
              </Link>
            ) : (
              <Button variant="outline" size="sm" disabled>
                View snapshot
              </Button>
            )}
          </div>
        )
      })}
    </div>
  )
}
