'use client'

/**
 * The lifecycle buttons of one snapshot (spec section 7.1, decisions 8.18,
 * 8.30): the author (and a site admin, 6.5) submits, recalls and resubmits, the
 * author or a moderator deletes a draft; moderator(D) publishes, rejects,
 * makes current, withdraws and reinstates. Which buttons show is
 * `snapshotButtons` (`lib/lifecycleRights.ts`); the backend checks again.
 */
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import {
  Archive,
  ArchiveRestore,
  Check,
  FilePen,
  Send,
  Star,
  Trash2,
  Undo2,
  X,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { WriteButton } from '@/components/ui/write-button'
import ReasonDialog from '@/components/moderation/ReasonDialog'
import { backendJson } from '@/lib/backend'
import { snapshotButtons } from '@/lib/lifecycleRights'
import { useMe } from '@/lib/me'
import { usePublishCheck } from '@/lib/publishCheck'
import { useConfirm } from '@/components/common/ConfirmDialog'

export type LifecycleSnapshot = {
  _id: string
  version: number
  status: string
  is_current?: boolean
  superseded_by?: string | null
  added_by_user_id?: string | null
}

type Props = {
  snapshot: LifecycleSnapshot
  dataset: string | null | undefined
  /** Called after a successful action (the page also refreshes). */
  onChanged?: () => void
  size?: 'sm' | 'xs'
  /** The component, for the link to the correction form (spec 7.6). */
  identityId?: string
  /** Offer only these buttons (the Actions menu asks for a version per action). */
  only?: SnapshotAction[]
  /** `has_open_snapshot` of the element (8.195): "Back to draft" and "Correct" wait while one is open. */
  hasOpenSnapshot?: boolean
  /** the element is withdrawn: submit, publish, promote and correct are not offered (8.190) */
  identityWithdrawn?: boolean
}

export type SnapshotAction =
  | 'submit' | 'recall' | 'resubmit' | 'publish' | 'reject' | 'correct'
  | 'promote' | 'withdraw' | 'reinstate' | 'delete'

export default function SnapshotLifecycleActions({ snapshot, dataset, onChanged, size = 'xs', identityId, only, hasOpenSnapshot = false, identityWithdrawn = false }: Props) {
  const router = useRouter()
  const { me, isAdmin, moderates, rolesIn } = useMe()
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState<'reject' | 'withdraw' | null>(null)
  const { confirm, dialog: confirmDialog } = useConfirm()
  // the first version of a child also needs a moderator of every parent dataset (8.8)
  const publishCheck = usePublishCheck(
    identityId, !!me && snapshot.status === 'pending' && moderates(dataset))

  if (!me) return null
  const isAuthor = !!snapshot.added_by_user_id && snapshot.added_by_user_id === me._id
  const isModerator = moderates(dataset)
  const { status } = snapshot
  const show = snapshotButtons({
    isAuthor, isAdmin, isModerator, isContributor: rolesIn(dataset).includes('contributor'),
    status, superseded: !!snapshot.superseded_by, isCurrent: !!snapshot.is_current, hasOpenSnapshot, identityWithdrawn,
    // until the parents answered, the button is not offered
    publishBlock: publishCheck.state === 'blocked' ? publishCheck.reason
      : publishCheck.state === 'loading' ? 'loading' : null,
  })

  const run = async (label: string, path: string, body?: unknown) => {
    setBusy(true)
    try {
      await backendJson(path, { method: 'POST', body })
      toast.success(`v${snapshot.version}: ${label}`)
      onChanged?.()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `${label} failed`)
      throw err
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!(await confirm({
      title: `Delete v${snapshot.version}?`,
      description: 'The snapshot and its files are deleted. This cannot be undone.',
      confirmLabel: 'Delete',
      destructive: true,
    }))) return
    setBusy(true)
    try {
      await backendJson(`/snapshots/${snapshot._id}`, { method: 'DELETE' })
      toast.success(`v${snapshot.version} deleted`)
      onChanged?.()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const base = `/snapshots/${snapshot._id}`
  const buttonClass = size === 'xs' ? 'h-6 px-2 text-[11px]' : 'h-8 px-3 text-xs'
  const buttons: React.ReactNode[] = []
  const add = (key: SnapshotAction, node: React.ReactNode) => {
    if (!only || only.includes(key)) buttons.push(<span key={key}>{node}</span>)
  }
  const quiet = (fn: () => Promise<void>) => () => { fn().catch(() => undefined) }

  if (show.submit) {
    add('submit', (
      <WriteButton size="sm" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('submitted', `${base}/submit`))}>
        <Send className="mr-1 h-3 w-3" />Submit
      </WriteButton>
    ))
  }
  if (show.recall) {
    add('recall', (
      <WriteButton size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('recalled to draft', `${base}/recall`))}>
        <Undo2 className="mr-1 h-3 w-3" />Recall
      </WriteButton>
    ))
  }
  if (show.resubmit) {
    add('resubmit', (
      <WriteButton size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('back to draft', `${base}/resubmit`))}>
        <Undo2 className="mr-1 h-3 w-3" />Back to draft
      </WriteButton>
    ))
  }
  if (publishCheck.state === 'blocked' && isModerator && status === 'pending' && (!only || only.includes('publish'))) {
    buttons.push(<span key="publish-blocked" role="note" className="text-[11px] text-muted-foreground">{publishCheck.reason}</span>)
  }
  if (show.publish) {
    add('publish', (
      <WriteButton size="sm" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('published', `${base}/publish?promote=1`))}>
        <Check className="mr-1 h-3 w-3" />Publish
      </WriteButton>
    ))
  }
  if (show.reject) {
    add('reject', (
      <WriteButton size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={() => setDialog('reject')}>
        <X className="mr-1 h-3 w-3" />Reject
      </WriteButton>
    ))
  }
  if (identityId && show.correct) {
    add('correct', (
      <Button asChild size="sm" variant="outline" className={buttonClass}>
        <Link href={`/components/${encodeURIComponent(identityId)}/snapshot/new?${new URLSearchParams({ mode: 'correct', snapshot: snapshot._id })}`}>
          <FilePen className="mr-1 h-3 w-3" />Correct
        </Link>
      </Button>
    ))
  }
  if (show.promote) {
    add('promote', (
      <WriteButton size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('made current', `${base}/promote`))}>
        <Star className="mr-1 h-3 w-3" />Make current
      </WriteButton>
    ))
  }
  if (show.withdraw) {
    add('withdraw', (
      <WriteButton size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={() => setDialog('withdraw')}>
        <Archive className="mr-1 h-3 w-3" />Withdraw
      </WriteButton>
    ))
  }
  if (show.reinstate) {
    add('reinstate', (
      <WriteButton size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('reinstated', `${base}/reinstate`))}>
        <ArchiveRestore className="mr-1 h-3 w-3" />Reinstate
      </WriteButton>
    ))
  }
  if (show.delete) {
    add('delete', (
      <WriteButton size="sm" variant="ghost" className={`${buttonClass} text-destructive`} disabled={busy}
        onClick={() => void remove()} aria-label={`Delete v${snapshot.version}`}>
        <Trash2 className="h-3 w-3" />
      </WriteButton>
    ))
  }

  if (buttons.length === 0) return null

  return (
    <>
      {confirmDialog}
      <div className="flex flex-wrap items-center gap-1" onClick={(event) => event.stopPropagation()}>
        {buttons}
      </div>
      <ReasonDialog
        open={dialog === 'reject'}
        onOpenChange={(open) => setDialog(open ? 'reject' : null)}
        title={`Reject v${snapshot.version}`}
        description="The author sees the reason and can turn it back into a draft."
        confirmLabel="Reject"
        destructive
        onConfirm={(reason) => run('rejected', `${base}/reject`, { reason })}
      />
      <ReasonDialog
        open={dialog === 'withdraw'}
        onOpenChange={(open) => setDialog(open ? 'withdraw' : null)}
        title={`Withdraw v${snapshot.version}`}
        description="It leaves lists and the public view; dataset members keep the full record. If it is the current snapshot, the latest remaining published snapshot becomes current."
        confirmLabel="Withdraw"
        destructive
        onConfirm={(reason) => run('withdrawn', `${base}/withdraw`, { reason })}
      />
    </>
  )
}

