'use client'

/**
 * Invite one or more email addresses (decision 8.14): admin into any
 * dataset or none, a moderator into their dataset. Each address gets its
 * own single-use link by mail; an address with an account is reported.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { MailPlus, MailWarning, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import RoleCheckboxes, { type DatasetRole } from '@/components/admin/RoleCheckboxes'
import type { DatasetView, InviteResult } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { resendNotice, summariseInvitations } from '@/lib/mailResult'

const NO_DATASET = '__none__'

export default function InviteDialog({
  datasets,
  fixedDataset,
  allowNoDataset = false,
  onInvited,
}: {
  /** Datasets to choose from (ignored with ``fixedDataset``). */
  datasets: DatasetView[]
  fixedDataset?: string
  allowNoDataset?: boolean
  onInvited?: () => void
}) {
  const [open, setOpen] = useState(false)
  const [emails, setEmails] = useState('')
  const [dataset, setDataset] = useState<string>(fixedDataset ?? (allowNoDataset ? NO_DATASET : ''))
  const [roles, setRoles] = useState<DatasetRole[]>(['contributor'])
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<InviteResult[] | null>(null)

  const addresses = emails.split(/[\s,;]+/).map((e) => e.trim()).filter(Boolean)
  const target = fixedDataset ?? (dataset === NO_DATASET ? null : dataset || null)

  const resend = async (failed: InviteResult) => {
    if (!failed.invitation) return
    try {
      const again = await backendJson<InviteResult>(
        `/invitations/${failed.invitation._id}/resend`, { method: 'POST' })
      const notice = resendNotice({ email: failed.email, result: again.result })
      if (notice.warning) toast.warning(notice.text)
      else toast.success(notice.text)
      setResults((rows) => rows && rows.map((row) => (row.email === failed.email ? again : row)))
      onInvited?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Resend failed')
    }
  }

  const submit = async () => {
    setBusy(true)
    try {
      const response = await backendJson<InviteResult[]>('/invitations', {
        method: 'POST',
        body: { emails: addresses, dataset: target, roles: target ? roles : [] },
      })
      setResults(response)
      const summary = summariseInvitations(response)
      if (summary.warning) toast.warning(summary.toast)
      else toast.success(summary.toast)
      setEmails('')
      onInvited?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Invitation failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => { setResults(null); setOpen(true) }}>
        <MailPlus className="mr-2 h-4 w-4" />Invite
      </Button>
      <Dialog open={open} onOpenChange={(next) => { if (!busy) setOpen(next) }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Invite people</DialogTitle>
            <DialogDescription>
              Each address gets its own link by mail. It works once, for that address
              only, and expires after 14 days.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="invite-emails">Email addresses</Label>
              <Textarea
                id="invite-emails"
                rows={3}
                value={emails}
                onChange={(event) => setEmails(event.target.value)}
                placeholder="one or more, separated by commas or new lines"
              />
            </div>
            {!fixedDataset && (
              <div className="space-y-1">
                <Label>Dataset</Label>
                <Select value={dataset} onValueChange={setDataset}>
                  <SelectTrigger className="w-full"><SelectValue placeholder="Choose a dataset" /></SelectTrigger>
                  <SelectContent>
                    {allowNoDataset && <SelectItem value={NO_DATASET}>No dataset (account only)</SelectItem>}
                    {datasets.map((d) => (
                      <SelectItem key={d._id} value={d._id}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {target && (
              <div className="space-y-1">
                <Label>Roles in the dataset</Label>
                <RoleCheckboxes idPrefix="invite-role" value={roles} onChange={setRoles} />
              </div>
            )}
            {results && results.some((r) => r.result === 'mail_failed') && (
              <div role="alert" className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
                <p className="flex items-center gap-2 font-medium text-destructive">
                  <MailWarning className="h-4 w-4" aria-hidden />The mail could not be sent to:
                </p>
                <p className="text-xs text-muted-foreground">
                  The invitations exist. Resend mails a new link; the first one stops working.
                </p>
                <ul className="space-y-1">
                  {results.filter((r) => r.result === 'mail_failed').map((r) => (
                    <li key={r.email} className="flex items-center justify-between gap-2">
                      <span className="break-all">{r.email}</span>
                      <Button size="sm" variant="outline" onClick={() => void resend(r)}>
                        <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />Resend
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {results && results.some((r) => r.result === 'exists') && (
              <p className="text-sm text-muted-foreground">
                Already registered, not invited:{' '}
                {results.filter((r) => r.result === 'exists').map((r) => r.email).join(', ')}.
                Add them in the dataset&apos;s member list instead.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Close</Button>
            <Button
              onClick={() => void submit()}
              disabled={busy || addresses.length === 0 || (!fixedDataset && !allowNoDataset && !dataset)}
            >
              Send {addresses.length > 1 ? `${addresses.length} invitations` : 'invitation'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
