/**
 * What a refused upload says. The proxy answers `{ error }` and the backend
 * `{ detail }`; a 413 is put in plain words, any other answer shows its text,
 * never the raw JSON.
 */
export function uploadErrorText(status: number, body: string): string {
  if (status === 413) return 'This file is too large to upload. Choose a smaller one.'
  let text = body
  try {
    const parsed = JSON.parse(body) as { detail?: unknown; error?: unknown }
    const found = parsed.detail ?? parsed.error
    if (typeof found === 'string') text = found
  } catch {
    // not JSON: the text stands
  }
  return text.trim() || `Upload failed (${status})`
}
