'use client'

/**
 * The facts of the component in two groups (decision 8.118): "The component"
 * (what is true of the piece through all its states) and "This state" (what is
 * true of the version on screen). One place per fact; the recorder and the
 * timestamps are history and live in the History card.
 */
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { ORIGINAL_FUNCTION_LABELS, SHAPE_CLASS_LABELS, vocabLabel, type InheritUnit } from '@/generated/Vocab'
import InheritedMark from '@/components/lineage/InheritedMark'
import { factGroups, type Fact } from '@/lib/componentDetail'
import { useMaterials } from '@/lib/lineage'
import { hexComponentColor } from '@/lib/utils'

function Row({ fact, identity }: { fact: Fact; identity: CatalogComponent['identity'] }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/50 py-1 last:border-0">
      <dt className="shrink-0 text-xs text-muted-foreground">{fact.label}</dt>
      <dd className="min-w-0 break-words text-right text-xs font-medium text-foreground">
        {fact.swatch && (
          <span
            className="mr-1.5 inline-block h-3 w-3 rounded-full border border-border align-[-1px]"
            style={{ backgroundColor: hexComponentColor(fact.swatch) }}
          />
        )}
        <span className={fact.label === 'Notes' ? 'whitespace-pre-wrap' : undefined}>{fact.value}</span>
        {fact.inheritedUnit && <InheritedMark identity={identity} unit={fact.inheritedUnit as InheritUnit} />}
      </dd>
    </div>
  )
}

/** "box (authored)", "prism (fit: p95 1.2 mm)": the proxy the viewer draws. */
function proxyFact(snapshot: ReturnType<typeof primarySnapshot>): Fact | null {
  const proxies = (snapshot.geometry?.proxies ?? []) as {
    role?: string
    primitive: string
    fit?: { method: string; p95_mm?: number | null; max_mm?: number | null }
  }[]
  const proxy = proxies.find((p) => p.role === 'primary') ?? proxies[0]
  if (!proxy) return null
  const fit = proxy.fit
  const detail = fit?.p95_mm != null
    ? `${fit.method}, p95 ${fit.p95_mm.toFixed(1)} mm, max ${(fit.max_mm ?? 0).toFixed(1)} mm`
    : fit?.method
  return { label: 'Proxy', value: `${proxy.primitive}${detail ? ` (${detail})` : ''}` }
}

export default function ComponentFactsCard({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  // the material by its label in the materials list, not by its id
  const materials = useMaterials(true)
  const materialLabel = materials.find((m) => m._id === identity.material)?.label ?? null
  const groups = factGroups({
    identity,
    snapshot,
    materialLabel,
    functionLabel: vocabLabel(ORIGINAL_FUNCTION_LABELS, identity.original_function),
    shapeClassLabel: snapshot.shape_class ? vocabLabel(SHAPE_CLASS_LABELS, snapshot.shape_class) : null,
  })
  const proxy = proxyFact(snapshot)
  const state = proxy ? [...groups.state, proxy] : groups.state

  return (
    <section aria-label="Facts" className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">The component</h2>
      <dl>{groups.component.map((fact) => <Row key={fact.label} fact={fact} identity={identity} />)}</dl>
      <h2 className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">This state</h2>
      <dl>{state.map((fact) => <Row key={fact.label} fact={fact} identity={identity} />)}</dl>
    </section>
  )
}
