'use client'

import { ComponentModel } from '@/generated/ComponentModel'
import { ComponentOverviewDataTable } from './ComponentOverviewDataTable'
import { createComponentOverviewColumns, ComponentOverviewColumns } from './ComponentOverviewColumns'
import { PreviewCellConfig } from './ComponentOverviewDataTablePreviewCell'
import { useMemo } from 'react'

interface ComponentOverviewDataTableWithConfigProps {
  data: ComponentModel[]
  /** Optional config for preview cell customization */
  previewConfig?: PreviewCellConfig
}

/**
 * A client-side wrapper that creates columns with custom config.
 * Use this when you need custom column configuration from a server component.
 */
export default function ComponentOverviewDataTableWithConfig({
  data,
  previewConfig,
}: ComponentOverviewDataTableWithConfigProps) {
  const columns = useMemo(() => {
    if (previewConfig) {
      return createComponentOverviewColumns(previewConfig)
    }
    return ComponentOverviewColumns
  }, [previewConfig])

  return <ComponentOverviewDataTable columns={columns} data={data} />
}

