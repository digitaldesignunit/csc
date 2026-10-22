'use client'

import { useLayoutEffect, useRef, useState } from 'react'
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { columnWidths, firstPaintWidths, minTableWidth } from '@/lib/tableWidths'

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
}

export function ComponentOverviewDataTable<TData, TValue>({
  columns,
  data,
}: DataTableProps<TData, TValue>) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  // Every column has a minimum width (lib/tableWidths): the table is never
  // narrower than the sum of those of the columns it shows, and its frame
  // scrolls sideways below that (the page never does). Above it the room is
  // shared by weight, so the table fills the frame.
  const ids = table.getFlatHeaders().map((header) => header.column.id)
  const frame = useRef<HTMLDivElement>(null)
  const [frameWidth, setFrameWidth] = useState<number | null>(null)
  useLayoutEffect(() => {
    const element = frame.current
    if (!element) return
    const measure = () => setFrameWidth(element.clientWidth)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const sized = columnWidths(frameWidth, ids)
  const firstPaint = firstPaintWidths(ids)

  return (
    <div ref={frame} className="w-full overflow-x-auto rounded-lg border bg-card">
      <Table
        className="table-fixed text-foreground"
        style={{ width: sized ? sized.total : '100%', minWidth: minTableWidth(ids) }}
      >
        <colgroup>
          {ids.map((id, index) => (
            <col key={id} style={{ width: sized ? sized.widths[index] : firstPaint[index] }} />
          ))}
        </colgroup>

        <TableHeader className="bg-muted/30">
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="h-10">
              {headerGroup.headers.map((header) => {
                return (
                  <TableHead
                    key={header.id}
                    className="px-3 py-2 text-xs font-semibold text-muted-foreground whitespace-nowrap"
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                )
              })}
            </TableRow>
          ))}
        </TableHeader>

        <TableBody>
          {table.getRowModel().rows?.length ? (
            table.getRowModel().rows.map((row) => {
              // Check if this component is reserved
              const componentData = row.original as CatalogShallowRow
              const isReserved = componentData?.reserved
              
              return (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && 'selected'}
                  className={`h-12 ${isReserved ? 'bg-amber-100/60 hover:bg-amber-200/70 dark:bg-amber-900/40 dark:hover:bg-amber-800/50' : ''}`}
                >
                  {row.getVisibleCells().map((cell) => {
                    return (
                      <TableCell
                        key={cell.id}
                        className="px-3 py-2 text-sm whitespace-nowrap overflow-hidden"
                      >
                        <div className="min-w-0 truncate">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </div>
                      </TableCell>
                    )
                  })}
                </TableRow>
              )
            })
          ) : (
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="h-12 px-3 py-2 text-sm text-muted-foreground"
              >
                No results.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
