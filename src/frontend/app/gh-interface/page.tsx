import { readdir } from 'node:fs/promises'
import path from 'node:path'

import { isGhInterfaceDeactivated } from '@/lib/gh-interface'
import GHInterfacePageClient from './GHInterfacePageClient'

export const dynamic = 'force-dynamic'

/** The screenshots in public/gh-interface: new ones show up without a code change. */
async function screenshotFiles(): Promise<string[]> {
  try {
    const names = await readdir(path.join(process.cwd(), 'public', 'gh-interface'))
    return names.filter((name) => /\.(jpe?g|png|webp)$/i.test(name))
  } catch {
    return []
  }
}

export default async function GHInterfacePage() {
  return (
    <GHInterfacePageClient
      ghInterfaceDeactivated={isGhInterfaceDeactivated()}
      screenshots={await screenshotFiles()}
    />
  )
}
