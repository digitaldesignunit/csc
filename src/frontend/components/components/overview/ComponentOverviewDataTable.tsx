'use client'

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

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
}

type ColMeta = { colClassName?: string }

export function ComponentOverviewDataTable<TData, TValue>({
  columns,
  data,
}: DataTableProps<TData, TValue>) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <div className="w-full overflow-x-auto rounded-lg border bg-card">
      {/* Use table-fixed so widths from <col> and cells actually take effect */}
      <Table className="table-auto w-full text-foreground">
        {/* Apply responsive widths via <colgroup> */}
        <colgroup>
          {table.getFlatHeaders().map((header) => (
            <col
              key={header.id}
              className={(header.column.columnDef.meta as ColMeta | undefined)?.colClassName ?? ''}
            />
          ))}
        </colgroup>

        <TableHeader className="bg-muted/30">
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="h-10">
              {headerGroup.headers.map((header) => {
                const headMeta = header.column.columnDef.meta as ColMeta | undefined
                return (
                  
                  <TableHead
                    key={header.id}
                    className={`px-3 py-2 text-xs font-semibold text-muted-foreground whitespace-nowrap ${headMeta?.colClassName ?? ''}`}
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
              const componentData = row.original as any
              const isReserved = componentData?.reserved
              
              return (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && 'selected'}
                  className={`h-12 ${isReserved ? 'bg-amber-100/60 hover:bg-amber-200/70 dark:bg-amber-900/40 dark:hover:bg-amber-800/50' : ''}`}
                >
                  {row.getVisibleCells().map((cell) => {
                    const cellMeta = cell.column.columnDef.meta as ColMeta | undefined
                    return (
                      <TableCell
                        key={cell.id}
                        className={`px-3 py-2 text-sm whitespace-nowrap overflow-hidden ${cellMeta?.colClassName ?? ''}`}
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
