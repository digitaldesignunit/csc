'use client'

import UserItem from '@/components/auth/UserItem'
import AppMenu from './AppMenu'

export default function Sidebar() {
  return (
    <div className='fixed top-0 left-0 flex flex-col gap-4 w-[250px] h-screen p-4 justify-between overflow-hidden'>
      {/* User section at top */}
      <div>
        <UserItem/>
      </div>

      {/* Navigation menu */}
      <AppMenu />
    </div>
  )
}