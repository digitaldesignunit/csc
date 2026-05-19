'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import {
  Archive,
  CheckCircle,
  ChevronDown,
  Pencil,
  RotateCcw,
  Trash2,
} from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import ComponentSnapshotGeometryDownload from './ComponentSnapshotGeometryDownload'
import { ExtendedUser, isConsumedShallowRow } from './componentDetailShared'

type ComponentDetailActionsProps = {
  catalog: CatalogComponent
}

export default function ComponentDetailActions({ catalog }: ComponentDetailActionsProps) {
  const { identity, snapshot } = catalog
  const identityId = identity._id ?? ''
  const isConsumed = isConsumedShallowRow({
    consumed_at: identity.consumed_at as string | null | undefined,
  })
  const reservedBy = typeof identity.reserved === 'string' ? identity.reserved : ''

  const router = useRouter()
  const { data: session } = useSession()

  const [validating, setValidating] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showDestructiveActions, setShowDestructiveActions] = useState(false)
  const [archiveConfirmOpen, setArchiveConfirmOpen] = useState(false)
  const [archiveAction, setArchiveAction] = useState<'archive' | 'restore' | null>(null)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)

  const busy = validating || archiving || deleting

  const handleReserveComponent = async () => {
    try {
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/reserve`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        },
      )
      if (response.ok) {
        window.location.reload()
      } else {
        const error = await response.json()
        alert(`Failed to reserve component: ${error.detail || 'Unknown error'}`)
      }
    } catch {
      alert('Failed to reserve component. Please try again.')
    }
  }

  const handleReleaseComponent = async () => {
    try {
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/reserve`,
        {
          method: 'DELETE',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        },
      )
      if (response.ok) {
        window.location.reload()
      } else {
        const error = await response.json()
        alert(`Failed to release component: ${error.detail || 'Unknown error'}`)
      }
    } catch {
      alert('Failed to release component. Please try again.')
    }
  }

  const handleValidateComponent = async () => {
    try {
      setValidating(true)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/validate`,
        { method: 'GET', credentials: 'include' },
      )
      if (response.ok) {
        router.push('/admin/validation')
      } else {
        alert('Failed to validate component. Please try again.')
      }
    } catch {
      alert('Failed to validate component. Please try again.')
    } finally {
      setValidating(false)
    }
  }

  const handleArchiveComponent = async () => {
    try {
      setArchiving(true)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/consume`,
        { method: 'POST', credentials: 'include' },
      )
      if (response.ok) {
        router.refresh()
      } else {
        alert('Failed to archive component. Please try again.')
      }
    } catch {
      alert('Failed to archive component. Please try again.')
    } finally {
      setArchiving(false)
    }
  }

  const handleUnarchiveComponent = async () => {
    try {
      setArchiving(true)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/restore`,
        { method: 'POST', credentials: 'include' },
      )
      if (response.ok) {
        router.refresh()
      } else {
        alert('Failed to restore component. Please try again.')
      }
    } catch {
      alert('Failed to restore component. Please try again.')
    } finally {
      setArchiving(false)
    }
  }

  const openArchiveConfirmation = () => {
    setArchiveAction(isConsumed ? 'restore' : 'archive')
    setArchiveConfirmOpen(true)
  }

  const handleConfirmArchiveAction = async () => {
    const selectedAction = archiveAction
    if (!selectedAction) return
    setArchiveConfirmOpen(false)
    setArchiveAction(null)
    if (selectedAction === 'archive') {
      await handleArchiveComponent()
      return
    }
    await handleUnarchiveComponent()
  }

  const handleDeleteComponent = async () => {
    try {
      setDeleting(true)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}`,
        { method: 'DELETE', credentials: 'include' },
      )
      if (response.ok) {
        router.push('/components')
      } else {
        alert('Failed to delete component. Please try again.')
      }
    } catch {
      alert('Failed to delete component. Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  const handleConfirmDelete = async () => {
    setDeleteConfirmOpen(false)
    await handleDeleteComponent()
  }

  const currentUserId = (session?.user as ExtendedUser)?.id

  return (
    <div className="w-full space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap gap-2">
        <div className="w-full min-w-[8rem] flex-1">
          <ComponentSnapshotGeometryDownload catalog={catalog} />
        </div>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Link href={`/locate-by-id?reference_id=${identityId}`} className="flex-1 min-w-[8rem]">
                <Button variant="outline" className="w-full" size="sm">
                  Locate by ID
                </Button>
              </Link>
            </TooltipTrigger>
            <TooltipContent>Locate this component using the ID workflow</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex-1 min-w-[8rem]">
                {reservedBy ? (
                  currentUserId === reservedBy ? (
                    <Button
                      variant="destructive"
                      className="w-full"
                      size="sm"
                      onClick={handleReleaseComponent}
                    >
                      Release
                    </Button>
                  ) : (
                    <Button variant="destructive" className="w-full" size="sm" disabled>
                      Reserved
                    </Button>
                  )
                ) : (
                  <Button variant="default" className="w-full" size="sm" onClick={handleReserveComponent}>
                    Reserve
                  </Button>
                )}
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {reservedBy
                ? currentUserId === reservedBy
                  ? 'Release this component'
                  : 'Reserved by another user'
                : 'Reserve for your project'}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {session?.user?.role === 'admin' && (
        <div className="space-y-2">
          {!isConsumed && (
            <Link href={`/components/${identityId}/edit`} className="block">
              <Button variant="outline" className="w-full" size="sm" disabled={busy}>
                <Pencil className="h-4 w-4 mr-2" />
                Edit metadata
              </Button>
            </Link>
          )}

          <div className="flex gap-2">
            <Button
              onClick={handleValidateComponent}
              disabled={busy || Boolean(snapshot.validated)}
              variant="default"
              size="sm"
              className="flex-1 bg-green-600 hover:bg-green-700"
            >
              <CheckCircle className="h-4 w-4 mr-2" />
              {snapshot.validated ? 'Validated' : 'Validate'}
            </Button>
            <Button
              onClick={openArchiveConfirmation}
              disabled={busy}
              variant={isConsumed ? 'default' : 'outline'}
              size="sm"
              className="flex-1"
            >
              {isConsumed ? (
                <>
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Restore
                </>
              ) : (
                <>
                  <Archive className="h-4 w-4 mr-2" />
                  Consume
                </>
              )}
            </Button>
          </div>

          <div className="rounded-lg border border-destructive/30 overflow-hidden">
            <button
              type="button"
              onClick={() => setShowDestructiveActions(!showDestructiveActions)}
              className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors"
            >
              <span>Destructive actions</span>
              <ChevronDown
                className={`h-4 w-4 transition-transform ${showDestructiveActions ? 'rotate-180' : ''}`}
              />
            </button>
            {showDestructiveActions && (
              <div className="border-t border-destructive/30 p-3 pt-2">
                <p className="mb-2 text-xs text-muted-foreground">
                  Deleting is permanent. Prefer consume when possible.
                </p>
                <Button
                  onClick={() => setDeleteConfirmOpen(true)}
                  disabled={busy}
                  variant="destructive"
                  size="sm"
                  className="w-full"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Permanently delete
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      <Dialog open={archiveConfirmOpen} onOpenChange={setArchiveConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {isConsumed ? 'Restore identity?' : 'Mark identity as consumed?'}
            </DialogTitle>
            <DialogDescription>
              {isConsumed
                ? 'This will return the identity to the active catalog.'
                : 'This removes the identity from the active catalog. You can restore it later.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setArchiveConfirmOpen(false)
                setArchiveAction(null)
              }}
            >
              Cancel
            </Button>
            <Button
              variant={isConsumed ? 'default' : 'outline'}
              onClick={handleConfirmArchiveAction}
              disabled={busy}
            >
              {isConsumed ? 'Confirm restore' : 'Confirm consume'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Permanently delete component?</DialogTitle>
            <DialogDescription>
              This action cannot be undone. The component and associated files will be removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleConfirmDelete} disabled={busy}>
              Confirm delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
