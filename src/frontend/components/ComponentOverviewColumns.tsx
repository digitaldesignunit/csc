// ComponentOverviewColumns.tsx
'use client'

import { ColumnDef } from '@tanstack/react-table'
import { ComponentData, ComponentBoundingBox } from './models'
import { formatTimestamp, rgbToHex } from '@/lib/utils'
import ComponentOverviewDataTablePreviewCell from './ComponentOverviewDataTablePreviewCell'
import ComponentOverviewDataTableHeader from './ComponentOverviewDataTableHeader'
import ComponentOverviewDataTableFilterCell from './ComponentOverviewDataTableFilterCell'
import ComponentOverviewDataTableLocationCell from './ComponentOverviewDataTableLocationCell'

export const ComponentOverviewColumns: ColumnDef<ComponentData>[] = [
  {
    accessorKey: '_id',
    header: () => <ComponentOverviewDataTableHeader header='ID' />,
    meta: {
      // preview column: can compress a bit, then scroll
      colClassName: 'w-[200px] sm:w-[260px] md:w-[300px]',
      headerClassName: '',
      cellClassName: '',
    },
    cell: ({ row }) => (
      <ComponentOverviewDataTablePreviewCell component_data={row.original} />
    ),
  },
  {
    accessorKey: 'type',
    header: () => <ComponentOverviewDataTableHeader header='Type' />,
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
    header: () => <ComponentOverviewDataTableHeader header='Material' />,
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
    accessorKey: 'bbx',
    header: () => <ComponentOverviewDataTableHeader header='X' />,
    meta: { colClassName: 'w-[84px] sm:w-[96px] text-left' },
    cell: ({ row }) => {
      const bbx: ComponentBoundingBox = row.getValue('bbx')
      const x = bbx[1][0] - bbx[0][0]
      return <div className='text-xs tabular-nums text-left truncate'>{x.toFixed(2)}</div>
    },
  },
  {
    accessorKey: 'bbx_y',
    header: () => <ComponentOverviewDataTableHeader header='Y' />,
    meta: { colClassName: 'w-[84px] sm:w-[96px] text-left' },
    cell: ({ row }) => {
      const bbx: ComponentBoundingBox = row.getValue('bbx')
      const y = bbx[1][1] - bbx[0][1]
      return <div className='text-xs tabular-nums text-left truncate'>{y.toFixed(2)}</div>
    },
  },
  {
    accessorKey: 'bbx_z',
    header: () => <ComponentOverviewDataTableHeader header='Z' />,
    meta: { colClassName: 'w-[84px] sm:w-[96px] text-left' },
    cell: ({ row }) => {
      const bbx: ComponentBoundingBox = row.getValue('bbx')
      const z = bbx[1][2] - bbx[0][2]
      return <div className='text-xs tabular-nums text-left truncate'>{z.toFixed(2)}</div>
    },
  },
  {
    accessorKey: 'color',
    header: () => <ComponentOverviewDataTableHeader header='Color' />,
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
    header: () => <ComponentOverviewDataTableHeader header='Created' />,
    meta: { colClassName: 'w-[180px] sm:w-[200px]' },
    cell: ({ row }) => (
      <div className='text-xs truncate'>{formatTimestamp(row.getValue('created'))}</div>
    ),
  },
  {
    accessorKey: 'lastmodified',
    header: () => <ComponentOverviewDataTableHeader header='Last Modified' />,
    meta: { colClassName: 'w-[200px] sm:w-[220px]' },
    cell: ({ row }) => (
      <div className='text-xs truncate'>{formatTimestamp(row.getValue('lastmodified'))}</div>
    ),
  },
]
