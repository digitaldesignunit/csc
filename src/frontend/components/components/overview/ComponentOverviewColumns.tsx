// ComponentOverviewColumns.tsx
'use client'

import { useState } from 'react'
import { ColumnDef } from '@tanstack/react-table'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { SHAPE_CLASS_LABELS, ORIGINAL_FUNCTION_LABELS, vocabLabel } from '@/generated/Vocab'
import ChipView from '@/components/common/ChipView'
import { useMaterials } from '@/lib/lineage'
import { piecesNote, rowStatus, sizeLabel } from '@/lib/browse'
import { formatDay, formatTimestamp, rgbToHex } from '@/lib/utils'
import ComponentOverviewDataTablePreviewCell from './ComponentOverviewDataTablePreviewCell'
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

/** The material by its label in the materials list, as a filter cell. */
function MaterialCell({ id }: { id: string }) {
  const materials = useMaterials(true)
  const label = materials.find((m) => m._id === id)?.label ?? id
  return (
    <ComponentOverviewDataTableFilterCell
      param='material'
      value={id}
      label={label}
      titletext='Click to filter by this material'
    />
  )
}

type Column = ColumnDef<CatalogShallowRow>

/** The eight columns of the table (decision 8.118 Q6). */
const BASE: Record<string, Column> = {
  name: {
    id: 'name',
    accessorKey: 'name',
    header: () => <ComponentOverviewDataTableHeader header='Name' sortKey='name' />,
    meta: { colClassName: 'w-[26%]' },
    cell: ({ row }) => <ComponentOverviewDataTablePreviewCell component_data={row.original} />,
  },
  original_function: {
    id: 'original_function',
    accessorKey: 'original_function',
    header: () => <ComponentOverviewDataTableHeader header='Function' sortKey='original_function' />,
    meta: { colClassName: 'w-[11%]' },
    cell: ({ row }) => {
      const value: string = row.getValue('original_function')
      return (
        <ComponentOverviewDataTableFilterCell
          param='original_function'
          value={value}
          label={vocabLabel(ORIGINAL_FUNCTION_LABELS, value)}
          titletext='Click to filter by this original function'
        />
      )
    },
  },
  material: {
    id: 'material',
    accessorKey: 'material',
    header: () => <ComponentOverviewDataTableHeader header='Material' sortKey='material' />,
    meta: { colClassName: 'w-[16%]' },
    cell: ({ row }) => <MaterialCell id={(row.getValue('material') as string | null) ?? ''} />,
  },
  dataset: {
    id: 'dataset',
    accessorKey: 'dataset',
    header: () => <ComponentOverviewDataTableHeader header='Dataset' sortKey='dataset' />,
    meta: { colClassName: 'w-[16%]' },
    cell: ({ row }) => {
      const value: string = row.getValue('dataset') ?? ''
      return (
        <ComponentOverviewDataTableFilterCell
          param='dataset'
          value={value}
          titletext='Click to filter by this dataset'
        />
      )
    },
  },
  size: {
    id: 'size',
    accessorFn: (row) => sizeLabel(row.bbx),
    header: () => <ComponentOverviewDataTableHeader header='Size (mm)' sortKey='bbx.0' />,
    meta: { colClassName: 'w-[13%]' },
    cell: ({ row }) => {
      const text = sizeLabel(row.original.bbx)
      return text
        ? <div className='text-xs tabular-nums truncate'>{text}</div>
        : <div className='text-xs text-muted-foreground'>N/A</div>
    },
  },
  shape_class: {
    id: 'shape_class',
    accessorKey: 'shape_class',
    header: () => <ComponentOverviewDataTableHeader header='Shape class' sortKey='shape_class' />,
    meta: { colClassName: 'w-[8%]' },
    cell: ({ row }) => {
      const value = row.original.shape_class
      return value
        ? <ComponentOverviewDataTableFilterCell
            param='shape_class'
            value={value}
            label={vocabLabel(SHAPE_CLASS_LABELS, value)}
            titletext='Click to filter by this shape class'
          />
        : <div className='text-xs text-muted-foreground'>N/A</div>
    },
  },
  status: {
    id: 'status',
    accessorFn: (row) => rowStatus(row).label,
    header: () => <ComponentOverviewDataTableHeader header='Status' />,
    meta: { colClassName: 'w-[10%]' },
    cell: ({ row }) => {
      const pieces = piecesNote(row.original)
      return (
        <div className='flex flex-wrap items-center gap-1.5'>
          <ChipView chip={rowStatus(row.original)} />
          {pieces && <span className='text-xs text-muted-foreground'>{pieces}</span>}
        </div>
      )
    },
  },
}

