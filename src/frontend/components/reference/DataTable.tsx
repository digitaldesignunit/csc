import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type Column<T> = {
  key: string
  header: string
  render: (row: T) => ReactNode
  /** classes of the cells of the column on wide screens */
  className?: string
}

/**
 * A table that stays readable on a phone: from the `sm` width up an ordinary
 * table, below it one block per row (the first column as its heading, the
 * others as "name: value" lines), so that nothing scrolls sideways.
 */
export default function DataTable<T>({
  columns,
  rows,
  label,
  rowKey,
}: {
  columns: Column<T>[]
  rows: T[]
  label: string
  rowKey: (row: T, index: number) => string
}) {
  const [first, ...rest] = columns
  return (
    <>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full border-collapse text-sm" aria-label={label}>
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
              {columns.map((column) => (
                <th key={column.key} scope="col" className="px-2 py-1.5 font-medium">{column.header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={rowKey(row, index)} className="border-b border-border/60 align-top last:border-0">
                {columns.map((column) => (
                  <td key={column.key} className={cn('px-2 py-1.5', column.className)}>{column.render(row)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 sm:hidden" aria-label={label}>
        {rows.map((row, index) => (
          <li key={rowKey(row, index)} className="space-y-1 border-l-2 border-primary/40 pl-3 text-sm">
            <div className="font-medium">{first.render(row)}</div>
            {rest.map((column) => (
              <div key={column.key}>
                <span className="text-xs uppercase tracking-wide text-muted-foreground">{column.header}: </span>
                {column.render(row)}
              </div>
            ))}
          </li>
        ))}
      </ul>
    </>
  )
}
