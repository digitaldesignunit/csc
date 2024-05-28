'use client';

import { ColumnDef, createColumnHelper } from "@tanstack/react-table";
import { ComponentData } from "./models";
import { rgbToHex } from "@/lib/utils";
import ComponentSheet from "./ComponentSheet";

const columnHelper = createColumnHelper<ComponentData>()

export const ComponentOverviewColumns: ColumnDef<ComponentData>[] = [
  {
    accessorKey: '_id',
    header: () => <div className="text-left">ID</div>,
    cell: ({ row }) => {
      return (
          <ComponentSheet component_data={row.original} />
      );}
  },
  // {
  //   accessorKey: 'bbx',
  //   header: () => <div className="align-top">BBX</div>,
  //   cell: ({ row }) => {
  //     const component_bbx: string = row.original.bbx.xy.toString()
  //   return (
  //     <div className='text-left align-text-top'>
  //       {component_bbx}
  //     </div>
  //   )}
  // },
  {
    accessorKey: 'type',
    header: () => <div className="align-top">Type</div>,
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
    accessorKey: 'materialthickness',
    header: 'Z',
    cell: ({ row }) => {
      const component_z: number = Math.round(row.getValue('materialthickness'))
    return (
      <div className='text-left align-text-top'>
        {component_z}
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
        <div className="flex items-center max-w-12">
          <div className="avatar rounded-full min-h-4 min-w-4 max-w-4 max-h-4 items-center justify-left" style={{backgroundColor: hexcol}}></div>
          <div className="px-2 items-center justify-center text-center text">{colR}/{colG}/{colB}</div>
        </div>
    )}
  },
]