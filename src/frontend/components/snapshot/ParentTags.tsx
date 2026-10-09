'use client'

/**
 * The parents of a cut or merge: scan or paste their tags (spec 7.6). Each
 * parent is looked up so the user sees which piece the tag is; the backend
 * still decides whether it may be cut (8.34).
 */
import { useEffect, useState } from 'react'
import { Plus, X } from 'lucide-react'

import type { CatalogRow } from '@/generated/CatalogModels'
import { ORIGINAL_FUNCTION_LABELS, type OriginalFunction } from '@/generated/Vocab'
import { Button } from '@/components/ui/button'
import { backendJson, BackendError } from '@/lib/backend'
import { uuidFromScan } from '@/lib/scanIds'
import { TagField } from './TagField'

type Lookup = { state: 'loading' } | { state: 'ok'; row: CatalogRow } | { state: 'missing'; text: string }

function useParentLookup(id: string): Lookup {
  const [found, setFound] = useState<{ id: string; lookup: Lookup } | null>(null)
  useEffect(() => {
    let cancelled = false
    backendJson<CatalogRow>(`/identities/${encodeURIComponent(id)}?expand=shallow`)
      .then((row) => { if (!cancelled) setFound({ id, lookup: { state: 'ok', row } }) })
      .catch((err) => {
        if (cancelled) return
        const status = err instanceof BackendError ? err.status : 0
        const text = status === 404 ? 'No component has this tag.'
          : status === 401 || status === 403 ? 'You cannot see this component.'
            : 'Could not look it up.'
        setFound({ id, lookup: { state: 'missing', text } })
      })
    return () => { cancelled = true }
  }, [id])
  return found?.id === id ? found.lookup : { state: 'loading' }
}

function ParentRow({ id, onRemove, disabled }: { id: string; onRemove: () => void; disabled?: boolean }) {
  const lookup = useParentLookup(id)
  return (
    <li className="flex items-start justify-between gap-2 rounded-md border border-border p-2 text-sm">
      <div className="min-w-0 space-y-0.5">
        {lookup.state === 'ok' ? (
          <>
            <p className="font-medium">
              #{lookup.row.catalog_number} {lookup.row.name ?? ''}
            </p>
            <p className="text-xs text-muted-foreground">
              {ORIGINAL_FUNCTION_LABELS[lookup.row.original_function as OriginalFunction] ?? lookup.row.original_function}
              {' / '}{lookup.row.material}
            </p>
          </>
        ) : lookup.state === 'loading' ? (
          <p className="text-xs text-muted-foreground">Looking it up...</p>
        ) : (
          <p className="text-xs text-destructive">{lookup.text}</p>
        )}
        <p className="break-all font-mono text-[11px] text-muted-foreground">{id}</p>
      </div>
      <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0" disabled={disabled}
        onClick={onRemove} aria-label={`Remove parent ${id}`}>
        <X className="h-4 w-4" />
      </Button>
    </li>
  )
}

export function ParentTags({
  parents,
  onChange,
  exclude,
  disabled,
}: {
  parents: string[]
  onChange: (parents: string[]) => void
  /** The new piece's own tag cannot be its parent. */
  exclude?: string
  disabled?: boolean
}) {
  const [draft, setDraft] = useState('')
  const [scanNote, setScanNote] = useState<string | null>(null)
  const draftId = uuidFromScan(draft)
  const problem = !draftId ? null
    : draftId === exclude ? 'This is the tag of the new piece itself.'
      : parents.includes(draftId) ? 'Already a parent.'
        : null

  const add = (id: string) => {
    if (id === exclude) {
      setScanNote('This is the tag of the new piece itself.')
      return
    }
    if (parents.includes(id)) {
      setScanNote('Already a parent.')
      return
    }
    setScanNote(null)
    onChange([...parents, id])
    setDraft('')
  }

  return (
    <div className="space-y-3">
      {parents.length > 0 && (
        <ul className="space-y-2">
          {parents.map((id) => (
            <ParentRow key={id} id={id} disabled={disabled}
              onRemove={() => onChange(parents.filter((p) => p !== id))} />
          ))}
        </ul>
      )}
      <div className="space-y-2">
        <TagField
          id="parent-tag"
          value={draft}
          onChange={(value) => { setDraft(value); setScanNote(null) }}
          onScan={add}
          placeholder={parents.length ? 'Another parent (merge)' : 'Id or link of the parent'}
          disabled={disabled}
        />
        {(problem || scanNote) && <p className="text-xs text-destructive">{problem ?? scanNote}</p>}
        <Button type="button" variant="outline" size="sm" disabled={disabled || !draftId || !!problem}
          onClick={() => draftId && add(draftId)}>
          <Plus className="mr-1 h-4 w-4" />
          {parents.length ? 'Add another parent' : 'Add parent'}
        </Button>
      </div>
    </div>
  )
}
