'use client'

/**
 * Deinstallation of a piece that is in place, for moderator(D) (spec 3.1.6,
 * decisions 8.104, 8.110): record that it was taken out of its works, or
 * take that back while nothing follows it. A batch's deinstallation reaches
 * the pieces drawn from it that still inherit the origin.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import type { ComponentIdentity } from '@/generated/CatalogModels'
import { ORIGIN_KIND_LABELS, PRECISION_LABELS } from '@/generated/Vocab'
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
import { WORKS_ORIGIN_KINDS } from '@/lib/lineage'
import { DateWithPrecision, Field, VocabSelect } from './fields'

type Precision = keyof typeof PRECISION_LABELS

function todayIso(): string {
  return `${new Date().toISOString().slice(0, 10)}T00:00:00Z`
}

/** The body of `POST /identities/{id}/deinstall`: only what was filled in. */
export function deinstallBody(input: {
  at: string
  precision: string
  kind: 'deinstallation' | 'demolition'
  method: string
  notes: string
}) {
  return {
    at: input.at,
    at_precision: input.precision,
    kind: input.kind,
    ...(input.method.trim() ? { method: input.method.trim() } : {}),
    ...(input.notes.trim() ? { notes: input.notes.trim() } : {}),
  }
}

export function DeinstallDialog({ identity, open, onOpenChange }: {
  identity: ComponentIdentity
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const planned = identity.origin?.at ?? null
  const [at, setAt] = useState<string | null>(planned ?? todayIso())
  const [precision, setPrecision] = useState<Precision>(planned ? identity.origin?.at_precision ?? 'day' : 'day')
  const [kind, setKind] = useState<'deinstallation' | 'demolition'>(
    identity.origin?.kind === 'demolition' ? 'demolition' : 'deinstallation')
  const [method, setMethod] = useState(identity.origin?.method ?? '')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!at) {
      setError('When was it deinstalled?')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await backendJson(`/identities/${identity._id}/deinstall`, {
        method: 'POST',
        body: deinstallBody({ at, precision, kind, method, notes }),
      })
      toast.success('Deinstallation recorded')
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
          <DialogTitle>Record deinstallation</DialogTitle>
          <DialogDescription>
            The piece is out of its works. Its reservation stays, and no new state is created;
            record one if the piece changed. Pieces drawn from it that take over its origin follow.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="How" htmlFor="deinstall-kind">
            <VocabSelect id="deinstall-kind" labels={ORIGIN_KIND_LABELS} values={WORKS_ORIGIN_KINDS}
              value={kind} onChange={(value) => value && setKind(value as typeof kind)} />
          </Field>
          <DateWithPrecision id="deinstall-at" label="Deinstalled on" at={at} precision={precision}
            onChange={(next, p) => { setAt(next); setPrecision(p) }} />
          <Field label="Method" htmlFor="deinstall-method">
            <Input id="deinstall-method" value={method} onChange={(event) => setMethod(event.target.value)}
              placeholder="e.g. unbolted, crane lift" />
          </Field>
          <Field label="Notes" htmlFor="deinstall-notes">
            <Textarea id="deinstall-notes" rows={2} value={notes}
              onChange={(event) => setNotes(event.target.value)} />
          </Field>
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={busy}>Record deinstallation</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Take a deinstallation back while nothing follows it (the backend refuses
 *  it when a state or evidence is dated after the deinstallation). */
export async function undoDeinstall(identityId: string, refresh: () => void): Promise<void> {
  try {
    await backendJson(`/identities/${identityId}/undo-deinstall`, { method: 'POST' })
    toast.success('Deinstallation undone: the piece is in place again')
    refresh()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Undo failed')
  }
}
