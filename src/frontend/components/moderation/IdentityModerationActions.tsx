'use client'

/**
 * Withdraw or reinstate a whole component (moderator(D); spec section
 * 3.1.4, decisions 8.17, I19). A duplicate names its canonical piece: the
 * permanent link and the component page then lead there.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Archive, ArchiveRestore } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import ReasonDialog from '@/components/moderation/ReasonDialog'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'
import { uuidFromScan } from '@/lib/scanIds'

type Props = {
  identityId: string
  dataset: string | null | undefined
  withdrawn: boolean
}

export default function IdentityModerationActions({ identityId, dataset, withdrawn }: Props) {
  const router = useRouter()
  const { moderates } = useMe()
  const [open, setOpen] = useState(false)
  const [duplicate, setDuplicate] = useState('')
  const [busy, setBusy] = useState(false)

  if (!moderates(dataset)) return null

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

  const reinstate = async () => {
    setBusy(true)
    try {
      await backendJson(`/identities/${identityId}/reinstate`, { method: 'POST' })
      toast.success('Component reinstated')
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Reinstate failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Moderation
      </span>
      {withdrawn ? (
        <Button size="sm" variant="outline" className="h-8 text-xs" disabled={busy}
          onClick={() => void reinstate()}>
          <ArchiveRestore className="mr-1 h-3.5 w-3.5" />Reinstate component
        </Button>
      ) : (
        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => setOpen(true)}>
          <Archive className="mr-1 h-3.5 w-3.5" />Withdraw component
        </Button>
      )}
      <ReasonDialog
        open={open}
        onOpenChange={setOpen}
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
    </div>
  )
}
