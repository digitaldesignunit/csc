'use client'

/**
 * Reads what `parentsRefusePublish` needs (decision 8.8, #46): the rows of the
 * element's versions and the dataset of every parent. A hook for one element
 * (the version list of the page) and a plain function for the moderation
 * queue, which loads details per row.
 */
import { useEffect, useState } from 'react'

import { isFirstPublish, parentsRefusePublish, type ParentLookup } from '@/lib/publishRights'
import { isTombstone } from '@/lib/backend'
import { useMe } from '@/lib/me'

async function readJson(path: string): Promise<{ status: number; body: unknown }> {
  try {
    const response = await fetch(`/api/backend${path}`, { credentials: 'include', cache: 'no-store' })
    const text = await response.text()
    let body: unknown = null
    try {
      body = text ? JSON.parse(text) : null
    } catch {
      body = null
    }
    return { status: response.status, body }
  } catch {
    return { status: 0, body: null }
  }
}

async function lookup(parentId: string): Promise<ParentLookup> {
  const { status, body } = await readJson(`/identities/${encodeURIComponent(parentId)}?expand=none`)
  if (status === 401 || status === 403) return { kind: 'refused' }
  if (status === 200 && isTombstone(body)) return { kind: 'refused' }
  const dataset = (body as { dataset?: unknown } | null)?.dataset
  if (status === 200 && typeof dataset === 'string') return { kind: 'dataset', dataset }
  return { kind: 'gone' }          // 404, 410 or an answer the web cannot read: the backend decides
}

/** Whether this is the first version of the element and which datasets its parents are in. */
export async function loadPublishFacts(identityId: string): Promise<{ first: boolean; parents: ParentLookup[] }> {
  const [identity, rows] = await Promise.all([
    readJson(`/identities/${encodeURIComponent(identityId)}?expand=none`),
    readJson(`/identities/${encodeURIComponent(identityId)}/snapshots`),
  ])
  const parentIds = (identity.body as { parent_identities?: string[] | null } | null)?.parent_identities ?? []
  const first = Array.isArray(rows.body)
    ? isFirstPublish(rows.body as { status?: string | null }[])
    : false                                    // the rows did not load: the backend decides
  if (!first || parentIds.length === 0) return { first, parents: [] }
  return { first, parents: await Promise.all(parentIds.map(lookup)) }
}

export type PublishCheck = { state: 'loading' } | { state: 'ok' } | { state: 'blocked'; reason: string }

/** The check of one element, for a moderator looking at a pending version of it. */
export function usePublishCheck(identityId: string | undefined, enabled: boolean): PublishCheck {
  const { moderates } = useMe()
  const [facts, setFacts] = useState<{ first: boolean; parents: ParentLookup[] } | null>(null)
  useEffect(() => {
    if (!enabled || !identityId) return
    let cancelled = false
    void loadPublishFacts(identityId).then((loaded) => { if (!cancelled) setFacts(loaded) })
    return () => { cancelled = true }
  }, [identityId, enabled])
  if (!enabled || !identityId) return { state: 'ok' }
  if (!facts) return { state: 'loading' }
  const reason = parentsRefusePublish({ ...facts, moderates })
  return reason ? { state: 'blocked', reason } : { state: 'ok' }
}
