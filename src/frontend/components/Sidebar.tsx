'use client'

import UserItem from './UserItem'
import AppMenu from './AppMenu'

export default function Sidebar() {

  return (
    <div className='fixed flex flex-col gap-4 w-[250px] min-w-[250px] p-4 h-[95dvh] justify-between'>
      
      {/* <div>
        <UserItem/>
      </div> */}

      <AppMenu />

    </div>
  )
}