'use client';

import { copyright_year } from '@/lib/utils'

export default function Footer() {
  return (
      <div className='flex flex-col sm:flex-row gap-2 p-2 border-t text-xs text-center justify-center items-center'>
        <p>&copy; {copyright_year()} <a href='https://www.dg.architektur.tu-darmstadt.de/fachgebiet_ddu/index.en.jsp' target='_blank' className='hover:underline'>Digital Design Unit (DDU)</a></p>
        <span className='hidden sm:inline'>•</span>
        <a href='/settings' className='hover:underline text-muted-foreground hover:text-foreground'>Cookie Settings</a>
      </div>
  );
}