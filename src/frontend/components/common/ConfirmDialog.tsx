'use client'

/**
 * `window.confirm` as a shadcn AlertDialog (decision 8.134 / plan D1 item 5):
 * `const { confirm, dialog } = useConfirm()`, render `{dialog}` once, and
 * `if (!(await confirm({ title, description }))) return` where the browser's
 * own box was. The dialog says what happens and has a cancel; a destructive
 * confirm is coloured as one.
 */
import { useCallback, useRef, useState } from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type ConfirmOptions = {
  title: string
  description?: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** a delete or another thing that cannot be undone */
  destructive?: boolean
}

export function useConfirm(): {
  confirm: (options: ConfirmOptions) => Promise<boolean>
  dialog: React.ReactNode
} {
  const [options, setOptions] = useState<ConfirmOptions | null>(null)
  const resolver = useRef<((answer: boolean) => void) | null>(null)

  const settle = useCallback((answer: boolean) => {
    resolver.current?.(answer)
    resolver.current = null
    setOptions(null)
  }, [])

  const confirm = useCallback((next: ConfirmOptions) => {
    // a second question while one is open answers the first with "no"
    resolver.current?.(false)
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve
      setOptions(next)
    })
  }, [])

  const dialog = (
    <AlertDialog open={options !== null} onOpenChange={(open) => { if (!open) settle(false) }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{options?.title}</AlertDialogTitle>
          {options?.description ? (
            <AlertDialogDescription asChild>
              <div className="text-sm text-muted-foreground">{options.description}</div>
            </AlertDialogDescription>
          ) : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{options?.cancelLabel ?? 'Cancel'}</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => settle(true)}
            className={cn(options?.destructive && buttonVariants({ variant: 'destructive' }))}
          >
            {options?.confirmLabel ?? (options?.destructive ? 'Delete' : 'Continue')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
  return { confirm, dialog }
}
