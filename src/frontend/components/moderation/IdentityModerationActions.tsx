'use client'

/**
 * Withdraw or reinstate a whole component (moderator(D); spec section
 * 3.1.4, decisions 8.17, I19). A duplicate names its canonical piece: the
 * permanent link and the component page then lead there. The Actions menu
 * of the component page opens the dialog (8.118).
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import ReasonDialog from '@/components/moderation/ReasonDialog'
import { backendJson } from '@/lib/backend'
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
