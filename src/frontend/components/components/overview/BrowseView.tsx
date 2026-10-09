'use client'

/**
 * Browse (plan P11 stage 2, decision 8.118 Q6, Q8, Q9, Q10): the search field
 * (it takes a name, a number or an id), the circulation switch kept in the
 * URL, the shared filter bar, then a card list on a phone or a table of eight
 * columns with a picker for the rest on a desktop.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Columns3, Search, X } from 'lucide-react'

import CatalogFilterBar from '@/components/catalog/CatalogFilterBar'
import ChipView from '@/components/common/ChipView'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import Help from '@/components/ui/help'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import {
  CIRCULATION_GROUPS,
  CIRCULATION_HELP,
  IN_CIRCULATION_PARTS,
  OPTIONAL_COLUMNS,
  cardLine,
  circulationGroup,
  parsePickedColumns,
  piecesNote,
  rowName,
  rowNumber,
  rowStatus,
  searchTarget,
  withParams,
  type Circulation,
} from '@/lib/browse'
import { useMaterials } from '@/lib/lineage'
import ComponentPreviewImage from '../ComponentPreviewImage'
import { buildColumns } from './ComponentOverviewColumns'
import { ComponentOverviewDataTable } from './ComponentOverviewDataTable'
import ComponentOverviewPagination from './ComponentOverviewPagination'

const PICKED_KEY = 'csc.browse.columns'

const SORT_OPTIONS = [
  { value: '_id', label: 'Identity id' },
  { value: 'name', label: 'Name' },
  { value: 'original_function', label: 'Function' },
  { value: 'material', label: 'Material' },
  { value: 'dataset', label: 'Dataset' },
  { value: 'lastmodified', label: 'Last modified' },
]

type Props = {
  rows: CatalogShallowRow[]
  total: number
  page: number
  size: number
  circulation: Circulation
  q: string
  sortkey: string
  sortorder: 'asc' | 'desc'
  /** Focus the search field on arrival (the phone's top bar Search). */
  focusSearch?: boolean
}

