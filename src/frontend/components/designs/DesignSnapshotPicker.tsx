'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DesignComponent } from '@/generated/DesignModel'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { Plus, Search, X } from 'lucide-react'

const defaultIframe = (): DesignComponent['iframe'] => ({
  o: [0, 0, 0],
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1],
})

type DesignSnapshotPickerProps = {
  placements: DesignComponent[]
  onChange: (placements: DesignComponent[]) => void
}

export default function DesignSnapshotPicker({
  placements,
  onChange,
}: DesignSnapshotPickerProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<CatalogShallowRow[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [expandedIdentityId, setExpandedIdentityId] = useState<string | null>(null)
  const [versionRows, setVersionRows] = useState<SnapshotSummaryItem[]>([])
  const [isLoadingVersions, setIsLoadingVersions] = useState(false)

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setIsSearching(true)
    try {
      const response = await fetch(
        `/api/backend/identities?page=1&size=20&comptype=&material=&dataset=&expand=shallow`,
        { credentials: 'include' },
      )
      if (response.ok) {
        setSearchResults((await response.json()) as CatalogShallowRow[])
      }
    } finally {
      setIsSearching(false)
    }
  }

  const loadVersions = async (identityId: string) => {
    if (expandedIdentityId === identityId) {
      setExpandedIdentityId(null)
      setVersionRows([])
      return
    }

    setExpandedIdentityId(identityId)
    setIsLoadingVersions(true)
    try {
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/snapshots`,
        { credentials: 'include' },
      )
      if (response.ok) {
        setVersionRows((await response.json()) as SnapshotSummaryItem[])
      } else {
        setVersionRows([])
      }
    } finally {
      setIsLoadingVersions(false)
    }
  }

  const addPlacement = (snapshotId: string) => {
    onChange([
      ...placements,
      { snapshot: snapshotId, iframe: defaultIframe() },
    ])
    setExpandedIdentityId(null)
    setVersionRows([])
    setSearchQuery('')
    setSearchResults([])
  }

  const removePlacement = (index: number) => {
    onChange(placements.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="design-snapshot-search">Add snapshot placements</Label>
        <div className="flex gap-2 mt-1">
          <Input
            id="design-snapshot-search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search identities..."
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                void handleSearch()
              }
            }}
          />
          <Button type="button" onClick={() => void handleSearch()} disabled={isSearching}>
            <Search className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {searchResults.length > 0 && (
        <div className="border rounded-lg p-4 max-h-64 overflow-y-auto space-y-2">
          <h4 className="font-medium">Search results</h4>
          {searchResults.map((row) => {
            const identityId = row._id ?? ''
            const isExpanded = expandedIdentityId === identityId
            return (
              <div key={identityId} className="border rounded p-2 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium truncate">
                      {typeof row.name === 'string' ? row.name : 'Unnamed identity'}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {row.type} • {row.material}
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void loadVersions(identityId)}
                  >
                    {isExpanded ? 'Hide versions' : 'Pick version'}
                  </Button>
                </div>
                {isExpanded && (
                  <div className="space-y-1 pl-2 border-l">
                    {isLoadingVersions ? (
                      <p className="text-sm text-muted-foreground">Loading versions…</p>
                    ) : versionRows.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No snapshots found.</p>
                    ) : (
                      versionRows.map((snap) => (
                        <div
                          key={snap._id}
                          className="flex items-center justify-between gap-2 text-sm"
                        >
                          <span>
                            v{snap.version}
                            {typeof snap.name === 'string' && snap.name ? ` — ${snap.name}` : ''}
                            {snap.is_current ? ' (current)' : ''}
                          </span>
                          <Button
                            type="button"
                            size="sm"
                            onClick={() => addPlacement(snap._id)}
                          >
                            <Plus className="h-4 w-4" />
                          </Button>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="space-y-2">
        <Label>Selected snapshots ({placements.length})</Label>
        {placements.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No snapshots added yet. Search identities and pick a specific version.
          </div>
        ) : (
          placements.map((placement, index) => (
            <div
              key={`${placement.snapshot}-${index}`}
              className="flex items-center justify-between p-3 border rounded-lg"
            >
              <div className="min-w-0">
                <div className="font-medium font-mono text-sm truncate">
                  {placement.snapshot}
                </div>
                <div className="text-sm text-muted-foreground">
                  o: [{placement.iframe.o.map((v) => v.toFixed(2)).join(', ')}]
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => removePlacement(index)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
