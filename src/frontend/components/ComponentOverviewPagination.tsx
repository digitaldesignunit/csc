'use client';

import { useMemo } from 'react';
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from './ui/pagination';
import { useSearchParams, usePathname, useRouter } from 'next/navigation';

export interface ComponentOverviewPaginationProps {
  pageNum: number;
  pageSize: number;
  total: number;
  /** How many numbered page links to show around the current page (on each side). Default: 2 */
  siblingCount?: number;
}

export default function ComponentOverviewPagination({
  pageNum,
  pageSize,
  total,
  siblingCount = 2,
}: ComponentOverviewPaginationProps) {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const { replace } = useRouter();

  const pageCount = useMemo(() => {
    const pc = Math.ceil((total ?? 0) / Math.max(pageSize, 1));
    return Math.max(pc, 1);
  }, [total, pageSize]);

  const clampedPage = Math.min(Math.max(pageNum, 1), pageCount);
  const canPrev = clampedPage > 1;
  const canNext = clampedPage < pageCount;

  function setPage(p: number) {
    const target = Math.min(Math.max(p, 1), pageCount);
    const params = new URLSearchParams(searchParams);
    params.set('page', String(target));
    // keep size stable in the URL for SSR fetches
    params.set('size', String(pageSize));
    replace(`${pathname}?${params.toString()}`);
  }

  // Build a compact page window: [1] ... [n-2 n-1 n n+1 n+2] ... [last]
  const pages = useMemo(() => {
    const items: Array<number | 'ellipsis'> = [];
    const start = Math.max(2, clampedPage - siblingCount);
    const end = Math.min(pageCount - 1, clampedPage + siblingCount);

    items.push(1);

    if (start > 2) items.push('ellipsis');

    for (let p = start; p <= end; p++) items.push(p);

    if (end < pageCount - 1) items.push('ellipsis');

    if (pageCount > 1) items.push(pageCount);

    return items;
  }, [clampedPage, pageCount, siblingCount]);

  return (
    <div className="flex items-left justify-between py-2">
      <div className="text-sm text-neutral-600">
        Page {clampedPage} of {pageCount}
        {typeof total === 'number' ? ` · ${total} items` : null}
      </div>

      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              aria-disabled={!canPrev}
              className={canPrev ? 'cursor-pointer' : 'pointer-events-none opacity-50'}
              onClick={() => canPrev && setPage(clampedPage - 1)}
            />
          </PaginationItem>

          {pages.map((p, idx) =>
            p === 'ellipsis' ? (
              <PaginationItem key={`e-${idx}`}>
                <PaginationEllipsis />
              </PaginationItem>
            ) : (
              <PaginationItem key={p}>
                <PaginationLink
                  aria-current={p === clampedPage ? 'page' : undefined}
                  isActive={p === clampedPage}
                  className="cursor-pointer"
                  onClick={() => setPage(p)}
                >
                  {p}
                </PaginationLink>
              </PaginationItem>
            )
          )}

          <PaginationItem>
            <PaginationNext
              aria-disabled={!canNext}
              className={canNext ? 'cursor-pointer' : 'pointer-events-none opacity-50'}
              onClick={() => canNext && setPage(clampedPage + 1)}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}
