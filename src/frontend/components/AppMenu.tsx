'use client'

import { HomeIcon, QrCode, Package, Puzzle, Asterisk, BookText } from 'lucide-react'
import { Command, CommandGroup, CommandItem, CommandList } from './ui/command'
import Link from 'next/link'
import type { ReactNode } from 'react'

type MenuItem = {
  id: string
  link: string
  icon: ReactNode
  text: string
}

type MenuGroup = {
  group: string
  items: MenuItem[]
}

export default function AppMenu() {
  const menuList: MenuGroup[] = [
    {
      group: 'General',
      items: [
        { id: 'homebutton', link: '/', icon: <HomeIcon />, text: 'Home' },
      ],
    },
    {
      group: 'Components',
      items: [
        { id: 'componentsbutton', link: '/components', icon: <Puzzle />, text: 'Browse Components' },
        { id: 'findcomponentbutton', link: '/findcomponent', icon: <QrCode />, text: 'Find Component' },
      ],
    },
    {
      group: 'Designs',
      items: [
        { id: 'designsbutton', link: '/designs', icon: <Package />, text: 'Browse Designs' },
      ],
    },
    {
      group: 'Misc',
      items: [
        { id: 'creditsbutton', link: '/credits', icon: <Asterisk />, text: 'Credits' },
        { id: 'imprintbutton', link: '/imprint', icon: <BookText />, text: 'Imprint' },
      ],
    },
  ]

  return (
    <div className="flex h-full flex-col justify-items-center gap-4">
      <div className="flex grow">
        <Command className="rounded-lg" style={{ overflow: 'visible' }}>
          <CommandList style={{ overflow: 'visible' }}>
            <CommandGroup heading={menuList[0].group}>
              {menuList[0].items.map((option) => (
                <Link key={option.id} href={option.link}>
                  <CommandItem id={option.id} className="flex gap-2 cursor-pointer">
                    {option.icon}
                    {option.text}
                  </CommandItem>
                </Link>
              ))}
            </CommandGroup>

            <CommandGroup heading={menuList[1].group}>
              {menuList[1].items.map((option) => (
                <Link key={option.id} href={option.link}>
                  <CommandItem id={option.id} className="flex gap-2 cursor-pointer">
                    {option.icon}
                    {option.text}
                  </CommandItem>
                </Link>
              ))}
            </CommandGroup>

            <CommandGroup heading={menuList[2].group}>
              {menuList[2].items.map((option) => (
                <Link key={option.id} href={option.link}>
                  <CommandItem id={option.id} className="flex gap-2 cursor-pointer">
                    {option.icon}
                    {option.text}
                  </CommandItem>
                </Link>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </div>

      <div className="flex shrink-0">
        <Command className="rounded-lg" style={{ overflow: 'visible' }}>
          <CommandList style={{ overflow: 'visible' }}>
            <CommandGroup heading={menuList[3].group}>
              {menuList[3].items.map((option) => (
                <Link key={option.id} href={option.link}>
                  <CommandItem id={option.id} className="flex gap-2 cursor-pointer">
                    {option.icon}
                    {option.text}
                  </CommandItem>
                </Link>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </div>
    </div>
  )
}
