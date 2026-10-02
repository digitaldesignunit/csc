'use client'

/**
 * The lifecycle buttons of one snapshot (spec section 7.1, decisions 8.18,
 * 8.30): the author submits, recalls, resubmits and deletes a draft;
 * moderator(D) publishes, rejects, makes current, withdraws and
 * reinstates. Only the buttons the caller may use are shown; the backend
 * checks again.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import {
  Archive,
  ArchiveRestore,
  Check,
  Send,
  Star,
  Trash2,
  Undo2,
  X,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import ReasonDialog from '@/components/moderation/ReasonDialog'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'

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
}

export default function SnapshotLifecycleActions({ snapshot, dataset, onChanged, size = 'xs' }: Props) {
  const router = useRouter()
  const { me, moderates } = useMe()
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState<'reject' | 'withdraw' | null>(null)

  if (!me) return null
  const isAuthor = !!snapshot.added_by_user_id && snapshot.added_by_user_id === me._id
  const isModerator = moderates(dataset)
  const { status } = snapshot
  const live = status === 'published' && !snapshot.superseded_by

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
    if (!window.confirm(`Delete v${snapshot.version} and its files? This cannot be undone.`)) return
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
  const add = (key: string, node: React.ReactNode) => buttons.push(<span key={key}>{node}</span>)
  const quiet = (fn: () => Promise<void>) => () => { fn().catch(() => undefined) }

  if (isAuthor && status === 'draft') {
    add('submit', (
      <Button size="sm" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('submitted', `${base}/submit`))}>
        <Send className="mr-1 h-3 w-3" />Submit
      </Button>
    ))
  }
  if (isAuthor && status === 'pending') {
    add('recall', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('recalled to draft', `${base}/recall`))}>
        <Undo2 className="mr-1 h-3 w-3" />Recall
      </Button>
    ))
  }
  if (isAuthor && status === 'rejected') {
    add('resubmit', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('back to draft', `${base}/resubmit`))}>
        <Undo2 className="mr-1 h-3 w-3" />Back to draft
      </Button>
    ))
  }
  if (isModerator && status === 'pending') {
    add('publish', (
      <Button size="sm" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('published', `${base}/publish?promote=1`))}>
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
  if (isModerator && live && !snapshot.is_current) {
    add('promote', (
      <Button size="sm" variant="outline" className={buttonClass} disabled={busy}
        onClick={quiet(() => run('made current', `${base}/promote`))}>
        <Star className="mr-1 h-3 w-3" />Make current
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
        onClick={quiet(() => run('reinstated', `${base}/reinstate`))}>
        <ArchiveRestore className="mr-1 h-3 w-3" />Reinstate
      </Button>
    ))
  }
  if ((isAuthor || isModerator) && ['draft', 'pending', 'rejected'].includes(status)) {
    add('delete', (
      <Button size="sm" variant="ghost" className={`${buttonClass} text-destructive`} disabled={busy}
        onClick={() => void remove()} aria-label={`Delete v${snapshot.version}`}>
        <Trash2 className="h-3 w-3" />
      </Button>
    ))
  }

  if (buttons.length === 0) return null

  return (
    <>
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
        description="It leaves lists and the public view; dataset members keep the full record. If it is the current state, the latest remaining published version becomes current."
        confirmLabel="Withdraw"
        destructive
        onConfirm={(reason) => run('withdrawn', `${base}/withdraw`, { reason })}
      />
    </>
  )
}

