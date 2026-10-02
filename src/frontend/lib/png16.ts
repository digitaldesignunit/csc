/**
 * Reader for the deviation-map PNGs (spec appendix B): 16-bit RGB, one
 * zlib stream, filter type 0 --- exactly what the backend writes. A canvas
 * would flatten them to 8 bit, so the bytes are decoded here (the browser's
 * `DecompressionStream` inflates the zlib data).
 */

export type Rgb16Image = {
  width: number
  height: number
  /** Interleaved R, G, B; `height * width * 3` values 0..65535. */
  data: Uint16Array
}

const SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]

async function inflate(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([bytes as BlobPart])
    .stream()
    .pipeThrough(new DecompressionStream('deflate'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

export async function decodePng16(buffer: ArrayBuffer): Promise<Rgb16Image> {
  const bytes = new Uint8Array(buffer)
  if (!SIGNATURE.every((value, i) => bytes[i] === value)) {
    throw new Error('not a PNG')
  }
  const view = new DataView(buffer)
  let position = 8
  let width = 0
  let height = 0
  const parts: Uint8Array[] = []
  while (position < bytes.length) {
    const length = view.getUint32(position)
    const kind = String.fromCharCode(...bytes.subarray(position + 4, position + 8))
    const bodyStart = position + 8
    const body = bytes.subarray(bodyStart, bodyStart + length)
    position += 12 + length
    if (kind === 'IHDR') {
      width = view.getUint32(bodyStart)
      height = view.getUint32(bodyStart + 4)
      const depth = body[8]
      const colour = body[9]
      if (depth !== 16 || colour !== 2) throw new Error('only 16-bit RGB PNGs')
    } else if (kind === 'IDAT') {
      parts.push(body)
    }
  }
  const compressed = new Uint8Array(parts.reduce((n, p) => n + p.length, 0))
  let offset = 0
  for (const part of parts) {
    compressed.set(part, offset)
    offset += part.length
  }
  const raw = await inflate(compressed)
  const stride = width * 6 + 1
  const data = new Uint16Array(width * height * 3)
  for (let row = 0; row < height; row += 1) {
    const start = row * stride
    if (raw[start] !== 0) throw new Error('only filter type 0')
    for (let i = 0; i < width * 3; i += 1) {
      const at = start + 1 + i * 2
      data[row * width * 3 + i] = (raw[at] << 8) | raw[at + 1]
    }
  }
  return { width, height, data }
}
