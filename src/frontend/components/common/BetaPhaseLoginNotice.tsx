'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { FlaskConical } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const STORAGE_PREFIX = 'csc-beta-login-notice-dismissed'

type Props = {
  message: string
}

export default function BetaPhaseLoginNotice({ message }: Props) {
  const { data: session, status } = useSession()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (status !== 'authenticated' || !session?.user) return

    const userKey =
      session.user.email ||
      session.user.name ||
      (session.user as { id?: string }).id ||
      'user'
    const storageKey = `${STORAGE_PREFIX}:${userKey}`

    if (localStorage.getItem(storageKey) === 'true') return

    setOpen(true)
  }, [session, status])

  const handleDismiss = () => {
    if (session?.user) {
      const userKey =
        session.user.email ||
        session.user.name ||
        (session.user as { id?: string }).id ||
        'user'
      localStorage.setItem(`${STORAGE_PREFIX}:${userKey}`, 'true')
    }
    setOpen(false)
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) handleDismiss()
    else setOpen(true)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-amber-600" />
            Beta phase
          </DialogTitle>
          <DialogDescription className="text-left text-sm leading-relaxed text-foreground/90">
            {message}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={handleDismiss} className="w-full sm:w-auto">
            Got it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
