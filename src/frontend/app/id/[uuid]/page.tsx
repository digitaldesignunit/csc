import { headers } from 'next/headers'
import { notFound, redirect } from 'next/navigation'

import ComponentAccessNotice from '@/components/components/ComponentAccessNotice'
import UnknownTag from '@/components/snapshot/UnknownTag'
import type { DatasetView } from '@/generated/AccessModels'
import { uuidFromScan } from '@/lib/scanIds'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * The permanent identifier route (spec section 7.5): `/id/{uuid}` never
 * moves. It leads to the component page, which shows the piece, its
 * tombstone, or the duplicate's canonical piece; a purged piece answers with
 * the 410 page. An id no component has is
 * a 404 --- except for a signed-in caller who contributes to some dataset:
 * they get "this tag is not in the catalog yet" with the two ways to
 * record it (decision 8.87). Nobody else learns anything beyond the 404.
 */
export default async function IdPage({ params }: { params: Promise<{ uuid: string }> }) {
  const { uuid } = await params
  const id = uuidFromScan(uuid)
  if (!id) notFound()

  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`
  const init = { cache: 'no-store' as const, headers: { cookie } }

  const found = await fetch(`${base}/api/backend/identities/${encodeURIComponent(id)}?expand=none`, init)
  // purged: the 410 page of spec 7.5, not a redirect to a page that says the same later
  if (found.status === 410) return <ComponentAccessNotice kind="purged" />
  if (found.status !== 404) redirect(`/components/${id}`)

  // unknown: only a contributor is told what they can do about it
  let contributes = false
  if (cookie) {
    const res = await fetch(`${base}/api/backend/datasets`, init).catch(() => null)
    if (res?.ok) {
      const datasets = (await res.json()) as DatasetView[]
      contributes = Array.isArray(datasets) && datasets.some((d) => d.roles?.includes('contributor'))
    }
  }
  if (!contributes) notFound()
  return <UnknownTag id={id} />
}
