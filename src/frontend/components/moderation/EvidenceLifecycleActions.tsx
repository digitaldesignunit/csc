'use client'

/**
 * The lifecycle buttons of one evidence record (spec 3.3.3, 7.2; decisions
 * 8.18, 8.66): the author submits, recalls, resubmits and deletes;
 * moderator(D) publishes, rejects, withdraws and reinstates; contributor(D)
 * corrects a published record (a new pending record that supersedes it).
 * Only the buttons the caller may use are shown; the backend checks again.
 */
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Archive, ArchiveRestore, Check, Pencil, Send, Trash2, Undo2, X } from 'lucide-react'

import ReasonDialog from '@/components/moderation/ReasonDialog'
import { Button } from '@/components/ui/button'
import { deleteEvidence, evidenceAction, type EvidenceVerb } from '@/lib/evidence/api'
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
}

export default function EvidenceLifecycleActions({ record, dataset, onChanged, size = 'xs' }: Props) {
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
  const buttons: React.ReactNode[] = []
  const add = (key: string, node: React.ReactNode) => buttons.push(<span key={key}>{node}</span>)

  if ((isAuthor || isModerator) && status === 'draft') {
    add('submit', (
      <Button size="sm" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('Submitted for moderation', 'submit'))}>
        <Send className="mr-1 h-3 w-3" />Submit
      </Button>
    ))
    if (isModerator) {
      add('submit-publish', (
        <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
          onClick={quiet(() => run('Submitted and published', 'submit', undefined, '?publish=1'))}>
          <Check className="mr-1 h-3 w-3" />Submit and publish
        </Button>
      ))
    }
  }
  if (isAuthor && status === 'pending') {
    add('recall', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('Recalled to draft', 'recall'))}>
        <Undo2 className="mr-1 h-3 w-3" />Recall
      </Button>
    ))
  }
  if (isAuthor && status === 'rejected') {
    add('resubmit', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('Back to draft', 'resubmit'))}>
        <Undo2 className="mr-1 h-3 w-3" />Back to draft
      </Button>
    ))
  }
  if (isModerator && status === 'pending') {
    add('publish', (
      <Button size="sm" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('Published', 'publish'))}>
        <Check className="mr-1 h-3 w-3" />Publish
      </Button>
    ))
    add('reject', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={() => setDialog('reject')}>
        <X className="mr-1 h-3 w-3" />Reject
      </Button>
    ))
  }
  if (isModerator && status === 'published') {
    add('withdraw', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={() => setDialog('withdraw')}>
        <Archive className="mr-1 h-3 w-3" />Withdraw
      </Button>
    ))
  }
  if (isModerator && status === 'withdrawn') {
    add('reinstate', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('Reinstated', 'reinstate'))}>
        <ArchiveRestore className="mr-1 h-3 w-3" />Reinstate
      </Button>
    ))
  }
  if (live && isContributor) {
    add('correct', (
      <Button asChild size="sm" variant="outline" className={buttonClass}>
        <Link href={`/components/${encodeURIComponent(record.identity_id)}/evidence/new?correct=${encodeURIComponent(record._id)}`}>
          <Pencil className="mr-1 h-3 w-3" />Correct
        </Link>
      </Button>
    ))
  }
  if ((isAuthor || isModerator) && ['draft', 'pending', 'rejected'].includes(status)) {
    add('delete', (
      <Button size="sm" variant="ghost" className={`${buttonClass} text-destructive`} disabled={busy}
        onClick={() => void remove()} aria-label="Delete record">
        <Trash2 className="h-3 w-3" />
      </Button>
    ))
  }

  if (buttons.length === 0) return null

  return (
    <>
      <div className="flex flex-wrap items-center gap-1">{buttons}</div>
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
