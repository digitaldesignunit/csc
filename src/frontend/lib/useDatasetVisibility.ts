'use client'

/**
 * The visibility of a dataset (`members` or `catalog`) for the "Not public"
 * notice (decision 8.131 e): from the caller's memberships when they are a
 * member, else from `GET /datasets/{id}` (open to everyone who can see the
 * piece). Nothing is fetched unless `enabled`.
 */
import { useEffect, useState } from 'react'

import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'

type Visibility = 'members' | 'catalog'

export function useDatasetVisibility(dataset: string | null | undefined, enabled: boolean): Visibility | null {
  const { me } = useMe()
  const fromMe = me?.memberships.find((m) => m.dataset === dataset)?.visibility ?? null
  const [fetched, setFetched] = useState<{ dataset: string; visibility: Visibility } | null>(null)

  useEffect(() => {
    if (!enabled || !dataset || fromMe) return
    let cancelled = false
    backendJson<{ visibility: Visibility }>(`/datasets/${encodeURIComponent(dataset)}`)
      .then((body) => { if (!cancelled) setFetched({ dataset, visibility: body.visibility }) })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [dataset, enabled, fromMe])

  if (fromMe) return fromMe
  return fetched && fetched.dataset === dataset ? fetched.visibility : null
}
