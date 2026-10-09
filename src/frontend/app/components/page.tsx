import BrowseView from '@/components/components/overview/BrowseView'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { parseCirculation } from '@/lib/browse'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type SearchParams = Record<string, string | undefined>

/** The URL parameters that go on to the backend list and count unchanged. */
const FILTER_PARAMS = [
  'original_function',
  'material',
  'dataset',
  'shape_class',
  'complexity',
  'fragment',
  'bbx_min_x',
  'bbx_min_y',
  'bbx_min_z',
  'bbx_max_x',
  'bbx_max_y',
  'bbx_max_z',
  'q',
] as const

/**
 * Browse (plan P11 stage 2, decision 8.118 Q8): signed in or not. An
 * anonymous visitor gets the public tier from the same routes; the circulation
 * switch is `?circulation=` so older links keep working.
 */
export default async function ComponentsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const sp = await searchParams
  const circulation = parseCirculation(sp?.circulation)

  const page = Math.max(1, Number(sp?.page ?? 1) || 1)
  const size = Math.min(200, Math.max(1, Number(sp?.size ?? 20) || 20))
  const sortkey = sp?.sortkey ?? '_id'
  const sortorder: 'asc' | 'desc' = sp?.sortorder === 'desc' ? 'desc' : 'asc'

  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const countParams = new URLSearchParams({ circulation })
  for (const key of FILTER_PARAMS) {
    const value = sp?.[key]
    if (value) countParams.set(key, value)
  }
  const listParams = new URLSearchParams(countParams)
  listParams.set('page', String(page))
  listParams.set('size', String(size))
  listParams.set('sortkey', sortkey)
  listParams.set('sortorder', sortorder)
  listParams.set('expand', 'shallow')

  const fetchOpts = { cache: 'no-store' as const, headers: { cookie } }
  const [itemsRes, countRes] = await Promise.all([
    fetch(`${base}/api/backend/identities?${listParams.toString()}`, fetchOpts),
    fetch(`${base}/api/backend/identities/count?${countParams.toString()}`, fetchOpts),
  ])

  if (itemsRes.status === 401 || countRes.status === 401) {
    redirect('/auth/signin?callbackUrl=%2Fcomponents')
  }
  if (!itemsRes.ok) {
    throw new Error(`Failed to fetch identities: ${itemsRes.status} ${await itemsRes.text()}`)
  }
  if (!countRes.ok) {
    throw new Error(`Failed to fetch identity count: ${countRes.status} ${await countRes.text()}`)
  }

  const rows = (await itemsRes.json()) as CatalogShallowRow[]
  const { count: total } = (await countRes.json()) as { count: number }

  return (
    <BrowseView
      rows={rows}
      total={total}
      page={page}
      size={size}
      circulation={circulation}
      q={sp?.q ?? ''}
      sortkey={sortkey}
      sortorder={sortorder}
      focusSearch={sp?.focus === 'search'}
    />
  )
}
