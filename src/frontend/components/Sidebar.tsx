'use client'

import { Bell, FileLock, HomeIcon, Inbox, ReceiptText, ScrollText, Settings, User } from "lucide-react";
import { Command, CommandGroup, CommandItem, CommandList } from "./ui/command";
import UserItem from "./UserItem";
import Link from "next/link";

export default function Sidebar() {

  const menuList = [
    {
      group: "General",
      items: [
        {
          link: "/",
          icon: <HomeIcon />,
          text: "Home"
        },
        {
          link: "/components",
          icon: <ReceiptText/>,
          text: "Component Overview"
        },
      ]
      },
      {
        group: "Misc",
        items: [
          {
            link: "/settings",
            icon: <Settings/>,
            text: "Settings"
          },
          {
            link: "/",
            icon: <FileLock/>,
            text: "Privacy"
          },
          {
            link: "/",
            icon: <ScrollText/>,
            text: "Logs"
          },
        ]
      }
    ]

  return (
    <div className="fixed flex flex-col gap-4 w-[300px] min-w-[300px] p-4 min-h-screen">
      
      <div>
        <UserItem/>
      </div>

      <div className="grow">
        <Command style={{ overflow: 'visible' }} className="rounded-lg">
          <CommandList style={{ overflow: 'visible' }}>
              <CommandGroup heading={menuList[0].group}>
                {menuList[0].items.map((option: any, optionKey: number) => 
                  <Link key={optionKey} href={option.link}>
                    <CommandItem key={optionKey} className="flex gap-2 cursor-pointer">
                      {option.icon}
                      {option.text}
                    </CommandItem>
                  </Link>
                )}
              </CommandGroup>
          </CommandList>
        </Command>
      </div>

      <div>
        <Command style={{ overflow: 'visible' }} className="rounded-lg">
          <CommandList style={{ overflow: 'visible' }}>
              <CommandGroup heading={menuList[1].group}>
                {menuList[1].items.map((option: any, optionKey: number) => 
                  <Link key={optionKey} href={option.link}>
                    <CommandItem key={optionKey} className="flex gap-2 cursor-pointer">
                      {option.icon}
                      {option.text}
                    </CommandItem>
                  </Link>
                )}
              </CommandGroup>
          </CommandList>
        </Command>
      </div>
    </div>
  );
}