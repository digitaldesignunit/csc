'use client'

/**
 * The descriptors panel of the component page (HKS level 1, plan 0.6): the
 * heat kernel signature of this version as two curves, the mean and the
 * variance over the surface at growing scales (decision 8.6). Folded by
 * default; it is for people who compare pieces by shape (the component map
 * can embed it as a basis). A version without an HKS says why: the geometry
 * runner has not computed it yet.
 */
import { Waves } from 'lucide-react'

import Help from '@/components/ui/help'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { HKS_T_MAX, HKS_T_MIN, chartPoints, linePath, parseHks } from '@/lib/hks'

const WIDTH = 220
const HEIGHT = 96

const HELP = 'The heat kernel signature describes the shape of the whole surface at growing scales: '
  + 'small times see local detail, large times the overall form. It does not depend on size, position or '
  + 'orientation. Mean and variance are taken over the surface at each time.'

function Curve({ title, values, tone }: { title: string; values: number[]; tone: string }) {
  const { points, min, max } = chartPoints(values, WIDTH, HEIGHT)
  const text = (n: number) => (Math.abs(n) >= 0.01 ? n.toFixed(3) : n.toExponential(1))
  return (
    <figure className="min-w-0 space-y-1">
      <figcaption className="text-xs font-medium">{title}</figcaption>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full rounded border border-border bg-muted/30"
        role="img" aria-label={`${title}: from ${text(values[0])} at the smallest time to ${text(values[values.length - 1])} at the largest`}>
        <line x1={6} x2={WIDTH - 6} y1={HEIGHT - 6} y2={HEIGHT - 6} stroke="var(--border)" strokeWidth={1} />
        <path d={linePath(points)} fill="none" stroke={tone} strokeWidth={2} strokeLinejoin="round" />
        {points.map((p) => (
          <circle key={p.x} cx={p.x} cy={p.y} r={2.2} fill={tone}>
            <title>{`t = ${p.t.toPrecision(2)}: ${text(p.value)}`}</title>
          </circle>
        ))}
      </svg>
      <p className="flex justify-between text-[10px] tabular-nums text-muted-foreground">
        <span>min {text(min)}</span>
        <span>max {text(max)}</span>
      </p>
    </figure>
  )
}

export default function ComponentDescriptorsCard({ catalog }: { catalog: CatalogComponent }) {
  const snapshot = primarySnapshot(catalog)
  const curves = parseHks(snapshot.descriptors)
  return (
    <details className="group rounded-lg border border-border bg-card p-3 shadow-sm" aria-label="Descriptors">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-semibold">
        <span className="flex items-center gap-2"><Waves className="h-4 w-4" aria-hidden />Descriptors</span>
        <span className="text-xs font-normal text-muted-foreground group-open:hidden">Heat kernel signature</span>
      </summary>
      <div className="mt-3 space-y-3">
        <div className="flex items-center gap-1.5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Heat kernel signature</h3>
          <Help label="Heat kernel signature" text={HELP} />
        </div>
        {curves ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              <Curve title="Mean over the surface" values={curves.mean} tone="var(--primary)" />
              <Curve title="Variance over the surface" values={curves.variance} tone="#d97706" />
            </div>
            <p className="text-[11px] text-muted-foreground">
              Time grows to the right, from {HKS_T_MIN.toPrecision(2)} to {HKS_T_MAX.toPrecision(2)} (units of the
              surface area, log scale).
            </p>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            This version has no heat kernel signature yet. The geometry runner computes it with the other
            descriptors; a version without a surface to sample (no mesh, no point cloud, no authored shape) never gets one.
          </p>
        )}
      </div>
    </details>
  )
}
