'use client'

/**
 * The CSC navigation shell's sidebar (decision 8.29): brand at the top, the
 * entries of `lib/navigation.ts` in their groups, Recent, and the account
 * menu at the bottom.
 */
import { Fragment, useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { signIn, signOut, useSession } from 'next-auth/react'
import { useTheme } from 'next-themes'
import {
  ArrowUpRight,
  Award,
  ChevronsUpDown,
  CircleUser,
  FileText,
  History,
  Info,
  LayoutDashboard,
  LogIn,
  LogOut,
  RotateCw,
  SunMoon,
  UserPlus,
  X,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useCloseSheet,
  useIsRail,
} from '@/components/ui/sidebar'
import { isEntryActive, visibleNav, type NavViewer } from '@/lib/navigation'
import { forgetRecentComponents, useRecentComponents, useRecentUserId } from '@/lib/recentComponents'
import { useMe } from '@/lib/me'
import { backendJson } from '@/lib/backend'
import { cn, resolveStatic } from '@/lib/utils'

type SessionUser = {
  id?: string | null
  name?: string | null
  email?: string | null
  username?: string | null
  role?: string | null
}

function initialsFrom(user: SessionUser): string {
  const name = user.name?.trim()
  if (name) {
    const parts = name.split(/\s+/).slice(0, 2)
    return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[1][0]).toUpperCase()
  }
  const source = user.username || user.email || ''
  return (source.includes('@') ? source.split('@')[0] : source).slice(0, 2).toUpperCase()
}

function Brand({ betaBannerText }: { betaBannerText?: string }) {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  const close = useCloseSheet()
  useEffect(() => setMounted(true), [])
  const logo = resolveStatic(
    mounted && resolvedTheme === 'dark' ? '/logo/ddu_logo_white.png' : '/logo/ddu_logo_black.png',
  )
  return (
    <Link
      href="/"
      onClick={close}
      className="flex flex-col items-start gap-1.5 rounded-md p-1 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring rail:items-center rail:py-2 rail:px-0"
      aria-label="Catalog of Second Chances: About"
    >
      {/* the logo is 500 x 159 px: fixed height (width on the rail), the
          other side follows, so it is never stretched */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={logo}
        alt=""
        width={500}
        height={159}
        className={cn(
          'h-6 w-auto shrink-0 object-contain rail:h-auto rail:w-8',
          !mounted && 'opacity-0',
        )}
      />
      <span className="flex min-w-0 flex-col rail:hidden">
        <span className="truncate text-sm font-semibold leading-tight">
          Catalog of Second Chances
        </span>
        {betaBannerText ? (
          <Badge className="mt-0.5 w-fit border-amber-600 bg-amber-500 px-1.5 py-0 text-[10px] font-bold text-amber-950 dark:border-amber-300 dark:bg-amber-400">
            {betaBannerText}
          </Badge>
        ) : null}
      </span>
    </Link>
  )
}

/** Pending snapshots and evidence in the caller's moderated datasets (the queue badge). */
function usePendingCount(enabled: boolean): number {
  const pathname = usePathname()
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!enabled) {
      setCount(0)
      return
    }
    let cancelled = false
    const load = () => {
      // pending snapshots and pending evidence of the moderated datasets
      Promise.all([
        backendJson<unknown[]>('/snapshots/pending').catch(() => []),
        backendJson<unknown[]>('/evidence/pending').catch(() => []),
      ]).then(([snapshots, evidence]) => {
        if (cancelled) return
        const count = (rows: unknown) => (Array.isArray(rows) ? rows.length : 0)
        setCount(count(snapshots) + count(evidence))
      })
    }
    load()
    const timer = window.setInterval(load, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [enabled, pathname])
  return count
}

