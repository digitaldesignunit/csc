'use client';

import { FileLock, HomeIcon, QrCode, ReceiptText, ScrollText, Settings } from "lucide-react";
import { Command, CommandGroup, CommandItem, CommandList } from "./ui/command";
import Link from "next/link";

export default function AppMenu() {

  const menuList = [
    {
      group: "General",
      items: [
        {
          id: "homebutton",
          link: "/",
          icon: <HomeIcon />,
          text: "Home"
        },
        {
          id: "componentoverviewbutton",
          link: "/components",
          icon: <ReceiptText />,
          text: "Component Overview"
        },
        {
          id: "findcomponentbutton",
          link: "/findcomponent",
          icon: <QrCode />,
          text: "Find Component"
        },
      ]
      },
      {
        group: "Misc",
        items: [
          {
            id: "settingsbutton",
            link: "/settings",
            icon: <Settings />,
            text: "Settings"
          },
          {
            id: "privacybutton",
            link: "/",
            icon: <FileLock />,
            text: "Privacy"
          },
          {
            id: "logsbutton",
            link: "/",
            icon: <ScrollText />,
            text: "Logs"
          },
        ]
      }
    ]

  return (
    <>
      <div className="grow">
          <Command style={{ overflow: 'visible' }} className="rounded-lg">
            <CommandList style={{ overflow: 'visible' }}>
                <CommandGroup heading={menuList[0].group}>
                  {menuList[0].items.map((option: any, optionKey: number) => 
                    <Link key={optionKey} href={option.link}>
                      <CommandItem id={option.id} key={optionKey} className="flex gap-2 cursor-pointer">
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
                      <CommandItem id={option.id} key={optionKey} className="flex gap-2">
                        {option.icon}
                        {option.text}
                      </CommandItem>
                    </Link>
                  )}
                </CommandGroup>
            </CommandList>
          </Command>
        </div>
      </>
  );
}