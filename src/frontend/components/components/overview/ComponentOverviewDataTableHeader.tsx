'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { ArrowDown, ArrowUp, ArrowUpDown, X } from "lucide-react"

export default function ComponentOverviewDataTableHeader({
  header,
  sortKey,
} : {
  header: string
  sortKey?: string
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const activeSortKey = searchParams.get('sortkey') ?? '_id'
  const activeSortOrder = searchParams.get('sortorder') === 'desc' ? 'desc' : 'asc'
  const isActiveSort = Boolean(sortKey) && activeSortKey === sortKey

  const handleSortClick = () => {
    if (!sortKey) return
    const params = new URLSearchParams(searchParams.toString())
    if (isActiveSort) {
      params.set('sortorder', activeSortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      params.set('sortorder', 'asc')
    }
    params.set('sortkey', sortKey)
    params.set('page', '1')
    router.replace(`?${params.toString()}`)
  }

  const handleResetSort = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation()
    const params = new URLSearchParams(searchParams.toString())
    params.delete('sortkey')
    params.delete('sortorder')
    params.set('page', '1')
    router.replace(`?${params.toString()}`)
  }

  return (
    <div className='flex flex-row items-center text-left gap-1 whitespace-nowrap'>
      {sortKey ? (
        <div className='inline-flex items-center gap-1'>
          <button
            type="button"
            onClick={handleSortClick}
            className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 cursor-pointer border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
              isActiveSort
                ? 'text-foreground font-semibold bg-primary/10 border-primary/40'
                : 'text-muted-foreground bg-background/60 border-transparent hover:text-foreground hover:bg-accent hover:border-border'
            }`}
            title={
              isActiveSort
                ? `Sorted ${activeSortOrder}; click to sort ${activeSortOrder === 'asc' ? 'descending' : 'ascending'}`
                : `Sort by ${header} (ascending)`
            }
          >
            <span>{header}</span>
            {isActiveSort ? (
              activeSortOrder === 'asc' ? (
                <ArrowUp size={14} className='opacity-100' />
              ) : (
                <ArrowDown size={14} className='opacity-100' />
              )
            ) : (
              <ArrowUpDown size={14} className='opacity-70' />
            )}
          </button>
          {isActiveSort && (
            <button
              type="button"
              onClick={handleResetSort}
              className='inline-flex items-center justify-center rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent border border-transparent hover:border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1'
              title='Reset sorting'
              aria-label='Reset sorting'
            >
              <X size={12} />
            </button>
          )}
        </div>
      ) : (
        <div>{header}</div>
      )}
    </div>
  )
}