/** The columns the picker can add (decision 8.118 Q6). */
const OPTIONAL: Record<string, Column> = {
  _id: {
    id: '_id',
    accessorKey: '_id',
    header: () => <ComponentOverviewDataTableHeader header='Identity id' sortKey='_id' />,
    meta: { colClassName: 'w-[300px]' },
    cell: ({ row }) => <ComponentOverviewDataTableCopyIdCell componentId={row.getValue('_id') as string} />,
  },
  color: {
    id: 'color',
    accessorKey: 'color',
    header: () => <ComponentOverviewDataTableHeader header='Colour' sortKey='color' />,
    meta: { colClassName: 'w-[140px]' },
    cell: ({ row }) => {
      const color = row.getValue('color') as number[] | null | undefined
      // a state recorded without a colour (an imported piece, say) has none
      if (!Array.isArray(color) || color.length < 3) {
        return <div className='text-xs text-muted-foreground'>N/A</div>
      }
      const [r, g, b] = color.map((v) => Math.round(v))
      return (
        <div className='flex items-center min-w-0'>
          <div className='h-4 w-4 rounded-full shrink-0 border' style={{ backgroundColor: rgbToHex(r, g, b) }} />
          <div className='px-2 text-xs tabular-nums truncate'>{r}/{g}/{b}</div>
        </div>
      )
    },
  },
  fragment: {
    id: 'fragment',
    accessorKey: 'fragment',
    header: () => <ComponentOverviewDataTableHeader header='Fragment' />,
    meta: { colClassName: 'w-[100px]' },
    cell: ({ row }) => <div className='text-xs truncate'>{row.original.fragment ? 'yes' : 'no'}</div>,
  },
  complexity: {
    id: 'complexity',
    accessorKey: 'complexity',
    header: () => <ComponentOverviewDataTableHeader header='Complexity' sortKey='complexity' />,
    meta: { colClassName: 'w-[110px]' },
    cell: ({ row }) => <div className='text-xs tabular-nums truncate'>{row.original.complexity ?? ''}</div>,
  },
  location: {
    id: 'location',
    accessorKey: 'location',
    header: () => <ComponentOverviewDataTableHeader header='Location' />,
    meta: { colClassName: 'w-[220px]' },
    cell: ({ row }) => {
      const coords = row.getValue('location') as Parameters<typeof ComponentOverviewDataTableLocationCell>[0]['coords'] | null
      // a state recorded without a location has none
      return (
        <div className='text-xs min-w-0 truncate'>
          {coords ? <ComponentOverviewDataTableLocationCell coords={coords} /> : <span className='text-muted-foreground'>N/A</span>}
        </div>
      )
    },
  },
  created: {
    id: 'created',
    accessorKey: 'created',
    header: () => <ComponentOverviewDataTableHeader header='Created' sortKey='created' />,
    meta: { colClassName: 'w-[170px]' },
    cell: ({ row }) => <div className='text-xs truncate' title={formatTimestamp(row.getValue('created'))}>{formatDay(row.getValue('created'))}</div>,
  },
  lastmodified: {
    id: 'lastmodified',
    accessorKey: 'lastmodified',
    header: () => <ComponentOverviewDataTableHeader header='Last modified' sortKey='lastmodified' />,
    meta: { colClassName: 'w-[170px]' },
    cell: ({ row }) => <div className='text-xs truncate' title={formatTimestamp(row.getValue('lastmodified'))}>{formatDay(row.getValue('lastmodified'))}</div>,
  },
}

/** The base columns, then the picked optional ones in the picker's order. */
export function buildColumns(picked: string[]): Column[] {
  return [
    ...Object.values(BASE),
    ...Object.keys(OPTIONAL).filter((key) => picked.includes(key)).map((key) => OPTIONAL[key]),
  ]
}
