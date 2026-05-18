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
