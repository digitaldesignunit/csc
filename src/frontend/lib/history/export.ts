/**
 * Export of the full timeline (decision 8.140 h): the swimlane graph as an
 * SVG or a PNG, the data as JSON. The image is built from the drawing of the
 * page with every group opened (the caller renders it); this file only names
 * the files, turns the SVG into a PNG and starts the download.
 */

/** `csc-history-<number>-<yyyymmdd>.<ext>`: the piece's number, else a short id. */
export function exportFileName(
  catalogNumber: number | null | undefined,
  identityId: string,
  extension: 'svg' | 'png' | 'json',
  now: Date = new Date(),
): string {
  const day = now.toISOString().slice(0, 10).replace(/-/g, '')
  const who = catalogNumber != null ? String(catalogNumber) : identityId.slice(0, 8)
  return `csc-history-${who}-${day}.${extension}`
}

/** The serialised SVG: an XML declaration, the markup. */
export function svgText(svg: SVGSVGElement): string {
  const body = new XMLSerializer().serializeToString(svg)
  return `<?xml version="1.0" encoding="UTF-8"?>\n${body}\n`
}

/** The largest side of a PNG that every browser draws. */
export const MAX_CANVAS_SIDE = 16000

/** The scale of a PNG: 2 for a sharp print, less when the image is very wide. */
export function pngScale(width: number, height: number, wanted = 2): number {
  const longest = Math.max(width, height, 1)
  return Math.min(wanted, MAX_CANVAS_SIDE / longest)
}

export function downloadBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 2000)
}

/** Draws serialised SVG on a white canvas and returns it as a PNG. */
export async function svgToPng(text: string, width: number, height: number, wanted = 2): Promise<Blob> {
  const scale = pngScale(width, height, wanted)
  const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml;charset=utf-8' }))
  try {
    const image = new Image()
    image.decoding = 'async'
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('The image could not be drawn'))
      image.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('No canvas available')
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The PNG could not be made'))), 'image/png')
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}
