'use client'

/**
 * Confirmation before something becomes public (decision 8.131 c): says what
 * anonymous visitors then see. Making things private needs none.
 */
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
import { PUBLIC_EXPOSES } from '@/lib/publicSwitch'

export default function PublicConfirmDialog({
  open,
  onOpenChange,
  title,
  subject,
  confirmLabel = 'Make public',
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  /** What becomes public, one sentence: "This piece becomes public." */
  subject: string
  confirmLabel?: string
  onConfirm: () => void
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>{subject} Anyone without an account then sees:</p>
              <ul className="list-disc space-y-1 pl-5">
                {PUBLIC_EXPOSES.map((line) => <li key={line}>{line}</li>)}
              </ul>
              <p>You can make it private again at any time.</p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{confirmLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
