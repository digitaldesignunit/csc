// ComponentOverviewColumns.tsx
'use client'

import { useState } from 'react'
import { ColumnDef } from '@tanstack/react-table'
import { ComponentModel, ExtendedComponentModel, ComponentBoundingBox } from '@/generated/ComponentModel'
import { formatTimestamp, rgbToHex } from '@/lib/utils'
import ComponentOverviewDataTablePreviewCell, { PreviewCellConfig } from './ComponentOverviewDataTablePreviewCell'
import ComponentOverviewDataTableHeader from './ComponentOverviewDataTableHeader'
import ComponentOverviewDataTableFilterCell from './ComponentOverviewDataTableFilterCell'
import ComponentOverviewDataTableLocationCell from './ComponentOverviewDataTableLocationCell'

function ComponentOverviewDataTableCopyIdCell({ componentId }: { componentId: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopyId = async () => {
    try {
      await navigator.clipboard.writeText(componentId ?? '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch (error) {
      console.error('Failed to copy component ID:', error)
    }
  }

  return (
    <div
      className={`relative inline-flex max-w-full items-center rounded px-1.5 py-0.5 text-xs truncate cursor-pointer font-mono ${
        copied
          ? 'bg-green-100 text-green-700 hover:bg-green-200 hover:text-green-800'
          : 'bg-muted text-foreground hover:bg-accent hover:text-accent-foreground'
      }`}
      onClick={handleCopyId}
      title={copied ? 'Copied component ID to clipboard' : 'Click to copy component ID to clipboard'}
    >
      <span className={`truncate ${copied ? 'opacity-0' : ''}`}>{componentId}</span>
      {copied && (
        <span className='absolute inset-0 flex items-center justify-center px-1.5 py-0.5'>
          Copied!
        </span>
      )}
    </div>
  )
}

/**
 * Creates component overview columns with customizable preview cell config.
 * This allows reuse for both regular components and archived components.
 */
export function createComponentOverviewColumns(
  previewConfig?: PreviewCellConfig
): ColumnDef<ComponentModel>[] {
  return [
    {
      accessorKey: 'name',
      header: () => <ComponentOverviewDataTableHeader header='Name' sortKey='name' />,
      meta: {
        // preview column: can compress a bit, then scroll
        colClassName: 'w-[200px] sm:w-[260px] md:w-[300px]',
        headerClassName: '',
        cellClassName: '',
      },
      cell: ({ row }) => (
        <ComponentOverviewDataTablePreviewCell
          component_data={row.original}
          config={previewConfig}
        />
      ),
    },
  {
    accessorKey: '_id',
    header: () => <ComponentOverviewDataTableHeader header='ID' sortKey='_id' />,
    meta: { colClassName: 'w-[220px] sm:w-[260px] md:w-[320px]' },
    cell: ({ row }) => {
      const componentId = row.getValue('_id') as string
      return <ComponentOverviewDataTableCopyIdCell componentId={componentId} />
    },
  },
  {
    accessorKey: 'type',
    header: () => <ComponentOverviewDataTableHeader header='Type' sortKey='type' />,
    meta: { colClassName: 'w-[120px] sm:w-[140px] md:w-[160px]' },
    cell: ({ row }) => {
      const component_type: string = row.getValue('type')
      return (
        <ComponentOverviewDataTableFilterCell
          param='comptype'
          value={component_type}
          titletext='Click to filter by this component type'
        />
      )
    },
  },
  {
    accessorKey: 'material',
    header: () => <ComponentOverviewDataTableHeader header='Material' sortKey='material' />,
    meta: { colClassName: 'w-[140px] sm:w-[160px] md:w-[200px]' },
    cell: ({ row }) => {
      const component_mat: string = row.getValue('material') ?? ''
      return (
        <ComponentOverviewDataTableFilterCell
          param='material'
          value={component_mat}
          titletext='Click to filter by this material'
        />
      )
    },
  },
  {
    accessorKey: 'dataset',
    header: () => <ComponentOverviewDataTableHeader header='Dataset' sortKey='dataset' />,
    meta: { colClassName: 'w-[160px] sm:w-[180px] md:w-[220px]' },
    cell: ({ row }) => {
      const component_dataset: string = row.getValue('dataset') ?? ''
      return (
        <ComponentOverviewDataTableFilterCell
          param='dataset'
          value={component_dataset}
          titletext='Click to filter by this dataset'
        />
      )
    },
  },
  {
    accessorKey: 'bbx',
    header: () => <ComponentOverviewDataTableHeader header='X' sortKey='bbx.0' />,
    meta: { colClassName: 'w-[84px] sm:w-[96px] text-left' },
    cell: ({ row }) => {
      const bbx: ComponentBoundingBox = row.getValue('bbx')
      // Debug logging to understand data structure
      // if (process.env.NODE_ENV === 'development') {
      //   console.log('[ComponentOverviewColumns] BBX data:', bbx, 'Type:', typeof bbx, 'IsArray:', Array.isArray(bbx))
      // }
      // Add defensive programming for unexpected data structures
      if (!bbx || !Array.isArray(bbx) || bbx.length < 1 || typeof bbx[0] !== 'number') {
        return <div className='text-xs text-muted-foreground'>N/A</div>
      }
      const x = bbx[0] // X dimension
      return <div className='text-xs tabular-nums text-left truncate'>{x.toFixed(2)}</div>
    },
  },
  {
    accessorKey: 'bbx_y',
    header: () => <ComponentOverviewDataTableHeader header='Y' sortKey='bbx.1' />,
    meta: { colClassName: 'w-[84px] sm:w-[96px] text-left' },
    cell: ({ row }) => {
      const bbx: ComponentBoundingBox = row.getValue('bbx')
      // Add defensive programming for unexpected data structures
      if (!bbx || !Array.isArray(bbx) || bbx.length < 2 || typeof bbx[1] !== 'number') {
        return <div className='text-xs text-muted-foreground'>N/A</div>
      }
      const y = bbx[1] // Y dimension
      return <div className='text-xs tabular-nums text-left truncate'>{y.toFixed(2)}</div>
    },
  },
  {
    accessorKey: 'bbx_z',
    header: () => <ComponentOverviewDataTableHeader header='Z' sortKey='bbx.2' />,
    meta: { colClassName: 'w-[84px] sm:w-[96px] text-left' },
    cell: ({ row }) => {
      const bbx: ComponentBoundingBox = row.getValue('bbx')
      // Add defensive programming for unexpected data structures
      if (!bbx || !Array.isArray(bbx) || bbx.length < 3 || typeof bbx[2] !== 'number') {
        return <div className='text-xs text-muted-foreground'>N/A</div>
      }
      const z = bbx[2] // Z dimension
      return <div className='text-xs tabular-nums text-left truncate'>{z.toFixed(2)}</div>
    },
  },
  {
    accessorKey: 'color',
    header: () => <ComponentOverviewDataTableHeader header='Color' sortKey='color' />,
    meta: { colClassName: 'w-[140px] sm:w-[160px]' },
    cell: ({ row }) => {
      const color: number[] = row.getValue('color')
      const [r, g, b] = color.map(v => Math.round(v))
      const hex = rgbToHex(r, g, b)
      return (
        <div className='flex items-center min-w-0'>
          <div className='h-4 w-4 rounded-full shrink-0 border' style={{ backgroundColor: hex }} />
          <div className='px-2 text-xs tabular-nums truncate'>{r}/{g}/{b}</div>
        </div>
      )
    },
  },
  {
    accessorKey: 'fragment',
    header: () => <ComponentOverviewDataTableHeader header='Fragment' />,
    meta: { colClassName: 'w-[96px] sm:w-[112px]' },
    cell: ({ row }) => {
      const fragment: boolean = row.getValue('fragment')
      return <div className='text-xs truncate'>{fragment.toString()}</div>
    },
  },
  {
    accessorKey: 'complexity',
    header: () => <ComponentOverviewDataTableHeader header='Complexity' />,
    meta: { colClassName: 'w-[100px] sm:w-[112px] text-center' },
    cell: ({ row }) => {
      const complexity: number = row.getValue('complexity')
      return <div className='text-xs tabular-nums text-center truncate'>{complexity}</div>
    },
  },
  {
    accessorKey: 'location',
    header: () => <ComponentOverviewDataTableHeader header='Location' />,
    meta: { colClassName: 'w-[180px] sm:w-[220px] md:w-[260px]' },
    cell: ({ row }) => (
      <div className='text-xs min-w-0 truncate'>
        <ComponentOverviewDataTableLocationCell coords={row.getValue('location')} />
      </div>
    ),
  },
  {
    accessorKey: 'created',
    header: () => <ComponentOverviewDataTableHeader header='Created' sortKey='created' />,
    meta: { colClassName: 'w-[180px] sm:w-[200px]' },
    cell: ({ row }) => (
      <div className='text-xs truncate'>{formatTimestamp(row.getValue('created'))}</div>
    ),
  },
  {
    accessorKey: 'lastmodified',
    header: () => <ComponentOverviewDataTableHeader header='Last Modified' sortKey='lastmodified' />,
    meta: { colClassName: 'w-[200px] sm:w-[220px]' },
    cell: ({ row }) => (
      <div className='text-xs truncate'>{formatTimestamp(row.getValue('lastmodified'))}</div>
    ),
  },
  {
    accessorKey: 'reserved',
    header: () => <ComponentOverviewDataTableHeader header='Reserved' />,
    meta: { colClassName: 'w-[140px] sm:w-[160px]' },
    cell: ({ row }) => {
      const reserved: string | null = row.getValue('reserved')
      // Access reserved_by_username from the raw data, not as a table column
      const reservedByUsername: string | undefined = (row.original as ExtendedComponentModel).reserved_by_username
      if (!reserved) {
        return (
          <div className='text-xs text-muted-foreground'>
            Available
          </div>
        )
      }
      return (
        <div className='text-xs'>
          <div className='flex items-center gap-1'>
            <div className='w-2 h-2 rounded-full bg-orange-500'></div>
            <span className='text-orange-600 font-medium'>Reserved</span>
          </div>
          <div className='text-xs text-muted-foreground truncate' title={reservedByUsername || 'Unknown User'}>
            by {reservedByUsername || 'Unknown User'}
          </div>
        </div>
      )
    },
  },
  ]
}

// Default columns for regular components (backwards compatible)
export const ComponentOverviewColumns = createComponentOverviewColumns()
