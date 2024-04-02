'use client';

import { ColumnDef } from "@tanstack/react-table";
import { ComponentData } from "./models";
import { MoreHorizontal } from "lucide-react";

function rgbToHex(r: number, g: number, b: number) {
  return (
    "#" + ((1<<24) + (r<<16) + (g<<8)+ b).toString(16).slice(1)
  );
}

function invertColor(hex: string, bw: boolean = true) {
  if (hex.indexOf('#') === 0) {
      hex = hex.slice(1);
  }
  // convert 3-digit hex to 6-digits.
  if (hex.length === 3) {
      hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  }
  if (hex.length !== 6) {
      throw new Error('Invalid HEX color.');
  }
  var rnum = parseInt(hex.slice(0, 2), 16)
  var gnum = parseInt(hex.slice(2, 4), 16)
  var bnum = parseInt(hex.slice(4, 6), 16)
  if (bw) {
      // https://stackoverflow.com/a/3943023/112731
      return (rnum * 0.299 + gnum * 0.587 + bnum * 0.114) > 186
          ? '#000000'
          : '#FFFFFF';
  }
  // invert color components
  var r = (255 - rnum).toString(16);
  var g = (255 - gnum).toString(16);
  var b = (255 - bnum).toString(16);
  // pad each with zeros and return
  return "#" + padZero(r) + padZero(g) + padZero(b);
}

function padZero(str: string, len: number = 2) {
  len = len || 2;
  var zeros = new Array(len).join('0');
  return (zeros + str).slice(-len);
}

export const ComponentOverviewColumns: ColumnDef<ComponentData>[] = [
  {
    accessorKey: '_id',
    header: () => <div className="text-left">ID</div>,
    cell: ({ row }) => {
        const component_id: string = row.getValue('_id')
      return (
        <>
        <div className='text-left align-text-top font-bold'>
          {component_id}
        </div>
        </>
      );}
  },
  {
    accessorKey: 'type',
    header: () => <div className="align-top">Type</div>,
  },
  {
    accessorKey: 'material',
    header: 'Material',
  },
  {
    accessorKey: 'materialthickness',
    header: 'Mat. Thickness',
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
          <div className="avatar rounded-full min-h-5 min-w-5 max-w-5 max-h-5 items-center justify-left" style={{backgroundColor: hexcol}}></div>
          <div className="px-2 items-center justify-center text-center text">{colR}/{colG}/{colB}</div>
        </div>
    );}
  },
]