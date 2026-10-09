'use client'

import { useEffect } from 'react'
import { recordRecentComponent, useRecentUserId } from '@/lib/recentComponents'

/**
 * Adds the open component page to the signed-in user's Recent list (8.29,
 * 8.86); an anonymous visitor's page views are not recorded.
 */
export default function RecordRecentComponent({ id, label }: { id: string; label: string }) {
  const userId = useRecentUserId()
  useEffect(() => {
    if (userId) recordRecentComponent(userId, { id, label })
  }, [userId, id, label])
  return null
}
