'use client'

/**
 * The lifecycle buttons of one evidence record (spec 3.3.3, 7.2; decisions
 * 8.18, 8.66): the author submits, recalls, resubmits and deletes;
 * moderator(D) publishes, rejects, withdraws and reinstates; contributor(D)
 * corrects a published record (a new pending record that supersedes it);
 * the author or moderator(D) edits a draft and moderator(D) a pending record
 * (8.127). Only the buttons the caller may use are shown; the backend checks again.
 */
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Archive, ArchiveRestore, Check, MoreHorizontal, Pencil, Send, SquarePen, Trash2, Undo2, X } from 'lucide-react'

import ReasonDialog from '@/components/moderation/ReasonDialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { deleteEvidence, evidenceAction, type EvidenceVerb } from '@/lib/evidence/api'
import { canEditEvidence } from '@/lib/evidence/edit'
import { useMe } from '@/lib/me'

type Props = {
  record: {
    _id: string
    status: string
    recorded_by_user_id: string
    superseded_by?: string | null
    identity_id: string
  }
  dataset: string | null | undefined
  onChanged?: () => void
  size?: 'sm' | 'xs'
  /** `menu`: one "more" button with the actions inside (the record cards of the
   *  component page, 8.118); `buttons`: the row of buttons (queues). */
  variant?: 'buttons' | 'menu'
}

export default function EvidenceLifecycleActions({ record, dataset, onChanged, size = 'xs', variant = 'buttons' }: Props) {
  const router = useRouter()
  const { me, moderates, rolesIn } = useMe()
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState<'reject' | 'withdraw' | null>(null)

  if (!me) return null
  const isAuthor = record.recorded_by_user_id === me._id
  const isModerator = moderates(dataset)
  const isContributor = rolesIn(dataset).includes('contributor')
  const { status } = record
  const live = status === 'published' && !record.superseded_by

  const run = async (label: string, verb: EvidenceVerb, body?: { reason: string }, query = '') => {
    setBusy(true)
    try {
      await evidenceAction(record._id, verb, body, query)
      toast.success(label)
      onChanged?.()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `${label} failed`)
      throw err
    } finally {
      setBusy(false)
    }
  }
  const quiet = (fn: () => Promise<void>) => () => { fn().catch(() => undefined) }

  const remove = async () => {
    if (!window.confirm('Delete this record? This cannot be undone.')) return
    setBusy(true)
    try {
      await deleteEvidence(record._id)
      toast.success('Record deleted')
      onChanged?.()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const buttonClass = size === 'xs' ? 'h-6 px-2 text-[11px]' : 'h-8 px-3 text-xs'
  type Entry = {
    key: string
    label: string
    icon: typeof Send
    run?: () => void
    href?: string
    primary?: boolean
    destructive?: boolean
    iconOnly?: boolean
  }
  const entries: Entry[] = []
  const add = (entry: Entry) => entries.push(entry)

  if ((isAuthor || isModerator) && status === 'draft') {
    add({ key: 'submit', label: 'Submit', icon: Send, primary: true,
      run: quiet(() => run('Submitted for moderation', 'submit')) })
  }
  if (isAuthor && status === 'pending') {
    add({ key: 'recall', label: 'Recall', icon: Undo2, run: quiet(() => run('Recalled to draft', 'recall')) })
  }
  if (isAuthor && status === 'rejected') {
    add({ key: 'resubmit', label: 'Back to draft', icon: Undo2, run: quiet(() => run('Back to draft', 'resubmit')) })
  }
  if (isModerator && status === 'pending') {
    add({ key: 'publish', label: 'Publish', icon: Check, primary: true, run: quiet(() => run('Published', 'publish')) })
    add({ key: 'reject', label: 'Reject', icon: X, run: () => setDialog('reject') })
  }
  if (isModerator && status === 'published') {
    add({ key: 'withdraw', label: 'Withdraw', icon: Archive, run: () => setDialog('withdraw') })
  }
  if (isModerator && status === 'withdrawn') {
    add({ key: 'reinstate', label: 'Reinstate', icon: ArchiveRestore, run: quiet(() => run('Reinstated', 'reinstate')) })
  }
  if (canEditEvidence(status, isAuthor, isModerator)) {
    add({ key: 'edit', label: 'Edit', icon: SquarePen,
      href: `/components/${encodeURIComponent(record.identity_id)}/evidence/new?edit=${encodeURIComponent(record._id)}` })
  }
  if (live && isContributor) {
    add({ key: 'correct', label: 'Correct', icon: Pencil,
      href: `/components/${encodeURIComponent(record.identity_id)}/evidence/new?correct=${encodeURIComponent(record._id)}` })
  }
  if ((isAuthor || isModerator) && ['draft', 'pending', 'rejected'].includes(status)) {
    add({ key: 'delete', label: 'Delete', icon: Trash2, destructive: true, iconOnly: true, run: () => void remove() })
  }

  const buttons: React.ReactNode[] = entries.map((entry) => {
    const Icon = entry.icon
    const inner = <><Icon className={entry.iconOnly ? 'h-3 w-3' : 'mr-1 h-3 w-3'} />{entry.iconOnly ? null : entry.label}</>
    if (entry.href) {
      return (
        <span key={entry.key}>
          <Button asChild size="sm" variant="outline" className={buttonClass}>
            <Link href={entry.href}>{inner}</Link>
          </Button>
        </span>
      )
    }
    return (
      <span key={entry.key}>
        <Button size="sm" variant={entry.primary ? 'default' : entry.destructive ? 'ghost' : 'outline'}
          className={`${buttonClass}${entry.destructive ? ' text-destructive' : ''}`} disabled={busy}
          aria-label={entry.iconOnly ? 'Delete record' : undefined} onClick={entry.run}>
          {inner}
        </Button>
      </span>
    )
  })

  if (entries.length === 0) return null

  const menu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={busy}
          aria-label="Record actions" onClick={(event) => event.stopPropagation()}>
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={(event) => event.stopPropagation()}>
        {entries.map((entry) => {
          const Icon = entry.icon
          const body = <><Icon className="h-4 w-4" /><span className={entry.destructive ? 'text-destructive' : undefined}>{entry.label}</span></>
          return entry.href ? (
            <DropdownMenuItem key={entry.key} asChild><Link href={entry.href}>{body}</Link></DropdownMenuItem>
          ) : (
            <DropdownMenuItem key={entry.key} onSelect={() => entry.run?.()}>{body}</DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <>
      {variant === 'menu' ? menu : <div className="flex flex-wrap items-center gap-1">{buttons}</div>}
      <ReasonDialog
        open={dialog === 'reject'}
        onOpenChange={(open) => setDialog(open ? 'reject' : null)}
        title="Reject this record"
        description="The author sees the reason and can turn the record back into a draft."
        confirmLabel="Reject"
        destructive
        onConfirm={(reason) => run('Rejected', 'reject', { reason })}
      />
      <ReasonDialog
        open={dialog === 'withdraw'}
        onOpenChange={(open) => setDialog(open ? 'withdraw' : null)}
        title="Withdraw this record"
        description="It leaves the lists, the fold and the public view; dataset members keep the full record. If it corrected another record, that record takes its place again."
        confirmLabel="Withdraw"
        destructive
        onConfirm={(reason) => run('Withdrawn', 'withdraw', { reason })}
      />
    </>
  )
}
