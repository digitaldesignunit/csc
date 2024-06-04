'use client'

import { HomeIcon, QrCode, Package, Puzzle, BookMarked, Asterisk, BookText } from 'lucide-react'
import { Command, CommandGroup, CommandItem, CommandList } from './ui/command'
import Link from 'next/link'

export default function AppMenu() {

  const menuList = [
    {
      group: 'General',
      items: [
        {
          id: 'homebutton',
          link: '/',
          icon: <HomeIcon />,
          text: 'Home'
        },
      ]
      },
      {
        group: 'Components',
        items: [
          {
            id: 'componentsbutton',
            link: '/components',
            icon: <Puzzle />,
            text: 'Components'
          },
          {
            id: 'findcomponentbutton',
            link: '/findcomponent',
            icon: <QrCode />,
            text: 'Find Component'
          },
        ]
      },
      {
        group: 'Models',
        items: [
          {
            id: 'modelsbutton',
            link: '/',
            icon: <Package />,
            text: 'Models'
          },
        ]
      },
      {
        group: 'Misc',
        items: [
          // {
          //   id: 'settingsbutton',
          //   link: '/settings',
          //   icon: <Settings />,
          //   text: 'Settings'
          // },
          {
            id: 'creditsbutton',
            link: '/credits',
            icon: <Asterisk />,
            text: 'Credits'
          },
          {
            id: 'imprintbutton',
            link: '/',
            icon: <BookText />,
            text: 'Imprint'
          },
        ]
      }
    ]

  return (
    <>
    <div className='flex flex-col h-full justify-items-center'>
      <div className='flex grow'>
          <Command style={{ overflow: 'visible' }} className='rounded-lg'>
            <CommandList style={{ overflow: 'visible' }}>

                <CommandGroup heading={menuList[0].group}>
                  {menuList[0].items.map((option: any, optionKey: number) => 
                    <Link key={optionKey} href={option.link}>
                      <CommandItem id={option.id} key={optionKey} className='flex gap-2 cursor-pointer'>
                        {option.icon}
                        {option.text}
                      </CommandItem>
                    </Link>
                  )}
                </CommandGroup>

                <CommandGroup heading={menuList[1].group}>
                  {menuList[1].items.map((option: any, optionKey: number) => 
                    <Link key={optionKey} href={option.link}>
                      <CommandItem id={option.id} key={optionKey} className='flex gap-2 cursor-pointer'>
                        {option.icon}
                        {option.text}
                      </CommandItem>
                    </Link>
                  )}
                </CommandGroup>

                <CommandGroup heading={menuList[2].group}>
                  {menuList[2].items.map((option: any, optionKey: number) => 
                    <Link key={optionKey} href={option.link}>
                      <CommandItem id={option.id} key={optionKey} className='flex gap-2 cursor-pointer'>
                        {option.icon}
                        {option.text}
                      </CommandItem>
                    </Link>
                  )}
                </CommandGroup>

            </CommandList>
          </Command>
        </div>

        <div className='flex shrink-0'>
          <Command style={{ overflow: 'visible' }} className='rounded-lg'>
            <CommandList style={{ overflow: 'visible' }}>

                <CommandGroup heading={menuList[3].group}>
                  {menuList[3].items.map((option: any, optionKey: number) => 
                    <Link key={optionKey} href={option.link}>
                      <CommandItem id={option.id} key={optionKey} className='flex gap-2'>
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
      </>
  )
}