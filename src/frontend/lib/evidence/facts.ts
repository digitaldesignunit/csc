/**
 * What the server computed for a record (median, valid readings, the
 * length-to-diameter class ...): read from the payload with the fields the
 * registry's schema marks `server_computed`, so a new method needs no code
 * here. Values are shown, never entered.
 */
import type { JsonSchema, MethodInfo } from '@/lib/evidence/api'
import { isObject, kindOf, labelOf, resolve } from '@/lib/evidence/schema'

export type ServerFact = { path: string; label: string; value: string; help: string }

function show(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'number') return String(Math.round(value * 10000) / 10000)
  if (typeof value === 'string') return value
  return null
}

function walk(
  schema: JsonSchema,
  root: JsonSchema,
  value: unknown,
  path: string[],
  out: ServerFact[],
): void {
  if (!isObject(value)) return
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    const resolved = resolve(prop, root)
    const here = [...path, key]
    const raw = value[key]
    if (prop.server_computed || resolved.schema.server_computed) {
      const text = show(raw)
      if (text !== null) {
        out.push({ path: here.join('.'), label: labelOf(key, resolved), value: text, help: resolved.description })
      }
    } else if (kindOf(resolved, root) === 'object') {
      walk(resolved.schema, root, raw, here, out)
    }
  }
}

export function serverFacts(method: MethodInfo | undefined, payload: unknown): ServerFact[] {
  if (!method) return []
  const out: ServerFact[] = []
  walk(method.payload_schema, method.payload_schema, payload, [], out)
  return out
}
