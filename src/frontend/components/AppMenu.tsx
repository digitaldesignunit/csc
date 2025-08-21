'use client'

import { HomeIcon, QrCode, Package, Puzzle, Asterisk, BookText } from 'lucide-react'
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
        <div className="w-full rounded-lg bg-popover text-popover-foreground border p-2 space-y-4" style={{ overflow: 'visible' }}>
          <div className="space-y-2">
            <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              {menuList[0].group}
            </div>
            <div className="space-y-1">
              {menuList[0].items.map((option) => (
                <Link key={option.id} href={option.link}>
                  <div className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer">
                    {option.icon}
                    {option.text}
                  </div>
                </Link>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              {menuList[1].group}
            </div>
            <div className="space-y-1">
              {menuList[1].items.map((option) => (
                <Link key={option.id} href={option.link}>
                  <div className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer">
                    {option.icon}
                    {option.text}
                  </div>
                </Link>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              {menuList[2].group}
            </div>
            <div className="space-y-1">
              {menuList[2].items.map((option) => (
                <Link key={option.id} href={option.link}>
                  <div className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer">
                    {option.icon}
                    {option.text}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="flex shrink-0">
        <div className="w-full rounded-lg bg-popover text-popover-foreground border p-2 space-y-2" style={{ overflow: 'visible' }}>
          <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
            {menuList[3].group}
          </div>
          <div className="space-y-1">
            {menuList[3].items.map((option) => (
              <Link key={option.id} href={option.link}>
                <div className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer">
                  {option.icon}
                  {option.text}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
