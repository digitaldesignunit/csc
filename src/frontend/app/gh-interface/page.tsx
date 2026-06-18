import { isGhInterfaceDeactivated } from '@/lib/gh-interface'
import GHInterfacePageClient from './GHInterfacePageClient'

export default function GHInterfacePage() {
  return (
    <GHInterfacePageClient ghInterfaceDeactivated={isGhInterfaceDeactivated()} />
  )
}