export default function BrowseView({
  rows,
  total,
  page,
  size,
  circulation,
  q,
  sortkey,
  sortorder,
  focusSearch = false,
}: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  const wide = useMediaQuery('(min-width: 768px)')
  const materials = useMaterials(true)
  const materialLabel = useMemo(() => {
    const byId = new Map(materials.map((m) => [m._id, m.label]))
    return (id: string | null | undefined) => (id ? byId.get(id) ?? id : '')
  }, [materials])

  const replace = (changes: Record<string, string | null>, keepPage = false) => {
    const next = withParams(new URLSearchParams(search.toString()), changes, keepPage)
    const text = next.toString()
    router.replace(text ? `${pathname}?${text}` : pathname)
  }

  const group = circulationGroup(circulation)

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-3 p-3 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold sm:text-2xl">Browse</h1>
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {total} {total === 1 ? 'component' : 'components'}
        </p>
      </div>

      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <SearchField value={q} focus={focusSearch} onApply={(text) => replace({ q: text || null })} />
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={group}
            onValueChange={(value) => {
              const target = CIRCULATION_GROUPS.find((g) => g.group === value)
              if (target) replace({ circulation: target.value === 'active' ? null : target.value })
            }}
            aria-label="Circulation"
          >
            {CIRCULATION_GROUPS.map((g) => (
              <ToggleGroupItem key={g.group} value={g.group} className="px-3 text-xs sm:text-sm">
                {g.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <Help label="Circulation" text={CIRCULATION_HELP} />
          {group === 'in' && (
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={circulation}
              onValueChange={(value) => {
                if (value) replace({ circulation: value === 'active' ? null : value })
              }}
              aria-label="In place or not"
            >
              {IN_CIRCULATION_PARTS.map((part) => (
                <ToggleGroupItem key={part.value} value={part.value} className="px-2.5 text-xs">
                  {part.label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          )}
        </div>
      </div>

      <CatalogFilterBar circulation={circulation} />

      {rows.length === 0 ? (
        <Card className="p-6 text-center text-sm text-muted-foreground">
          No components match. Change or remove a filter.
        </Card>
      ) : wide ? (
        <DesktopTable rows={rows} />
      ) : (
        <PhoneCards
          rows={rows}
          materialLabel={materialLabel}
          sortkey={sortkey}
          sortorder={sortorder}
          onSort={(key, order) => replace({ sortkey: key === '_id' ? null : key, sortorder: order === 'asc' ? null : order }, true)}
        />
      )}

      <ComponentOverviewPagination pageNum={page} pageSize={size} total={total} />
    </div>
  )
}

// SEARCH ------------------------------------------------------------------------
function SearchField({
  value,
  focus,
  onApply,
}: {
  value: string
  focus: boolean
  onApply: (text: string) => void
}) {
  const router = useRouter()
  const [text, setText] = useState(value)
  const input = useRef<HTMLInputElement>(null)
  const timer = useRef<number | null>(null)
  useEffect(() => setText(value), [value])
  useEffect(() => {
    if (focus) input.current?.focus()
  }, [focus])
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])

  const submit = (immediately: boolean) => {
    if (timer.current) window.clearTimeout(timer.current)
    const target = searchTarget(text)
    if (target.kind === 'id') {
      if (immediately) router.push(`/components/${target.id}`)
      return
    }
    const apply = () => onApply(target.kind === 'q' ? target.q : '')
    if (immediately) apply()
    else timer.current = window.setTimeout(apply, 450)
  }

  return (
    <form
      className="relative min-w-0 flex-1"
      role="search"
      onSubmit={(e) => {
        e.preventDefault()
        submit(true)
      }}
    >
      <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
      <Input
        ref={input}
        type="search"
        enterKeyHint="search"
        aria-label="Search by name, number or id"
        placeholder="Name, number or id"
        className="h-9 pl-8 pr-8"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          if (timer.current) window.clearTimeout(timer.current)
          const target = searchTarget(e.target.value)
          if (target.kind !== 'id') {
            timer.current = window.setTimeout(() => onApply(target.kind === 'q' ? target.q : ''), 450)
          }
        }}
      />
      {text && (
        <button
          type="button"
          aria-label="Clear the search"
          className="absolute right-1.5 top-1.5 rounded p-1 text-muted-foreground hover:text-foreground"
          onClick={() => {
            setText('')
            onApply('')
          }}
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      )}
    </form>
  )
}

// PHONE ------------------------------------------------------------------------
function PhoneCards({
  rows,
  materialLabel,
  sortkey,
  sortorder,
  onSort,
}: {
  rows: CatalogShallowRow[]
  materialLabel: (id: string | null | undefined) => string
  sortkey: string
  sortorder: 'asc' | 'desc'
  onSort: (key: string, order: 'asc' | 'desc') => void
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm">
        <label htmlFor="browse-sort" className="text-muted-foreground">Sort</label>
        <select
          id="browse-sort"
          className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm"
          value={sortkey}
          onChange={(e) => onSort(e.target.value, sortorder)}
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8"
          onClick={() => onSort(sortkey, sortorder === 'asc' ? 'desc' : 'asc')}
          aria-label={sortorder === 'asc' ? 'Ascending, tap for descending' : 'Descending, tap for ascending'}
        >
          {sortorder === 'asc' ? 'A-Z' : 'Z-A'}
        </Button>
      </div>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row._id}>
            <BrowseCard row={row} line={cardLine(row, materialLabel(row.material))} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function BrowseCard({ row, line }: { row: CatalogShallowRow; line: string }) {
  const pieces = piecesNote(row)
  const number = rowNumber(row)
  return (
    <Link
      href={`/components/${row._id}`}
      className="flex items-center gap-3 rounded-lg border bg-card p-2.5 shadow-xs active:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="h-14 w-14 shrink-0 overflow-hidden rounded-md border bg-white">
        <ComponentPreviewImage
          key={row._id}
          snapshot_id={row.has_preview === false ? null : row.current_snapshot_id}
          alt=""
          width={56}
          height={56}
          maxHeight={56}
          className="h-full w-full"
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="truncate text-sm font-semibold">{rowName(row)}</span>
          {number && <span className="shrink-0 text-xs text-muted-foreground">{number}</span>}
        </div>
        {line && <p className="truncate text-xs text-muted-foreground">{line}</p>}
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <ChipView chip={rowStatus(row)} />
          {pieces && <span className="text-xs text-muted-foreground">{pieces}</span>}
        </div>
      </div>
    </Link>
  )
}

// DESKTOP ----------------------------------------------------------------------
function DesktopTable({ rows }: { rows: CatalogShallowRow[] }) {
  const [picked, setPicked] = useState<string[]>([])
  useEffect(() => {
    try {
      setPicked(parsePickedColumns(window.localStorage.getItem(PICKED_KEY)))
    } catch {
      // no storage: the base columns
    }
  }, [])
  const toggle = (key: string, on: boolean) => {
    const next = on ? [...picked, key] : picked.filter((k) => k !== key)
    setPicked(next)
    try {
      window.localStorage.setItem(PICKED_KEY, JSON.stringify(next))
    } catch {
      // not saved
    }
  }
  const columns = useMemo(() => buildColumns(picked), [picked])
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <Popover>
          <PopoverTrigger asChild>
            <Button type="button" variant="outline" size="sm" className="gap-1.5">
              <Columns3 className="h-4 w-4" aria-hidden />
              Columns
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-56 space-y-2 p-3">
            <p className="text-xs font-medium">More columns</p>
            {OPTIONAL_COLUMNS.map((column) => (
              <label key={column.key} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={picked.includes(column.key)}
                  onCheckedChange={(value) => toggle(column.key, value === true)}
                />
                {column.label}
              </label>
            ))}
          </PopoverContent>
        </Popover>
      </div>
      <Card className="w-full overflow-x-auto p-0">
        <ComponentOverviewDataTable columns={columns} data={rows} />
      </Card>
    </div>
  )
}
