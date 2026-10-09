/**
 * Browser-side calls to the backend through the `/api/backend` proxy, which
 * adds the login token and the client header. Errors carry the backend's
 * `detail` text so the UI can show why something was refused.
 */

export class BackendError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(backendErrorText(detail, status))
    this.status = status
    this.detail = detail
  }
}

function backendErrorText(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = (detail as { msg?: unknown }[])
      .map((row) => (typeof row?.msg === 'string' ? row.msg : ''))
      .filter(Boolean)
    if (messages.length) return messages.join('; ')
  }
  if (detail && typeof detail === 'object') {
    const record = detail as { message?: unknown; fields?: unknown }
    if (typeof record.message === 'string') {
      return Array.isArray(record.fields) && record.fields.length
        ? `${record.message} (${record.fields.join(', ')})`
        : record.message
    }
  }
  return `Request failed (${status})`
}

export async function backendJson<T>(
  path: string,
  init: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    method: init.method ?? 'GET',
    credentials: 'include',
    cache: 'no-store',
    signal: init.signal,
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  })
  const text = await response.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!response.ok) {
    const detail = (data as { detail?: unknown; error?: unknown } | null)?.detail
      ?? (data as { error?: unknown } | null)?.error
      ?? data
    throw new BackendError(response.status, detail)
  }
  return data as T
}

/** A withdrawn record seen from outside its dataset (8.17). */
export function isTombstone(body: unknown): body is import('@/generated/AccessModels').Tombstone {
  return Boolean(
    body
    && typeof body === 'object'
    && (body as { status?: unknown }).status === 'withdrawn'
    && typeof (body as { kind?: unknown }).kind === 'string',
  )
}
