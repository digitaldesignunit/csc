'use client'

import { Bell, FileLock, Inbox, ReceiptText, ScrollText, Settings, User } from "lucide-react";
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
          icon: <User/>,
          text: "Profile"
        },
        {
          link: "/",
          icon: <Inbox/>,
          text: "Inbox"
        },
        {
          link: "/components",
          icon: <ReceiptText/>,
          text: "Components"
        },
      ]
      },
      {
        group: "Settings",
        items: [
          {
            link: "/",
            icon: <Settings/>,
            text: "General Settings"
          },
          {
            link: "/",
            icon: <FileLock/>,
            text: "Privacy"
          },
          {
            link: "/",
            icon: <Bell/>,
            text: "Notifications"
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
    <div className="fixed flex flex-col gap-4 w-[300px] min-w-[300px] border-r min-h-screen p-4">
      <div>
        <UserItem/>
      </div>
      <div className="grow">
        <Command style={{ overflow: 'visible' }}>
          <CommandList style={{ overflow: 'visible' }}>
            {menuList.map((menu: any, key: number) =>
              <CommandGroup key={key} heading={menu.group}>
                {menu.items.map((option: any, optionKey: number) => 
                  <Link key={optionKey} href={option.link}>
                    <CommandItem key={optionKey} className="flex gap-2 cursor-pointer">
                      {option.icon}
                      {option.text}
                    </CommandItem>
                  </Link>
                )}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </div>
      <div>Settings / Notifications</div>
    </div>
  );
}