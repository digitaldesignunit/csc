'use client';

import { copyright_year } from '@/lib/utils'

export default function Footer() {
  return (
      <div className='flex gap-2 p-2 border-t text-xs text-center justify-center'>
        <p>&copy; {copyright_year()} <a href='https://www.dg.architektur.tu-darmstadt.de/fachgebiet_ddu/index.en.jsp' target='_blank'>Digital Design Unit (DDU)</a></p>
      </div>
  );
}