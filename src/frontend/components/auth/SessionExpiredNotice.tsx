'use client'

import { useSearchParams } from 'next/navigation'
import { AlertCircle } from 'lucide-react'

export default function SessionExpiredNotice() {
  const searchParams = useSearchParams()
  const error = searchParams.get('error')

  if (error !== 'SessionExpired') {
    return null
  }

  return (
    <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg">
      <div className="flex items-center gap-2">
        <AlertCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
        <p className="text-sm text-amber-800 dark:text-amber-200">
          Your session has expired for security reasons. Please sign in again to continue.
        </p>
      </div>
    </div>
  )
}
