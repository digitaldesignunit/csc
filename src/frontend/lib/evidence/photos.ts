/**
 * Files for evidence attachments in the browser: a phone photo is scaled
 * down before it is sent (the server re-encodes images anyway and the
 * proxy body is limited); a PDF is sent byte for byte.
 */
const MAX_EDGE_PX = 2400
const SHRINK_ABOVE_BYTES = 1_200_000

export const ATTACHMENT_ACCEPT = 'application/pdf,image/jpeg,image/png,image/webp'

/** An evidence file is capped at 25 MB (decision 8.82); the backend checks it too. */
export const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
export const MAX_ATTACHMENT_TEXT = '25 MB'

/** Why a file cannot be sent, said before it is chosen; null when it can. */
export function fileProblem(file: File): string | null {
  return file.size > MAX_ATTACHMENT_BYTES
    ? `${file.name} is larger than ${MAX_ATTACHMENT_TEXT}: a file can be at most ${MAX_ATTACHMENT_TEXT}.`
    : null
}

export async function prepareUpload(file: File): Promise<File> {
  if (!file.type.startsWith('image/') || file.size <= SHRINK_ABOVE_BYTES) return file
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const factor = Math.min(1, MAX_EDGE_PX / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * factor))
    canvas.height = Math.max(1, Math.round(bitmap.height * factor))
    const context = canvas.getContext('2d')
    if (!context) return file
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
    if (!blob || blob.size >= file.size) return file
    return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' })
  } catch {
    return file
  }
}
