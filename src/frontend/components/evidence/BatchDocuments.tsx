'use client'

/**
 * "Documents from the batch" (decision 8.105): a piece drawn from a batch
 * does not copy the batch's evidence; the documents that describe the whole
 * batch (drawings, data sheets, the source of the catalogue entry) are
 * listed here, read-only, with their source link.
 */
import { useEffect, useState } from 'react'
import { FileText } from 'lucide-react'

import type { EvidenceView } from '@/generated'
import type { ComponentIdentity } from '@/generated/CatalogModels'
import { formatDateAtPrecision } from '@/components/components/componentDetailShared'
import { backendJson } from '@/lib/backend'
import { documentOf } from '@/lib/evidence/document'
import { loadEvidenceOf } from '@/lib/evidence/api'

type Doc = { id: string; title: string; href: string | null; host: string | null; observedAt: string; precision: string | null }

export default function BatchDocuments({ identity }: { identity: ComponentIdentity }) {
  const parents = identity.parent_identities ?? []
  const parentId = parents.length === 1 ? String(parents[0]) : null
  const [docs, setDocs] = useState<Doc[]>([])

  useEffect(() => {
    if (!parentId) return
    let cancelled = false
    ;(async () => {
      try {
        // only a batch has `remaining`; a plain parent's evidence is not shown here
        const parent = await backendJson<{ remaining?: number | null }>(
          `/identities/${encodeURIComponent(parentId)}?expand=none`)
        if (typeof parent.remaining !== 'number') return
        const records = await loadEvidenceOf(parentId)
        const found = records
          .filter((r: EvidenceView) => 'method' in r && !r.summary && !r.superseded_by && r.status === 'published')
          .map((r) => {
            const cited = documentOf(r.payload)
            return {
              id: r._id,
              title: cited?.title ?? 'Untitled document',
              href: cited?.href ?? null,
              host: cited?.host ?? null,
              observedAt: r.observed_at,
              precision: r.observed_at_precision ?? null,
            }
          })
        if (!cancelled) setDocs(found)
      } catch {
        if (!cancelled) setDocs([])
      }
    })()
    return () => { cancelled = true }
  }, [parentId])

  if (docs.length === 0) return null
  return (
    <section aria-label="Documents from the batch" className="space-y-1.5 rounded-md border border-border/70 p-3">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <FileText className="h-3.5 w-3.5" />Documents from the batch
      </h3>
      <ul className="space-y-1 text-sm">
        {docs.map((doc) => (
          <li key={doc.id} className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">{doc.title}</span>
            {doc.href && (
              <a href={doc.href} target="_blank" rel="noopener noreferrer"
                className="text-xs underline underline-offset-2">{doc.host}</a>
            )}
            <span className="text-xs text-muted-foreground">
              {formatDateAtPrecision(doc.observedAt, doc.precision)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
