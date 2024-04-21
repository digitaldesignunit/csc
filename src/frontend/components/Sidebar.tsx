'use client'

import UserItem from "./UserItem";
import AppMenu from "./AppMenu";

export default function Sidebar() {

  return (
    <div className="fixed flex flex-col gap-4 w-[300px] min-w-[300px] p-4 min-h-screen">
      
      {/* <div>
        <UserItem/>
      </div> */}

      <AppMenu />

    </div>
  );
}