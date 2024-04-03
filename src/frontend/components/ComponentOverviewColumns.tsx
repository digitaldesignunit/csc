'use client';

import { ColumnDef, createColumnHelper } from "@tanstack/react-table";
import { ComponentData } from "./models";
import { rgbToHex } from "@/lib/utils";
import ComponentDrawer from "./ComponentDrawer";

const columnHelper = createColumnHelper<ComponentData>()

export const ComponentOverviewColumns: ColumnDef<ComponentData>[] = [
  {
    accessorKey: '_id',
    header: () => <div className="text-left">ID (Click to open preview)</div>,
    cell: ({ row }) => {
        const component_id: string = row.getValue('_id')
      return (
        <div className='text-left align-text-top font-bold'>
          <ComponentDrawer component_data={row.original} />
        </div>
      );}
  },
  {
    accessorKey: 'type',
    header: () => <div className="align-top">Type</div>,
    cell: ({ row }) => {
      const component_type: string = row.getValue('type')
    return (
      <div className='text-left align-text-top'>
        {component_type}
      </div>
    );}
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
    );}
  },
  {
    accessorKey: 'materialthickness',
    header: 'Z',
  },
  {
    accessorKey: 'color',
    header: 'Color',
    cell: ({ row }) => {
      const color: number[] = row.getValue('color');
      const colR = Math.round(color[0]);
      const colG = Math.round(color[1]);
      const colB = Math.round(color[2]);
      const hexcol = rgbToHex(colR, colG, colB)
      return (
        <div className="flex items-center max-w-12">
          <div className="avatar rounded-full min-h-4 min-w-4 max-w-5 max-h-5 items-center justify-left" style={{backgroundColor: hexcol}}></div>
          <div className="px-2 items-center justify-center text-center text">{colR}/{colG}/{colB}</div>
        </div>
    );}
  },
]