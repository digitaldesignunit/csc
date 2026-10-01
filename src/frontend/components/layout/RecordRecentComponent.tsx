'use client'

import { useEffect } from 'react'
import { recordRecentComponent } from '@/lib/recentComponents'

/** Adds the open component page to the sidebar's Recent list (8.29). */
export default function RecordRecentComponent({ id, label }: { id: string; label: string }) {
  useEffect(() => {
    recordRecentComponent({ id, label })
  }, [id, label])
  return null
}
