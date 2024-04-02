'use client';

import { useState } from "react";
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "./ui/pagination";
import { useSearchParams, usePathname, useRouter } from "next/navigation";


interface ComponentOverviewPaginationProps {
  pageNum: number
  pageSize: number
}


export default function ComponentOverviewPagination({
  pageNum,
  pageSize,
}: ComponentOverviewPaginationProps) {

  // const [pageSize, setPageSize] = useState(10);
  // const [pageNum, setPageNum] = useState(1);

  const searchParams = useSearchParams();
  const pathname = usePathname();
  const { replace } = useRouter();

  function handlePagination(pageNum: number | string, pageSize: number | string) {
    const params = new URLSearchParams(searchParams)
    params.set('page', pageNum.toString());
    replace(`${pathname}?${params.toString()}`)
  }

  // const [isActive, setActive] = useState<string>("");
  // const toggleHandler = (pn: number) => () =>
  //   setActive((isActive) => (isActive === id ? "" : id));

  return (
    <div>
      <Pagination>
        <PaginationContent>

          <PaginationItem>
            <PaginationPrevious 
              className={
                pageNum === 1 ?
                "pointer-events-none opacity-50" :
                "cursor-pointer"
              }
              onClick={() => {
                handlePagination(pageNum - 1, pageSize);
              }}
              />
          </PaginationItem>

          {/* <PaginationItem>
            <PaginationLink href="#">1</PaginationLink>
          </PaginationItem>

          <PaginationItem>
            <PaginationLink href="#" isActive>
              2
            </PaginationLink>
          </PaginationItem>

          <PaginationItem>
            <PaginationLink href="#">3</PaginationLink>
          </PaginationItem> */}

          <PaginationItem>
            <PaginationEllipsis />
          </PaginationItem>

          <PaginationItem>
            <PaginationNext 
              className={
                pageNum === 100 ?
                "pointer-events-none opacity-50" :
                "cursor-pointer"
              }
              onClick={() => {
                handlePagination(pageNum + 1, pageSize);
              }}
              />
          </PaginationItem>

        </PaginationContent>
      </Pagination>
    </div>
  );
}