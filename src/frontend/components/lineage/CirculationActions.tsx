'use client'

/**
 * Circulation of a component for moderator(D) (spec section 3.1.3, I18;
 * decisions 8.8, 8.19, 8.34): the dialogs to record an exit and to bring an
 * installed, returned or lost piece back with a new origin, and the undo of
 * a mistaken exit. They are opened from the Actions menu of the component
 * page (8.118). A split or merge the server derives from published pieces
 * is undone by withdrawing those pieces, not here.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import type { Exit, Origin } from '@/generated/CatalogModels'
import { EXIT_KIND_LABELS, PRECISION_LABELS, type ExitKind } from '@/generated/Vocab'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { backendJson } from '@/lib/backend'
import {
  cleanOrigin,
  emptyOrigin,
  IN_PLACE_EXIT_KINDS,
  MANUAL_EXIT_KINDS,
} from '@/lib/lineage'
import { DateWithPrecision, Field, OriginFields, VocabSelect } from './fields'

type Precision = keyof typeof PRECISION_LABELS

const EXIT_HINTS: Record<string, string> = {
  installed: 'Built into new works. It can come back later (re-entry).',
  recycled: 'Its material went into recycling. Final.',
  disposed: 'Landfill or incineration. Final.',
  returned: 'Back to its owner or supplier.',
  lost: 'Its whereabouts are unknown.',
  split: 'Cut up without cataloguing the pieces. Catalogued pieces set this by themselves.',
}

function todayIso(): string {
  return `${new Date().toISOString().slice(0, 10)}T00:00:00Z`
}

export function ExitDialog({ identityId, inPlace, open, onOpenChange }: {
  identityId: string
  /** Still in place: only recycled, disposed or lost are open (8.104). */
  inPlace: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const [kind, setKind] = useState<ExitKind>(inPlace ? 'recycled' : 'installed')
  const [at, setAt] = useState<string | null>(todayIso())
  const [precision, setPrecision] = useState<Precision>('day')
  const [work, setWork] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!at) {
      setError('When did it leave circulation?')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await backendJson(`/identities/${identityId}/exit`, {
        method: 'POST',
        body: {
          kind,
          at,
          at_precision: precision,
          construction_work: kind === 'installed' && work.trim() ? { name: work.trim() } : null,
          notes: notes.trim() || null,
        },
      })
      toast.success(`Recorded: ${EXIT_KIND_LABELS[kind].toLowerCase()}`)
      onOpenChange(false)
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next) }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Take out of circulation</DialogTitle>
          <DialogDescription>
            The component leaves the active catalog; its record stays. Its reservation ends.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="What happened" htmlFor="exit-kind" hint={EXIT_HINTS[kind]}>
            <VocabSelect id="exit-kind" labels={EXIT_KIND_LABELS}
              values={inPlace ? IN_PLACE_EXIT_KINDS : MANUAL_EXIT_KINDS}
              value={kind} onChange={(value) => value && setKind(value)} />
          </Field>
          <DateWithPrecision id="exit-at" label="On" at={at} precision={precision}
            onChange={(next, p) => { setAt(next); setPrecision(p) }} />
          {kind === 'installed' && (
            <Field label="Construction work" htmlFor="exit-work">
              <Input id="exit-work" value={work} onChange={(event) => setWork(event.target.value)}
                placeholder="Where it was built in" />
            </Field>
          )}
          <Field label="Notes" htmlFor="exit-notes">
            <Textarea id="exit-notes" rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </Field>
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={busy}>Record exit</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ReenterDialog({ identityId, exit, open, onOpenChange }: {
  identityId: string
  exit: Exit
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const [origin, setOrigin] = useState<Origin>(() => ({
    ...emptyOrigin(),
    kind: exit.kind === 'installed' ? 'deinstallation' : 'unknown',
    at: todayIso(),
    at_precision: 'day',
  }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await backendJson(`/identities/${identityId}/reenter`, {
        method: 'POST',
        body: { origin: cleanOrigin(origin) },
      })
      toast.success('Back in circulation')
      onOpenChange(false)
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next) }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Bring back into circulation</DialogTitle>
          <DialogDescription>
            The earlier origin and exit are kept as a past cycle. The next recorded state starts
            on the new origin date.
          </DialogDescription>
        </DialogHeader>
        <OriginFields idPrefix="reenter-origin" value={origin} onChange={setOrigin} />
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={busy}>Re-enter</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Undo an exit recorded by mistake (the page refreshes). */
export async function undoExit(identityId: string, refresh: () => void): Promise<void> {
  try {
    await backendJson(`/identities/${identityId}/exit`, { method: 'DELETE' })
    toast.success('Exit undone')
    refresh()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Undo failed')
  }
}
