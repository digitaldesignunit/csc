'use client'

import { ColumnDef } from '@tanstack/react-table'
import { ComponentData, ComponentBoundingBox, ComponentPolylinePoints } from './models'
import { formatLocationMapsLink, rgbToHex } from '@/lib/utils'
import ComponentSheet from './ComponentSheet'
import ComponentOverviewDataTableHeader from './ComponentOverviewDataTableHeader'
import { formatTimestamp, formatLocation } from '@/lib/utils'
import Link from 'next/link'

export const ComponentOverviewColumns: ColumnDef<ComponentData>[] = [
  {
    accessorKey: '_id',
    header: () => <ComponentOverviewDataTableHeader header='ID'/>,
    cell: ({ row }) => {
      return (
          <ComponentSheet component_data={row.original} />
      )}
  },
  {
    accessorKey: 'type',
    header: () => <ComponentOverviewDataTableHeader header='Type'/>,
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
    header: () => <ComponentOverviewDataTableHeader header='Material'/>,
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
    header: () => <ComponentOverviewDataTableHeader header='X'/>,
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
    header: () => <ComponentOverviewDataTableHeader header='Y'/>,
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
    header: () => <ComponentOverviewDataTableHeader header='Z'/>,
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
    header: () => <ComponentOverviewDataTableHeader header='Color'/>,
    cell: ({ row }) => {
      const color: number[] = row.getValue('color')
      const colR = Math.round(color[0])
      const colG = Math.round(color[1])
      const colB = Math.round(color[2])
      const hexcol = rgbToHex(colR, colG, colB)
      return (
        <div className='flex items-center'>
          <div className='avatar rounded-full min-h-4 min-w-4 max-w-4 max-h-4 items-center justify-left' style={{backgroundColor: hexcol}}></div>
          <div className='px-2 items-center justify-center text-center text-xs'>{colR}/{colG}/{colB}</div>
        </div>
    )}
  },
  {
    accessorKey: 'fragment',
    header: () => <ComponentOverviewDataTableHeader header='Fragment'/>,
    cell: ({ row }) => {
      const complexity: boolean = row.getValue('fragment')
    return (
      <div className='text-left align-text-top'>
        {complexity.toString()}
      </div>
    )}
  },
  {
    accessorKey: 'complexity',
    header: () => <ComponentOverviewDataTableHeader header='Complexity'/>,
    cell: ({ row }) => {
      const complexity: number = row.getValue('complexity')
    return (
      <div className='text-center align-text-top'>
        {complexity.toString()}
      </div>
    )}
  },
  {
    accessorKey: 'location',
    header: () => <ComponentOverviewDataTableHeader header='Location'/>,
    cell: ({ row }) => {
      const location: string = formatLocation(row.getValue('location'))
      const locationlink: string = formatLocationMapsLink(row.getValue('location'))
    return (
      <div className='text-left align-text-top text-xs'>
          <a href={locationlink}
            target="_blank"
            rel="noopener noreferrer"
            className='hover:text-gray-500'>
            {location}
          </a>
      </div>
    )}
  },
  {
    accessorKey: 'created',
    header: () => <ComponentOverviewDataTableHeader header='Created'/>,
    cell: ({ row }) => {
      const creation_date: string = formatTimestamp(row.getValue('created'))
    return (
      <div className='text-left align-text-top text-xs'>
        {creation_date}
      </div>
    )}
  },
  {
    accessorKey: 'lastmodified',
    header: () => <ComponentOverviewDataTableHeader header='Last Modified'/>,
    cell: ({ row }) => {
      const modified_date: string = formatTimestamp(row.getValue('lastmodified'))
    return (
      <div className='text-left align-text-top text-xs'>
        {modified_date}
      </div>
    )}
  }
]