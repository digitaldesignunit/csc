const MAX_PHOTO_SLOTS = 32
export const ALLOWED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const

export function snapshotPhotoUrl(snapshotId: string, index: number): string {
  return `/api/backend/snapshots/${encodeURIComponent(snapshotId)}/photos/${index}`
}

export function nextAvailablePhotoIndex(used: Iterable<number>): number | null {
  const taken = new Set(used)
  for (let i = 0; i < MAX_PHOTO_SLOTS; i++) {
    if (!taken.has(i)) return i
  }
  return null
}

export async function uploadSnapshotPhoto(
  snapshotId: string,
  index: number,
  file: File,
): Promise<void> {
  const contentType = (file.type || '').toLowerCase()
  if (!ALLOWED_PHOTO_TYPES.includes(contentType as (typeof ALLOWED_PHOTO_TYPES)[number])) {
    throw new Error('Use JPEG, PNG, or WebP.')
  }

  const form = new FormData()
  form.append('photo', file)
  const res = await fetch(snapshotPhotoUrl(snapshotId, index), {
    method: 'PUT',
    body: form,
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(body || `Upload failed (${res.status})`)
  }
}

export async function uploadSnapshotPhotos(
  snapshotId: string,
  files: File[],
  startIndices?: number[],
): Promise<number> {
  let uploaded = 0
  const used = new Set<number>(startIndices ?? [])

  for (const file of files) {
    const index = nextAvailablePhotoIndex(used)
    if (index === null) {
      throw new Error(`Maximum of ${MAX_PHOTO_SLOTS} photo slots reached.`)
    }
    await uploadSnapshotPhoto(snapshotId, index, file)
    used.add(index)
    uploaded += 1
  }

  return uploaded
}

async function probePhotoIndex(snapshotId: string, index: number): Promise<boolean> {
  const url = snapshotPhotoUrl(snapshotId, index)
  try {
    let res = await fetch(url, {
      method: 'HEAD',
      credentials: 'include',
      cache: 'no-store',
    })
    if (res.status === 405 || res.status === 501) {
      res = await fetch(url, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
      })
    }
    return res.ok
  } catch {
    return false
  }
}

/** Parse ``photo_count`` from compose/list snapshot payloads. */
export function parseSnapshotPhotoCount(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.floor(value))
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const n = parseInt(value, 10)
    if (Number.isFinite(n)) return Math.max(0, n)
  }
  return null
}

const UNKNOWN_COUNT_GAP = 4

/**
 * Resolve occupied photo slot indices.
 *
 * - ``photoCount === 0``: no requests (trust compose-synced count).
 * - ``photoCount > 0``: probe slots in order until that many are found (dense 0..n-1 → n requests).
 * - ``photoCount === null``: short sequential scan with gap early-exit (stale/missing count).
 */
export async function discoverSnapshotPhotoIndices(
  snapshotId: string,
  photoCount?: number | null,
): Promise<number[]> {
  const count = photoCount === undefined ? null : photoCount

  if (count === 0) {
    return []
  }

  const found: number[] = []

  if (count !== null && count > 0) {
    for (let index = 0; index < MAX_PHOTO_SLOTS; index += 1) {
      if (await probePhotoIndex(snapshotId, index)) {
        found.push(index)
      }
      if (found.length >= count) {
        break
      }
    }
    return found
  }

  let gap = 0
  for (let index = 0; index < MAX_PHOTO_SLOTS; index += 1) {
    if (await probePhotoIndex(snapshotId, index)) {
      found.push(index)
      gap = 0
    } else {
      gap += 1
      if (gap >= UNKNOWN_COUNT_GAP) {
        break
      }
    }
  }
  return found
}

export async function deleteSnapshotPhoto(snapshotId: string, index: number): Promise<void> {
  const res = await fetch(snapshotPhotoUrl(snapshotId, index), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok && res.status !== 404) {
    throw new Error(`Delete failed (${res.status})`)
  }
}

export { MAX_PHOTO_SLOTS }