function NavGroups({ viewer }: { viewer: NavViewer }) {
  const pathname = usePathname() ?? '/'
  const search = useSearchParams() ?? new URLSearchParams()
  const close = useCloseSheet()
  const groups = visibleNav(viewer)
  const pending = usePendingCount(viewer.isAdmin || viewer.isModerator)
  return (
    <>
      {groups.map((group, index) => (
        <Fragment key={group.id}>
          {index > 0 && <SidebarSeparator className="my-1 hidden rail:block" />}
          <SidebarGroup>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarMenu>
              {group.entries.map((entry) => {
                const Icon = entry.icon
                const active = isEntryActive(entry, pathname, search)
                return (
                  <SidebarMenuItem key={entry.id}>
                    <SidebarMenuButton asChild isActive={active} tooltip={entry.label}>
                      {entry.external ? (
                        <a href={entry.href} target="_blank" rel="noopener noreferrer">
                          <Icon />
                          <span>{entry.label}</span>
                          <ArrowUpRight className="sidebar-extra ml-auto !size-3 opacity-60" aria-label="opens in a new tab" />
                        </a>
                      ) : (
                        <Link href={entry.href} onClick={close}>
                          <Icon />
                          <span>{entry.label}</span>
                          {entry.id === 'queue' && pending > 0 ? (
                            <span
                              className="sidebar-extra ml-auto rounded-full bg-sidebar-primary px-1.5 text-[10px] font-semibold leading-4 text-sidebar-primary-foreground"
                              aria-label={`${pending} pending`}
                            >
                              {pending}
                            </span>
                          ) : null}
                        </Link>
                      )}
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroup>
        </Fragment>
      ))}
    </>
  )
}

function Recent() {
  const { items, remove, clear } = useRecentComponents(useRecentUserId())
  const close = useCloseSheet()
  const isRail = useIsRail()
  const pathname = usePathname() ?? '/'
  if (isRail || items.length === 0) return null
  return (
    <SidebarGroup className="rail:hidden">
      <SidebarGroupLabel>
        <span className="flex items-center gap-1.5">
          <History className="size-3.5" />
          Recent
        </span>
        <button
          type="button"
          onClick={clear}
          className="rounded px-1 text-[11px] font-normal text-sidebar-foreground/60 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none"
        >
          Clear
        </button>
      </SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => {
          const href = `/components/${encodeURIComponent(item.id)}`
          return (
            <SidebarMenuItem key={item.id}>
              <SidebarMenuButton asChild isActive={pathname === href} className="pr-7 font-normal">
                <Link href={href} onClick={close}>
                  <span>{item.label}</span>
                </Link>
              </SidebarMenuButton>
              <SidebarMenuAction
                aria-label={`Remove ${item.label} from Recent`}
                onClick={() => remove(item.id)}
              >
                <X />
              </SidebarMenuAction>
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}

function AccountMenu() {
  const { data: session, status } = useSession()
  const { theme, setTheme } = useTheme()
  const close = useCloseSheet()
  const isRail = useIsRail()
  const user = (session?.user ?? null) as SessionUser | null
  const expired = Boolean(
    (session as { error?: string } | null)?.error === 'ApiTokenExpired'
    || (session as { api?: { hasAccessToken?: boolean } } | null)?.api?.hasAccessToken === false,
  )

  const avatar = user ? (
    <span
      aria-hidden
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-bold',
        expired ? 'bg-destructive text-destructive-foreground' : 'bg-sidebar-primary text-sidebar-primary-foreground',
      )}
    >
      {initialsFrom(user)}
    </span>
  ) : (
    <CircleUser className="!size-8 shrink-0 p-1 text-sidebar-foreground/70" aria-hidden />
  )

  const primary = user ? (user.name || user.username || user.email || '') : 'Sign in'
  const secondary = user
    ? (expired ? 'Session expired' : (user.username || user.email || ''))
    : 'or register'

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <Tooltip>
          <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              className="h-12 rail:size-8"
              disabled={status === 'loading'}
            >
              {avatar}
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate font-medium">{primary}</span>
                <span className={cn('truncate text-xs', expired ? 'text-destructive' : 'text-sidebar-foreground/60')}>
                  {secondary}
                </span>
              </span>
              <ChevronsUpDown className="sidebar-extra ml-auto !size-4 opacity-60" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="right" align="center" hidden={!isRail}>
            {user ? `Account: ${primary}` : 'Sign in'}
          </TooltipContent>
          </Tooltip>
          <DropdownMenuContent side="top" align="start" className="w-60">
            {user ? (
              <>
                <DropdownMenuLabel className="font-normal">
                  <p className="truncate text-sm font-medium">{primary}</p>
                  <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {expired && (
                  <DropdownMenuItem onSelect={() => signIn()} className="text-destructive">
                    <RotateCw /> Re-authenticate
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem asChild>
                  <Link href="/dashboard" onClick={close}><LayoutDashboard /> Dashboard</Link>
                </DropdownMenuItem>
              </>
            ) : (
              <>
                <DropdownMenuItem onSelect={() => signIn()}>
                  <LogIn /> Sign in
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/auth/register" onClick={close}><UserPlus /> Register</Link>
                </DropdownMenuItem>
              </>
            )}
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <SunMoon className="mr-2 size-4 text-muted-foreground" /> Theme
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuRadioGroup value={theme ?? 'system'} onValueChange={setTheme}>
                  <DropdownMenuRadioItem value="light">Light</DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="dark">Dark</DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="system">System</DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/" onClick={close}><Info /> About</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/credits" onClick={close}><Award /> Credits</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/imprint" onClick={close}><FileText /> Imprint</Link>
            </DropdownMenuItem>
            {user && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => {
                    forgetRecentComponents(user.id)
                    void signOut()
                  }}
                >
                  <LogOut /> Sign out
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

export default function AppSidebar({ betaBannerText }: { betaBannerText?: string }) {
  const { data: session } = useSession()
  const { moderatesAny, reviewsAny } = useMe()
  const signedIn = Boolean(session?.user) && !(session as { error?: string } | null)?.error
  const isAdmin = signedIn && (session?.user as SessionUser | undefined)?.role === 'admin'
  const viewer: NavViewer = {
    signedIn,
    isAdmin,
    isModerator: signedIn && moderatesAny,
    isReviewer: signedIn && reviewsAny,
  }
  return (
    <Sidebar>
      <SidebarHeader className="pb-1">
        <Brand betaBannerText={betaBannerText} />
      </SidebarHeader>
      <SidebarContent>
        <NavGroups viewer={viewer} />
        <Recent />
      </SidebarContent>
      <SidebarFooter className="border-t border-sidebar-border">
        <AccountMenu />
      </SidebarFooter>
    </Sidebar>
  )
}
