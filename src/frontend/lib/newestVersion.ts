/**
 * An element with no current version (every version withdrawn, or none
 * published yet) has an empty passport at `GET /identities/{id}/compose`. The
 * page and the two forms then start from the newest row of
 * `GET /identities/{id}/snapshots` and read it with `?snapshots=<id>`
 * (decision 8.193, reviewer F1 and F2 of 0.6.4.5).
 */
import { backendJson } from '@/lib/backend'
import type { CatalogComponent } from '@/generated/CatalogModels'

export type VersionRowLike = { _id: string; version: number; status?: string | null }

/**
 * The newest row by version number. With `publishedOnly` only a row that was
 * published once counts (`published` or `withdrawn`): evidence is about a
 * state that was published.
 */
export function newestVersionRow<T extends VersionRowLike>(
  rows: readonly T[],
  options: { publishedOnly?: boolean } = {},
): T | undefined {
  const counted = options.publishedOnly
    ? rows.filter((row) => row.status === 'published' || row.status === 'withdrawn')
    : rows
  return [...counted].sort((a, b) => b.version - a.version)[0]
}

/**
 * The passport of the newest version of an element whose first passport had no
 * state, or `first` when there is no such version or it cannot be read (the
 * caller sees the element but not that version).
 */
export async function passportOfNewestVersion(
  identityId: string,
  first: CatalogComponent,
  options: { publishedOnly?: boolean } = {},
): Promise<CatalogComponent> {
  try {
    const rows = await backendJson<VersionRowLike[]>(`/identities/${encodeURIComponent(identityId)}/snapshots`)
    const row = newestVersionRow(rows, options)
    if (!row) return first
    return await backendJson<CatalogComponent>(
      `/identities/${encodeURIComponent(identityId)}/compose?snapshots=${encodeURIComponent(row._id)}`,
    )
  } catch {
    return first
  }
}
