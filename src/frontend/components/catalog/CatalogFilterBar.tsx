'use client'

/**
 * The filter bar shared by Browse and Analytics (plan P11 stage 2, decision
 * 8.118, review section 4): function, material and dataset always visible,
 * the rest behind "More filters", applied on change, the active filters as
 * chips with a cross. The state is the URL, so a link carries the filters.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { SlidersHorizontal, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  ORIGINAL_FUNCTION_LABELS,
  SHAPE_CLASS_LABELS,
} from '@/generated/Vocab'
import {
  activeFilters,
  filterChipLabel,
  withParams,
  withoutFilters,
  type FilterKey,
  type ParamsLike,
} from '@/lib/browse'
import { useMaterials } from '@/lib/lineage'

const SELECT_CLASS =
  'h-9 w-full min-w-0 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

type Props = {
  /** The circulation the dataset list is taken for (`meta/datasets`). */
  circulation?: string
  /** The "More filters" fields: the size boxes only where the list has sizes. */
  withSize?: boolean
  /** Extra fields of the "More filters" popover, e.g. the rows per page. */
  extra?: React.ReactNode
}

export default function CatalogFilterBar({ circulation = 'active', withSize = true, extra }: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  const materials = useMaterials(true)
  const [datasets, setDatasets] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    fetch(`/api/backend/identities/meta/datasets?circulation=${encodeURIComponent(circulation)}`, {
      credentials: 'include',
    })
      .then((res) => (res.ok ? res.json() : []))
      .then((rows: string[]) => {
        if (!cancelled) setDatasets(Array.isArray(rows) ? rows : [])
      })
      .catch(() => {
        if (!cancelled) setDatasets([])
      })
    return () => {
      cancelled = true
    }
  }, [circulation])

  const materialLabel = useMemo(() => {
    const byId = new Map(materials.map((m) => [m._id, m.label]))
    return (id: string) => byId.get(id) ?? id
  }, [materials])

  const go = (changes: Record<string, string | null>) => {
    const next = withParams(new URLSearchParams(search.toString()), changes)
    const text = next.toString()
    router.replace(text ? `${pathname}?${text}` : pathname)
  }
  const clearAll = () => {
    const text = withoutFilters(new URLSearchParams(search.toString())).toString()
    router.replace(text ? `${pathname}?${text}` : pathname)
  }

  const active = activeFilters(search)
  const moreCount = active.filter((f) => !['original_function', 'material', 'dataset'].includes(f.key)).length

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
        <select
          aria-label="Function"
          className={SELECT_CLASS}
          value={search.get('original_function') ?? ''}
          onChange={(e) => go({ original_function: e.target.value })}
        >
          <option value="">Any function</option>
          {Object.entries(ORIGINAL_FUNCTION_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        <select
          aria-label="Material"
          className={SELECT_CLASS}
          value={search.get('material') ?? ''}
          onChange={(e) => go({ material: e.target.value })}
        >
          <option value="">Any material</option>
          {materials.map((m) => (
            <option key={m._id} value={m._id}>{m.label}</option>
          ))}
        </select>
        <select
          aria-label="Dataset"
          className={SELECT_CLASS}
          value={search.get('dataset') ?? ''}
          onChange={(e) => go({ dataset: e.target.value })}
        >
          <option value="">Any dataset</option>
          {datasets.map((slug) => (
            <option key={slug} value={slug}>{slug}</option>
          ))}
        </select>
        <MoreFilters
          count={moreCount}
          search={search}
          go={go}
          withSize={withSize}
          extra={extra}
        />
      </div>
      {active.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {active.map((filter) => (
            <button
              key={filter.key}
              type="button"
              onClick={() => go({ [filter.key]: null })}
              className="inline-flex items-center gap-1 rounded-full border bg-muted px-2.5 py-0.5 text-xs hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`Remove filter ${filterChipLabel(filter.key, filter.value, { material: materialLabel })}`}
            >
              {filterChipLabel(filter.key, filter.value, { material: materialLabel })}
              <X className="h-3 w-3" aria-hidden />
            </button>
          ))}
          {active.length > 1 && (
            <button type="button" onClick={clearAll} className="px-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground">
              Clear all
            </button>
          )}
        </div>
      )}
    </div>
  )
}

const SIZE_FIELDS: { axis: 'x' | 'y' | 'z'; label: string }[] = [
  { axis: 'x', label: 'X' },
  { axis: 'y', label: 'Y' },
  { axis: 'z', label: 'Z' },
]

function MoreFilters({
  count,
  search,
  go,
  withSize,
  extra,
}: {
  count: number
  search: ParamsLike
  go: (changes: Record<string, string | null>) => void
  withSize: boolean
  extra?: React.ReactNode
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" className="h-9 justify-center gap-1.5">
          <SlidersHorizontal className="h-4 w-4" aria-hidden />
          More filters
          {count > 0 && (
            <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{count}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(22rem,calc(100vw-2rem))] space-y-3 p-3">
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label htmlFor="more-shape" className="text-xs">Shape class</Label>
            <select
              id="more-shape"
              className={SELECT_CLASS}
              value={search.get('shape_class') ?? ''}
              onChange={(e) => go({ shape_class: e.target.value })}
            >
              <option value="">Any</option>
              {Object.entries(SHAPE_CLASS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="more-complexity" className="text-xs">Complexity</Label>
            <select
              id="more-complexity"
              className={SELECT_CLASS}
              value={search.get('complexity') ?? ''}
              onChange={(e) => go({ complexity: e.target.value })}
            >
              <option value="">Any</option>
              <option value="0">0 - Simplest</option>
              <option value="1">1 - Simple</option>
              <option value="2">2 - Medium</option>
              <option value="3">3 - Complex</option>
            </select>
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="more-fragment" className="text-xs">Fragments</Label>
            <select
              id="more-fragment"
              className={SELECT_CLASS}
              value={search.get('fragment') ?? ''}
              onChange={(e) => go({ fragment: e.target.value })}
            >
              <option value="">Any</option>
              <option value="true">Fragments only</option>
              <option value="false">No fragments</option>
            </select>
          </div>
        </div>
        {withSize && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium">Size in mm (from, to)</p>
            {SIZE_FIELDS.map(({ axis, label }) => (
              <div key={axis} className="grid grid-cols-[1.25rem_1fr_1fr] items-center gap-2">
                <span className="text-xs text-muted-foreground">{label}</span>
                <SizeInput name={`bbx_min_${axis}`} label={`${label} from`} search={search} go={go} />
                <SizeInput name={`bbx_max_${axis}`} label={`${label} to`} search={search} go={go} />
              </div>
            ))}
          </div>
        )}
        {extra}
      </PopoverContent>
    </Popover>
  )
}

/** A number box that applies when the typing pauses (applied on change). */
function SizeInput({
  name,
  label,
  search,
  go,
}: {
  name: FilterKey
  label: string
  search: ParamsLike
  go: (changes: Record<string, string | null>) => void
}) {
  const stored = search.get(name) ?? ''
  const [value, setValue] = useState(stored)
  const timer = useRef<number | null>(null)
  useEffect(() => setValue(stored), [stored])
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])
  return (
    <Input
      type="number"
      inputMode="decimal"
      aria-label={label}
      placeholder={label.endsWith('from') ? 'from' : 'to'}
      className="h-8"
      value={value}
      onChange={(e) => {
        setValue(e.target.value)
        if (timer.current) window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => go({ [name]: e.target.value || null }), 500)
      }}
    />
  )
}
