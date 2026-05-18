'use client'

import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { ComponentOverviewDataTable } from './ComponentOverviewDataTable'
import { ComponentOverviewColumns } from './ComponentOverviewColumns'

interface ComponentOverviewDataTableWithConfigProps {
  data: CatalogShallowRow[]
}

/** @deprecated Use ComponentOverviewDataTable with ComponentOverviewColumns directly. */
export default function ComponentOverviewDataTableWithConfig({
  data,
}: ComponentOverviewDataTableWithConfigProps) {
  return <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={data} />
}
