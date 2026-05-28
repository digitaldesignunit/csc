const MAX_PHOTO_SLOTS = 32
export const ALLOWED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const

const PHOTO_EXTENSION_TO_MIME: Record<string, (typeof ALLOWED_PHOTO_TYPES)[number]> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
}

function extensionMimeType(filename: string): (typeof ALLOWED_PHOTO_TYPES)[number] | null {
  const match = filename.trim().toLowerCase().match(/\.([a-z0-9]+)$/)
  if (!match) return null
  return PHOTO_EXTENSION_TO_MIME[match[1]] ?? null
}

/** Resolve MIME from file.type and filename (gallery picks often omit type). */
export function resolvePhotoMimeType(file: File): (typeof ALLOWED_PHOTO_TYPES)[number] | null {
  const raw = (file.type || '').split(';', 1)[0].trim().toLowerCase()
  if (raw === 'image/jpg' || raw === 'image/pjpeg') return 'image/jpeg'
  if (ALLOWED_PHOTO_TYPES.includes(raw as (typeof ALLOWED_PHOTO_TYPES)[number])) {
    return raw as (typeof ALLOWED_PHOTO_TYPES)[number]
  }
  return extensionMimeType(file.name)
}

export function isAllowedPhotoFile(file: File): boolean {
  return resolvePhotoMimeType(file) !== null
}

/** Ensure upload FormData has a valid image MIME (some OS pickers leave type empty). */
export function normalizePhotoFile(file: File): File {
  const mime = resolvePhotoMimeType(file)
  if (!mime) {
    throw new Error('Use JPEG, PNG, or WebP.')
  }
  if (file.type === mime) return file
  return new File([file], file.name, { type: mime, lastModified: file.lastModified })
}

export type SnapshotPhotoMutationResult = {
  photoCount?: number
}

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
): Promise<SnapshotPhotoMutationResult> {
  const normalized = normalizePhotoFile(file)

  const form = new FormData()
  form.append('photo', normalized)
  const res = await fetch(snapshotPhotoUrl(snapshotId, index), {
    method: 'PUT',
    body: form,
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(body || `Upload failed (${res.status})`)
  }
  try {
    const data = (await res.json()) as { photo_count?: unknown }
    const photoCount = parseSnapshotPhotoCount(data.photo_count)
    return photoCount === null ? {} : { photoCount }
  } catch {
    return {}
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

export async function deleteSnapshotPhoto(
  snapshotId: string,
  index: number,
): Promise<SnapshotPhotoMutationResult> {
  const res = await fetch(snapshotPhotoUrl(snapshotId, index), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok && res.status !== 404) {
    throw new Error(`Delete failed (${res.status})`)
  }
  try {
    const data = (await res.json()) as { photo_count?: unknown }
    const photoCount = parseSnapshotPhotoCount(data.photo_count)
    return photoCount === null ? {} : { photoCount }
  } catch {
    return {}
  }
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

export { MAX_PHOTO_SLOTS }
