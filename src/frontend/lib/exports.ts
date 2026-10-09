/**
 * Exports of a component passport (spec 7.8, plan P10): the paths under the
 * `/api/backend` proxy, the file name of the PDF, and the one rule the web
 * repeats from the backend: CERO covers concrete elements only (8.116 d).
 */

const API = '/api/backend'

/** Materials CERO (v0.1) describes; the backend answers 409 for any other. */
export const CERO_MATERIALS: readonly string[] = ['concrete', 'autoclaved_aerated_concrete']

export function isCeroMaterial(material: string | null | undefined): boolean {
  return !!material && CERO_MATERIALS.includes(material)
}

export type PassportExport = {
  pdf: string
  pdfFilename: string
  jsonld: string
  /** null for a piece CERO does not cover: no link at all */
  cero: string | null
  ceroFilename: string
}

export function passportExports(
  identityId: string,
  catalogNumber: number | null | undefined,
  material: string | null | undefined,
): PassportExport {
  const id = encodeURIComponent(identityId)
  return {
    pdf: `${API}/identities/${id}/export/pdf`,
    pdfFilename: `csc-passport-${catalogNumber ?? id}.pdf`,
    ceroFilename: `csc-cero-${catalogNumber ?? id}.ttl`,
    jsonld: `${API}/identities/${id}/compose?format=jsonld`,
    cero: isCeroMaterial(material) ? `${API}/identities/${id}/export/cero` : null,
  }
}

/** What a refused download says: the rate limit (429) in plain words, any
 *  other answer as the backend gave it. */
export function downloadFailureMessage(status: number, text: string): string {
  if (status === 429) return 'Too many downloads, try again in a minute'
  return text || `Download failed (${status})`
}

/** Fetch an export through the proxy (the session, if any, rides along) and
 *  hand it to the browser as a download. */
export async function downloadExport(url: string, filename: string): Promise<void> {
  const res = await fetch(url, { credentials: 'include', cache: 'no-store' })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(downloadFailureMessage(res.status, text))
  }
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

export const downloadPassportPdf = downloadExport
