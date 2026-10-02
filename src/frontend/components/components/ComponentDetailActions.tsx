'use client'

import Link from 'next/link'
import { useSession } from 'next-auth/react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import ComponentSnapshotGeometryDownload from './ComponentSnapshotGeometryDownload'
import { toast } from 'sonner'
import { ExtendedUser, isOutOfCirculation } from './componentDetailShared'
import IdentityModerationActions from '@/components/moderation/IdentityModerationActions'
import { useMe } from '@/lib/me'

type ComponentDetailActionsProps = {
  catalog: CatalogComponent
}

/**
 * Download, locate, reserve / release, and for moderator(D) the
 * withdrawal of the whole component (plan P3). Exit and editing return with
 * plan P4 / P7.
 */
export default function ComponentDetailActions({ catalog }: ComponentDetailActionsProps) {
  const { identity } = catalog
  const identityId = identity._id ?? ''
  const outOfCirculation = isOutOfCirculation(identity)
  const reservedBy = typeof identity.reserved === 'string' ? identity.reserved : ''

  const { data: session } = useSession()
  const { moderates } = useMe()
  const canRelease = (userId: string | undefined) =>
    !!reservedBy && (userId === reservedBy || moderates(identity.dataset))

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
        toast.error(`Failed to reserve component: ${error.detail || 'Unknown error'}`)
      }
    } catch {
      toast.error('Failed to reserve component. Please try again.')
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
        toast.error(`Failed to release component: ${error.detail || 'Unknown error'}`)
      }
    } catch {
      toast.error('Failed to release component. Please try again.')
    }
  }

  const currentUserId = (session?.user as ExtendedUser)?.id

  if (!session?.user) {
    return null
  }

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
                <Button variant="outline" className="h-8 w-full text-xs" size="sm">
                  Locate by ID
                </Button>
              </Link>
            </TooltipTrigger>
            <TooltipContent>Locate this component using the ID workflow</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {!outOfCirculation && <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex-1 min-w-[8rem]">
                {reservedBy ? (
                  canRelease(currentUserId) ? (
                    <Button
                      variant="destructive"
                      className="h-8 w-full text-xs"
                      size="sm"
                      onClick={handleReleaseComponent}
                    >
                      Release
                    </Button>
                  ) : (
                    <Button variant="destructive" className="h-8 w-full text-xs" size="sm" disabled>
                      Reserved
                    </Button>
                  )
                ) : (
                  <Button variant="default" className="h-8 w-full text-xs" size="sm" onClick={handleReserveComponent}>
                    Reserve
                  </Button>
                )}
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {reservedBy
                ? canRelease(currentUserId)
                  ? currentUserId === reservedBy
                    ? 'Release this component'
                    : 'Release this reservation (moderator)'
                  : 'Reserved by another user'
                : 'Reserve for your project'}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>}
      </div>

      <IdentityModerationActions
        identityId={identityId}
        dataset={identity.dataset}
        withdrawn={Boolean(identity.withdrawn)}
      />
    </div>
  )
}
