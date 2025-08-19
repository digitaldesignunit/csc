'use client'

import { BookOpenText} from 'lucide-react'
import AppMenu from './AppMenu'
import ThemeToggle from './ThemeToggle'

export default function Header() {
  return (
    <>
      <div className='flex gap-4 p-4 border-b font-bold grow'>
        <BookOpenText /><h1>Catalogue of Second Chances</h1><ThemeToggle />
      </div>

      

      <div className='md:hidden p-4'>
        <AppMenu />
      </div>
    </>
  )
}