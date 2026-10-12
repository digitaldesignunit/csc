'use client'

/**
 * "New dataset" (decision 8.139 j): any signed-in account with a verified
 * e-mail address creates a dataset; the id is made from the name (shown as
 * you type) and the creator becomes its moderator and contributor. A new
 * dataset is members only and waits for an administrator's review before it
 * can be visible to all signed-in users or have public pieces. The limit per
 * account is the server's (`CSC_MAX_DATASETS_PER_USER`): its message is shown
 * when it is reached. An administrator may name the id.
 */
import { useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { Field } from '@/components/evidence/controls'
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
import type { DatasetView } from '@/generated/AccessModels'
import { BackendError, backendJson } from '@/lib/backend'
import { REVIEW_EXPLANATION, newDatasetHint, slugFromName } from '@/lib/datasets'
import { useMe } from '@/lib/me'

export default function NewDatasetDialog({
  onCreated,
  variant = 'default',
  label = 'New dataset',
}: {
  onCreated: (slug: string) => void
  variant?: 'default' | 'outline'
  label?: string
}) {
  const { isAdmin, refresh } = useMe()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [slug, setSlug] = useState<string | null>(null)       // an administrator's own id
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = {
        name: name.trim(), description: description.trim() || null, visibility: 'members',
      }
      if (isAdmin && slug !== null && slug.trim()) body._id = slug.trim()
      const made = await backendJson<DatasetView>('/datasets', { method: 'POST', body })
      toast.success(`Dataset ${made.name} created`)
      await refresh()
      setOpen(false)
      setName('')
      setDescription('')
      setSlug(null)
      onCreated(made._id)
    } catch (err) {
      setError(err instanceof BackendError ? err.message : 'Could not create the dataset')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button size="sm" variant={variant} onClick={() => setOpen(true)}>
        <Plus className="mr-2 h-4 w-4" />{label}
      </Button>
      <Dialog open={open} onOpenChange={(next) => { if (!busy) setOpen(next) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New dataset</DialogTitle>
            <DialogDescription>
              A dataset is a project: its members, their roles and who sees its components. You become its
              moderator and can invite people.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Field id="ds-new-name" label="Name" required>
              <Input id="ds-new-name" value={name} maxLength={120} autoFocus
                onChange={(event) => setName(event.target.value)} />
              {isAdmin ? null : <p className="text-xs text-muted-foreground">{newDatasetHint(name)}</p>}
            </Field>
            {isAdmin && (
              <Field id="ds-new-slug" label="Id (administrators may choose it)">
                <Input id="ds-new-slug" value={slug ?? slugFromName(name)} spellCheck={false}
                  onChange={(event) => setSlug(event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))} />
                <p className="text-xs text-muted-foreground">It cannot be changed later; the name can.</p>
              </Field>
            )}
            <Field id="ds-new-description" label="Description">
              <Textarea id="ds-new-description" rows={2} value={description}
                onChange={(event) => setDescription(event.target.value)} />
            </Field>
            <p className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
              {isAdmin
                ? 'A dataset you create is reviewed and members only; you can open it to all signed-in users later.'
                : `Members only. ${REVIEW_EXPLANATION}`}
            </p>
            {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
            <Button onClick={() => void create()} disabled={busy || !name.trim()}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
