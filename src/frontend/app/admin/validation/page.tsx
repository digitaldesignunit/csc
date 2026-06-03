'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  CheckCircle,
  Shield,
  Eye,
  ChevronDown,
  ChevronUp,
  Trash2,
  ExternalLink,
} from 'lucide-react'
import type { CatalogComponent } from '@/generated/CatalogModels'
import type { PendingValidationSnapshotItem } from '@/generated/SnapshotModels'
import ComponentViewer from '@/components/components/ComponentViewer'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { formatTimestamp } from '@/lib/utils'
import { toast } from 'sonner'

type DeleteTarget = {
  snapshotId: string
  identityId: string
}

export default function ValidationPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [pendingSnapshots, setPendingSnapshots] = useState<PendingValidationSnapshotItem[]>([])
  const [loading, setLoading] = useState(true)
  const [validating, setValidating] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [expandedPreviews, setExpandedPreviews] = useState<Set<string>>(new Set())
  const [previewById, setPreviewById] = useState<Record<string, CatalogComponent>>({})
  const [loadingPreviews, setLoadingPreviews] = useState<Set<string>>(new Set())
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null)

  useEffect(() => {
    if (status === 'loading') return

    if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
      router.push('/')
    }
  }, [session, status, router])

  useEffect(() => {
    if (session?.user?.role === 'admin' && !session.error) {
      void fetchPendingSnapshots()
    }
  }, [session])

  const fetchPendingSnapshots = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/backend/snapshots/pending-validation', {
        credentials: 'include',
      })
      if (response.ok) {
        const data = (await response.json()) as PendingValidationSnapshotItem[]
        setPendingSnapshots(data)
      }
    } catch (error) {
      console.error('Failed to fetch pending snapshots:', error)
    } finally {
      setLoading(false)
    }
  }

  const validateSnapshot = async (snapshotId: string) => {
    try {
      setValidating(snapshotId)
      const response = await fetch(
        `/api/backend/snapshots/${encodeURIComponent(snapshotId)}/validate`,
        { method: 'POST', credentials: 'include' },
      )

      if (response.ok) {
        setPendingSnapshots((prev) => prev.filter((row) => row._id !== snapshotId))
        toast.success('Snapshot validated and promoted to live')
      } else {
        console.error('Failed to validate snapshot')
        toast.error('Failed to validate snapshot. Please try again.')
      }
    } catch (error) {
      console.error('Error validating snapshot:', error)
      toast.error('Failed to validate snapshot. Please try again.')
    } finally {
      setValidating(null)
    }
  }

  const rejectSnapshot = async (snapshotId: string) => {
    try {
      setDeleting(snapshotId)
      const response = await fetch(
        `/api/backend/snapshots/${encodeURIComponent(snapshotId)}`,
        { method: 'DELETE', credentials: 'include' },
      )

      if (response.ok) {
        setPendingSnapshots((prev) => prev.filter((row) => row._id !== snapshotId))
        toast.success('Pending snapshot rejected')
      } else {
        const body = await response.json().catch(() => ({}))
        toast.error(
          typeof body.detail === 'string'
            ? body.detail
            : 'Failed to reject snapshot. Please try again.',
        )
      }
    } catch (error) {
      console.error('Error rejecting snapshot:', error)
      toast.error('Failed to reject snapshot. Please try again.')
    } finally {
      setDeleting(null)
    }
  }

  const deleteIdentity = async (identityId: string, snapshotId: string) => {
    try {
      setDeleting(snapshotId)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}`,
        {
          method: 'DELETE',
          credentials: 'include',
        },
      )

      if (response.ok) {
        setPendingSnapshots((prev) => prev.filter((row) => row._id !== snapshotId))
      } else {
        console.error('Failed to delete identity')
        toast.error('Failed to delete component. Please try again.')
      }
    } catch (error) {
      console.error('Error deleting identity:', error)
      toast.error('Failed to delete component. Please try again.')
    } finally {
      setDeleting(null)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    const { identityId, snapshotId } = deleteTarget
    setDeleteTarget(null)
    await deleteIdentity(identityId, snapshotId)
  }

  const fetchComposePreview = async (identityId: string, snapshotId: string) => {
    setLoadingPreviews((prev) => new Set(prev).add(snapshotId))
    try {
      const params = new URLSearchParams({ snapshot_id: snapshotId })
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/compose?${params.toString()}`,
        { credentials: 'include', cache: 'no-store' },
      )
      if (response.ok) {
        const json = (await response.json()) as CatalogComponent
        setPreviewById((prev) => ({
          ...prev,
          [snapshotId]: json,
        }))
      }
    } catch (error) {
      console.error('Failed to fetch compose for preview:', error)
    } finally {
      setLoadingPreviews((prev) => {
        const next = new Set(prev)
        next.delete(snapshotId)
        return next
      })
    }
  }

  const togglePreview = (row: PendingValidationSnapshotItem) => {
    const snapshotId = row._id
    const wasExpanded = expandedPreviews.has(snapshotId)
    setExpandedPreviews((prev) => {
      const next = new Set(prev)
      if (wasExpanded) {
        next.delete(snapshotId)
      } else {
        next.add(snapshotId)
      }
      return next
    })

    if (!wasExpanded && !previewById[snapshotId]) {
      void fetchComposePreview(row.identity_id, snapshotId)
    }
  }

  const displayName = (row: PendingValidationSnapshotItem) => {
    if (typeof row.name === 'string' && row.name.trim().length > 0) {
      return row.name
    }
    if (row.catalog_number != null) {
      return `Component #${row.catalog_number}`
    }
    return `Identity ${row.identity_id.slice(0, 8)}`
  }

  if (status === 'loading') {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </div>
    )
  }

  if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
    return null
  }

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-4 sm:mb-6">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Shield className="h-5 w-5 sm:h-6 sm:w-6 text-primary" />
          <h1 className="text-xl sm:text-2xl font-bold">Validation Dashboard</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          Review pending snapshots before they become the live catalog version
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">{pendingSnapshots.length}</div>
            <p className="text-xs text-muted-foreground">Pending Snapshots</p>
          </div>
        </Card>
      </div>

      <div className="grid gap-6">
        <Card>
          <CardContent className="pt-6">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              </div>
            ) : pendingSnapshots.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <CheckCircle className="h-12 w-12 mx-auto mb-4 text-green-500" />
                <p className="text-lg font-medium">All snapshots are validated!</p>
                <p>No pending snapshots require validation.</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <Button
                    onClick={fetchPendingSnapshots}
                    variant="outline"
                    size="sm"
                    className="w-full sm:w-auto"
                  >
                    Refresh
                  </Button>
                </div>

                <div className="grid gap-4">
                  {pendingSnapshots.map((row) => {
                    const snapshotId = row._id
                    const isNewIdentity = row.version === 0
                    const isVersionUpdate =
                      !isNewIdentity &&
                      row.live_version != null &&
                      row.version > row.live_version

                    return (
                      <div
                        key={snapshotId}
                        className="border rounded-lg hover:bg-muted/50 transition-colors"
                      >
                        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between p-4 gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              <h3 className="font-medium text-sm sm:text-base truncate">
                                <Link
                                  href={`/components/${row.identity_id}`}
                                  className="text-primary hover:text-primary/80 hover:underline inline-flex items-center gap-1 transition-colors"
                                >
                                  {displayName(row)}
                                  <ExternalLink className="h-3 w-3" />
                                </Link>
                              </h3>
                              <Badge variant="secondary" className="text-xs">
                                v{row.version}
                              </Badge>
                              {isNewIdentity && (
                                <Badge variant="outline" className="text-xs">
                                  New identity
                                </Badge>
                              )}
                              {isVersionUpdate && (
                                <Badge variant="outline" className="text-xs">
                                  Update from v{row.live_version}
                                </Badge>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              {row.type && (
                                <Badge variant="secondary" className="text-xs">
                                  {row.type}
                                </Badge>
                              )}
                              {row.material && (
                                <Badge variant="outline" className="text-xs">
                                  {row.material}
                                </Badge>
                              )}
                            </div>
                            <div className="text-xs sm:text-sm text-muted-foreground space-y-1">
                              <p className="break-all">
                                Identity:{' '}
                                <Link
                                  href={`/components/${row.identity_id}`}
                                  className="text-primary hover:underline"
                                >
                                  {row.identity_id}
                                </Link>
                              </p>
                              <p className="break-all">Snapshot: {snapshotId}</p>
                              <p>Submitted: {formatTimestamp(row.created)}</p>
                            </div>
                          </div>

                          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 lg:ml-4 lg:flex-shrink-0">
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    onClick={() => togglePreview(row)}
                                    variant="outline"
                                    size="sm"
                                    className="flex items-center gap-2 w-full sm:w-auto"
                                  >
                                    {loadingPreviews.has(snapshotId) ? (
                                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
                                    ) : (
                                      <Eye className="h-4 w-4" />
                                    )}
                                    {expandedPreviews.has(snapshotId) ? (
                                      <>
                                        <ChevronUp className="h-4 w-4" />
                                        <span className="hidden sm:inline">Hide</span>
                                      </>
                                    ) : (
                                      <>
                                        <ChevronDown className="h-4 w-4" />
                                        <span className="hidden sm:inline">Preview</span>
                                      </>
                                    )}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Preview this pending snapshot in 3D</p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <Button
                              onClick={() => validateSnapshot(snapshotId)}
                              disabled={validating === snapshotId || deleting === snapshotId}
                              size="sm"
                              className="bg-green-600 hover:bg-green-700 w-full sm:w-auto"
                            >
                              {validating === snapshotId ? (
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                              ) : (
                                <>
                                  <CheckCircle className="h-4 w-4 sm:mr-2" />
                                  <span className="hidden sm:inline">Validate</span>
                                </>
                              )}
                            </Button>
                            {isNewIdentity ? (
                              <Button
                                onClick={() =>
                                  setDeleteTarget({
                                    snapshotId,
                                    identityId: row.identity_id,
                                  })
                                }
                                disabled={validating === snapshotId || deleting === snapshotId}
                                size="sm"
                                variant="destructive"
                                className="w-full sm:w-auto"
                              >
                                {deleting === snapshotId ? (
                                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                                ) : (
                                  <>
                                    <Trash2 className="h-4 w-4 sm:mr-2" />
                                    <span className="hidden sm:inline">Delete</span>
                                  </>
                                )}
                              </Button>
                            ) : (
                              <Button
                                onClick={() => rejectSnapshot(snapshotId)}
                                disabled={validating === snapshotId || deleting === snapshotId}
                                size="sm"
                                variant="destructive"
                                className="w-full sm:w-auto"
                              >
                                {deleting === snapshotId ? (
                                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                                ) : (
                                  <>
                                    <Trash2 className="h-4 w-4 sm:mr-2" />
                                    <span className="hidden sm:inline">Reject</span>
                                  </>
                                )}
                              </Button>
                            )}
                          </div>
                        </div>

                        {expandedPreviews.has(snapshotId) && (
                          <div className="p-3 sm:p-4 bg-muted/30 rounded-b-lg border-t">
                            <div className="mb-3">
                              <h4 className="text-sm font-medium text-muted-foreground mb-2">
                                Pending snapshot preview — v{row.version}
                              </h4>
                              <p className="text-xs text-muted-foreground">
                                Interactive 3D view with orbit controls. Use mouse to rotate,
                                scroll to zoom.
                              </p>
                            </div>
                            <div className="h-full w-full">
                              {loadingPreviews.has(snapshotId) ? (
                                <div className="flex items-center justify-center h-full min-h-[200px]">
                                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                                </div>
                              ) : previewById[snapshotId] ? (
                                <ComponentViewer catalog={previewById[snapshotId]} />
                              ) : (
                                <div className="flex items-center justify-center h-full min-h-[200px] text-muted-foreground">
                                  Failed to load snapshot preview
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {deleteTarget && pendingSnapshots.find((r) => r._id === deleteTarget.snapshotId)?.version === 0
                ? 'Permanently delete new component?'
                : 'Reject pending snapshot?'}
            </DialogTitle>
            <DialogDescription>
              {deleteTarget && pendingSnapshots.find((r) => r._id === deleteTarget.snapshotId)?.version === 0
                ? 'This removes the identity and its initial snapshot. Only available for brand-new components that have not been validated yet.'
                : 'This discards the pending snapshot and its uploaded geometry. The live catalog version is unchanged.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={
                !deleteTarget ||
                deleting === deleteTarget.snapshotId
              }
            >
              Confirm Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
