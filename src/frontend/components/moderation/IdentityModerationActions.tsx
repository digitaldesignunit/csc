'use client'

/**
 * Withdraw or reinstate a whole component (moderator(D); spec section
 * 3.1.4, decisions 8.17, I19). A duplicate names its canonical piece: the
 * permanent link and the component page then lead there. The Actions menu
 * of the component page opens the dialog (8.118). Also here: move an element
 * to another dataset (8.191) and delete one nothing of which was published
 * (8.192).
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import type { DatasetView } from '@/generated/AccessModels'
import { Button } from '@/components/ui/button'
import { WriteButton } from '@/components/ui/write-button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import ReasonDialog from '@/components/moderation/ReasonDialog'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'
import { moveTargets, unreviewedRefuses, unreviewedWarning, type MoveTarget } from '@/lib/moveTargets'
import { uuidFromScan } from '@/lib/scanIds'

/** The dialog to withdraw a whole component (a reason, and the canonical piece
 *  when it duplicates one). Opened from the Actions menu (8.118). */
export function WithdrawComponentDialog({ identityId, open, onOpenChange }: {
  identityId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const [duplicate, setDuplicate] = useState('')

  const withdraw = async (reason: string) => {
    const raw = duplicate.trim()
    const duplicateOf = raw ? uuidFromScan(raw) : null
    if (raw && !duplicateOf) throw new Error('Duplicate of: give the component id or its link.')
    await backendJson(`/identities/${identityId}/withdraw`, {
      method: 'POST',
      body: { reason, duplicate_of: duplicateOf },
    })
    toast.success('Component withdrawn')
    setDuplicate('')
    router.refresh()
  }

  return (
    <ReasonDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Withdraw this component"
      description="It disappears from lists and the public view; members of its dataset keep the full record. Nothing is deleted."
      confirmLabel="Withdraw"
      destructive
      onConfirm={withdraw}
    >
      <div className="space-y-1 pt-2">
        <Label htmlFor="duplicate-of">Duplicate of (optional)</Label>
        <Input
          id="duplicate-of"
          value={duplicate}
          onChange={(event) => setDuplicate(event.target.value)}
          placeholder="Id or link of the component this one duplicates"
        />
        <p className="text-xs text-muted-foreground">
          Its tag and link then lead to that component.
        </p>
      </div>
    </ReasonDialog>
  )
}

/** Bring a withdrawn component back. */
export async function reinstateComponent(identityId: string, refresh: () => void): Promise<void> {
  try {
    await backendJson(`/identities/${identityId}/reinstate`, { method: 'POST' })
    toast.success('Component reinstated')
    refresh()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Reinstate failed')
  }
}

/** Delete an element nothing of which was published (`delete_identity`, 8.192); the caller confirmed. */
export async function deleteComponent(identityId: string, goTo: (path: string) => void): Promise<void> {
  try {
    await backendJson(`/identities/${identityId}`, { method: 'DELETE' })
    toast.success('Component deleted')
    goTo('/components')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Delete failed')
  }
}

/**
 * Move the element to another dataset (8.191): a moderator of its dataset and
 * of the destination, an admin any. The route refuses while a version or an
 * evidence record is draft or pending (the rights of its author hang on the
 * dataset), and a public element does not move into a dataset an admin has not
 * reviewed. One element at a time.
 */
export function MoveComponentDialog({ identityId, dataset, isPublic, hasOpenSnapshot, open, onOpenChange }: {
  identityId: string
  dataset: string | null | undefined
  isPublic: boolean | null | undefined
  /** `has_open_snapshot` (8.195): a draft or pending version is known to exist */
  hasOpenSnapshot: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const { me, isAdmin } = useMe()
  const [rows, setRows] = useState<DatasetView[] | null>(null)
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    backendJson<DatasetView[]>('/datasets')
      .then((loaded) => { if (!cancelled) setRows(loaded) })
      .catch((err) => { if (!cancelled) { setRows([]); setError(err instanceof Error ? err.message : 'Could not load the datasets') } })
    return () => { cancelled = true }
  }, [open])

  const targets: MoveTarget[] = rows
    ? moveTargets({ datasets: rows, moderated: me?.moderated_datasets ?? [], isAdmin, current: dataset })
    : []
  const chosen = targets.find((row) => row.id === target)
  const warning = unreviewedWarning(chosen, isPublic, isAdmin)

  const submit = async () => {
    if (!chosen) return
    setBusy(true)
    setError(null)
    try {
      await backendJson(`/identities/${identityId}/move`, { method: 'POST', body: { dataset: chosen.id } })
      toast.success(`Moved to ${chosen.name}`)
      onOpenChange(false)
      setTarget('')
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Move failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next) }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Move to another dataset</DialogTitle>
          <DialogDescription>
            The component, with its snapshots and evidence, belongs to the other dataset afterwards. Its catalog number
            stays. A move can change who sees it: the members of the new dataset see it, the members of{' '}
            {dataset ?? 'this dataset'} no longer do unless they belong to both.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {hasOpenSnapshot && (
            <p role="status" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
              A snapshot of this component is waiting for review (draft or pending). It moves only when no snapshot or
              evidence record is draft or pending: publish, reject or delete those first, because the rights of their
              authors hang on the dataset.
            </p>
          )}
          {rows === null ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : targets.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              There is no other dataset you moderate. Moving needs a moderator of both datasets.
            </p>
          ) : (
            <div className="space-y-1">
              <Label htmlFor="move-target">Destination</Label>
              <Select value={target || undefined} onValueChange={setTarget} disabled={busy}>
                <SelectTrigger id="move-target" className="w-full"><SelectValue placeholder="Choose a dataset" /></SelectTrigger>
                <SelectContent>
                  {targets.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                The datasets you moderate{isAdmin ? ' (an administrator: all)' : ''}, without {dataset ?? 'this one'}.
                A draft or pending snapshot or evidence record stops the move.
              </p>
            </div>
          )}
          {warning && <p className="text-xs text-amber-800 dark:text-amber-300">{warning}</p>}
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <WriteButton onClick={() => void submit()} disabled={busy || !chosen || hasOpenSnapshot || unreviewedRefuses(chosen, isPublic, isAdmin)}>Move</WriteButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
