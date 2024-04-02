'use client';

import { useState } from "react";
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "./ui/pagination";

export default function ComponentOverviewPagination() {

  const [pageSize, setPageSize] = useState(10);
  const [pageNum, setPageNum] = useState(1);

  return (
    <div>
      <Pagination>
        <PaginationContent>

          <PaginationItem>
            <PaginationPrevious 
              className={
                pageNum === 1 ? "pointer-events-none opacity-50" : undefined
              }
              onClick={() => {
                setPageNum(pageNum - 1);
              }}
              href="#" />
          </PaginationItem>

          <PaginationItem>
            <PaginationLink href="#">1</PaginationLink>
          </PaginationItem>

          <PaginationItem>
            <PaginationLink href="#" isActive>
              2
            </PaginationLink>
          </PaginationItem>

          <PaginationItem>
            <PaginationLink href="#">3</PaginationLink>
          </PaginationItem>

          <PaginationItem>
            <PaginationEllipsis />
          </PaginationItem>

          <PaginationItem>
            <PaginationNext 
              className={
                pageNum === 100 ? "pointer-events-none opacity-50" : undefined
              }
              onClick={() => {
                setPageNum(pageNum + 1);
              }}
              href="#" />
          </PaginationItem>

        </PaginationContent>
      </Pagination>
    </div>
  );
}