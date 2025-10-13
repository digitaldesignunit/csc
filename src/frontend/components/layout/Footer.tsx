'use client';

import { copyright_year } from '@/lib/utils'

export default function Footer() {
  return (
      <div className='flex flex-col sm:flex-row gap-2 p-2 border-t text-xs text-center justify-center items-center'>
        <p>
          &copy; {copyright_year()} < a href='https://maxeschenbach.com/' target='_blank' className='hover:underline'>Max Benjamin Eschenbach</a> • powered by{' '}
          <a href='https://www.dg.architektur.tu-darmstadt.de/' target='_blank' className='hover:underline'>Digital Design Unit (DDU)</a>
          {' '}•{' '}
          <a href='/settings' className='hover:underline text-muted-foreground hover:text-foreground'>Cookie Settings</a>
        </p>
      </div>
  );
}