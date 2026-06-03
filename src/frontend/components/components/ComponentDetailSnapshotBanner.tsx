import Link from 'next/link'
import { Eye } from 'lucide-react'

type ComponentDetailSnapshotBannerProps = {
  identityId: string
  viewingVersion: number
  liveVersion: number
  isPending: boolean
}

export default function ComponentDetailSnapshotBanner({
  identityId,
  viewingVersion,
  liveVersion,
  isPending,
}: ComponentDetailSnapshotBannerProps) {
  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 text-sm text-blue-950 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-100 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-start gap-2">
        <Eye className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p className="font-medium">
            Viewing snapshot v{viewingVersion}
            {isPending ? ' (pending approval)' : ''}
          </p>
          <p className="mt-0.5 text-xs text-blue-900/90 dark:text-blue-100/90">
            Live catalog version is v{liveVersion}. Geometry and metadata below
            reflect this historical snapshot.
          </p>
        </div>
      </div>
      <Link
        href={`/components/${encodeURIComponent(identityId)}`}
        className="shrink-0 text-sm font-medium underline underline-offset-4 hover:no-underline"
      >
        Back to live (v{liveVersion})
      </Link>
    </div>
  )
}
