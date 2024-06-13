'use client'

import { ColumnDef, createColumnHelper } from '@tanstack/react-table'
import { ComponentData, ComponentBoundingBox, ComponentPolylinePoints } from './models'
import { rgbToHex } from '@/lib/utils'
import ComponentSheet from './ComponentSheet'
import ComponentPreviewImage from './ComponentPreviewImage'

const columnHelper = createColumnHelper<ComponentData>()

export const ComponentOverviewColumns: ColumnDef<ComponentData>[] = [
  {
    accessorKey: '_id',
    header: () => <div className='text-left'>ID</div>,
    cell: ({ row }) => {
      return (
          <ComponentSheet component_data={row.original} />
      )}
  },
  {
    accessorKey: 'type',
    header: () => <div className='align-top'>Type</div>,
    cell: ({ row }) => {
      const component_type: string = row.getValue('type')
    return (
      <div className='text-left align-text-top'>
        {component_type}
      </div>
    )}
  },
  {
    accessorKey: 'material',
    header: 'Material',
    cell: ({ row }) => {
      const component_mat: string = row.getValue('material')
    return (
      <div className='text-left align-text-top'>
        {component_mat}
      </div>
    )}
  },
  {
    accessorKey: 'bbx',
    header: 'X',
    cell: ({ row }) => {
      const component_bbx: ComponentBoundingBox = row.getValue('bbx')
      const component_bbx_xy: ComponentPolylinePoints = component_bbx.xy
      const component_bbx_xyz: ComponentPolylinePoints = component_bbx.xyz
      let component_bbx_x: number = 0
      if (component_bbx_xy) {
        component_bbx_x = component_bbx_xy[1][0] - component_bbx_xy[0][0]
      }
      else {
        component_bbx_x = component_bbx_xyz[1][0] - component_bbx_xyz[0][0]
      }
    return (
      <div className='text-left align-text-top'>
        {component_bbx_x.toFixed(2)}
      </div>
    )}
  },
  {
    accessorKey: 'bbx',
    header: 'Y',
    cell: ({ row }) => {
      const component_bbx: ComponentBoundingBox = row.getValue('bbx')
      const component_bbx_xy: ComponentPolylinePoints = component_bbx.xy
      const component_bbx_xyz: ComponentPolylinePoints = component_bbx.xyz
      let component_bbx_y: number = 0
      if (component_bbx_xy) {
        component_bbx_y = component_bbx_xy[2][1] - component_bbx_xy[1][1]
      }
      else {
        component_bbx_y = component_bbx_xyz[2][1] - component_bbx_xyz[1][1]
      }
    return (
      <div className='text-left align-text-top'>
        {component_bbx_y.toFixed(2)}
      </div>
    )}
  },
  {
    accessorKey: 'materialthickness',
    header: 'Z',
    cell: ({ row }) => {
      const component_z: number = Math.round(row.getValue('materialthickness'))
    return (
      <div className='text-left align-text-top'>
        {component_z.toFixed(2)}
      </div>
    )}
  },
  {
    accessorKey: 'color',
    header: 'Color',
    cell: ({ row }) => {
      const color: number[] = row.getValue('color')
      const colR = Math.round(color[0])
      const colG = Math.round(color[1])
      const colB = Math.round(color[2])
      const hexcol = rgbToHex(colR, colG, colB)
      return (
        <div className='flex items-center'>
          <div className='avatar rounded-full min-h-4 min-w-4 max-w-4 max-h-4 items-center justify-left' style={{backgroundColor: hexcol}}></div>
          <div className='px-2 items-center justify-center text-center text'>{colR}/{colG}/{colB}</div>
        </div>
    )}
  },
  {
    accessorKey: 'created',
    header: 'Created',
    cell: ({ row }) => {
      const creation_date: string = row.getValue('created')
    return (
      <div className='text-left align-text-top'>
        {creation_date}
      </div>
    )}
  },
]