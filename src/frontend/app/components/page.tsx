import BrowseView from '@/components/components/overview/BrowseView'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { parseCirculation } from '@/lib/browse'
import { fitBackendParams } from '@/lib/fit'
import { nearBackendParams } from '@/lib/near'
import { serverBackend } from '@/lib/serverBackend'
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
  // a usable fit or near search goes on to the backend (an unusable one is
  // left out, the backend would refuse it); the list sorts by the distance of
  // a near search, else the match of a fit, unless another sort is set
  const urlParams = new URLSearchParams(
    Object.entries(sp ?? {}).filter((e): e is [string, string] => typeof e[1] === 'string'))
  const fit = fitBackendParams(urlParams)
  const near = nearBackendParams(urlParams)
  const asked = sp?.sortkey
  // `match` or `distance` without its search (an old link) is no sort: the
  // backend would refuse it
  const usable = !(asked === 'match' && !fit.fit_mode) && !(asked === 'distance' && !near.near_lat)
  const sortkey = asked && usable ? asked : near.near_lat ? 'distance' : fit.fit_mode ? 'match' : '_id'
  const sortorder: 'asc' | 'desc' = sp?.sortorder === 'desc' ? 'desc' : 'asc'

  const countParams = new URLSearchParams({ circulation })
  for (const key of FILTER_PARAMS) {
    const value = sp?.[key]
    if (value) countParams.set(key, value)
  }
  for (const [key, value] of Object.entries({ ...fit, ...near })) countParams.set(key, value)
  const listParams = new URLSearchParams(countParams)
  listParams.set('page', String(page))
  listParams.set('size', String(size))
  listParams.set('sortkey', sortkey)
  listParams.set('sortorder', sortorder)
  listParams.set('expand', 'shallow')

  const [itemsRes, countRes] = await Promise.all([
    serverBackend(`/identities?${listParams.toString()}`),
    serverBackend(`/identities/count?${countParams.toString()}`),
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
