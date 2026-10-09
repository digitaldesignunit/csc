'use client'

/**
 * A collapsible sidebar after the shadcn/ui `Sidebar` primitive, trimmed to
 * what the CSC shell needs (decision 8.29): an expanded panel that collapses
 * to an icon rail, `Ctrl/Cmd+B`, the choice in a cookie the server reads,
 * the rail by default below 1024 px, a slide-in sheet below 768 px.
 *
 * The rail is pure CSS: the `rail:` variant (globals.css) applies when the
 * shell carries `data-sidebar-state="collapsed"`, or `"auto"` on a narrow
 * viewport --- so the first paint already has the right width.
 */
import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { PanelLeft } from 'lucide-react'

import { cn } from '@/lib/utils'
import { SIDEBAR_COOKIE, type SidebarChoice } from '@/lib/sidebarState'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

const SIDEBAR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
const RAIL_QUERY = '(width < 64rem)'
const SHEET_QUERY = '(width < 48rem)'

type SidebarContextValue = {
  choice: SidebarChoice
  /** The desktop sidebar currently shows the rail. */
  isRail: boolean
  sheetOpen: boolean
  setSheetOpen: (open: boolean) => void
  toggle: () => void
}

const SidebarContext = React.createContext<SidebarContextValue | null>(null)

/** Where a part renders: the desktop sidebar or the phone sheet. */
const SurfaceContext = React.createContext<'desktop' | 'sheet'>('desktop')

export function useSidebar() {
  const context = React.useContext(SidebarContext)
  if (!context) throw new Error('useSidebar must be used within a SidebarProvider.')
  return context
}

function useMedia(query: string): boolean {
  return React.useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

export function SidebarProvider({
  initialChoice = 'auto',
  className,
  children,
  ...props
}: React.ComponentProps<'div'> & { initialChoice?: SidebarChoice }) {
  const [choice, setChoice] = React.useState<SidebarChoice>(initialChoice)
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const narrow = useMedia(RAIL_QUERY)
  const isRail = choice === 'collapsed' || (choice === 'auto' && narrow)

  const toggle = React.useCallback(() => {
    if (window.matchMedia(SHEET_QUERY).matches) {
      setSheetOpen((open) => !open)
      return
    }
    const next: SidebarChoice = isRail ? 'expanded' : 'collapsed'
    setChoice(next)
    document.cookie = `${SIDEBAR_COOKIE}=${next}; path=/; max-age=${SIDEBAR_COOKIE_MAX_AGE}; samesite=lax`
  }, [isRail])

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'b' && (event.metaKey || event.ctrlKey)
          && !event.altKey && !event.shiftKey) {
        event.preventDefault()
        toggle()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  const value = React.useMemo(
    () => ({ choice, isRail, sheetOpen, setSheetOpen, toggle }),
    [choice, isRail, sheetOpen, toggle],
  )

  return (
    <SidebarContext.Provider value={value}>
      <TooltipProvider delayDuration={0}>
        <div
          data-slot="sidebar-shell"
          data-sidebar-state={choice}
          className={cn('flex min-h-svh w-full', className)}
          {...props}
        >
          {children}
        </div>
      </TooltipProvider>
    </SidebarContext.Provider>
  )
}

/** The desktop sidebar, and the same content in a sheet on phones. */
export function Sidebar({
  className,
  children,
  label = 'Navigation',
}: { className?: string; children: React.ReactNode; label?: string }) {
  const { sheetOpen, setSheetOpen } = useSidebar()
  return (
    <>
      <aside
        data-slot="sidebar"
        aria-label={label}
        className={cn(
          'sticky top-0 hidden h-svh w-60 shrink-0 flex-col border-r border-sidebar-border',
          'bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-linear',
          'md:flex rail:w-12',
          className,
        )}
      >
        {children}
      </aside>
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent
          side="left"
          className="w-72 gap-0 bg-sidebar p-0 text-sidebar-foreground"
        >
          <SheetTitle className="sr-only">{label}</SheetTitle>
          <SheetDescription className="sr-only">Site navigation</SheetDescription>
          <SurfaceContext.Provider value="sheet">
            <div className="flex h-full flex-col">{children}</div>
          </SurfaceContext.Provider>
        </SheetContent>
      </Sheet>
    </>
  )
}

/** True where the rail is showing (the sheet never shows it). */
export function useIsRail(): boolean {
  const { isRail } = useSidebar()
  return React.useContext(SurfaceContext) === 'desktop' && isRail
}

/** Closes the phone sheet; call from navigation links. */
export function useCloseSheet() {
  const { setSheetOpen } = useSidebar()
  const surface = React.useContext(SurfaceContext)
  return React.useCallback(() => {
    if (surface === 'sheet') setSheetOpen(false)
  }, [surface, setSheetOpen])
}

export function SidebarTrigger({ className, ...props }: React.ComponentProps<'button'>) {
  const { toggle } = useSidebar()
  return (
    <button
      type="button"
      data-slot="sidebar-trigger"
      aria-label="Toggle sidebar"
      title="Toggle sidebar (Ctrl/Cmd+B)"
      onClick={toggle}
      className={cn(
        'inline-flex size-8 items-center justify-center rounded-md text-muted-foreground',
        'transition-colors hover:bg-accent hover:text-accent-foreground',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
        className,
      )}
      {...props}
    >
      <PanelLeft className="size-4" />
    </button>
  )
}

export function SidebarHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="sidebar-header" className={cn('flex flex-col gap-2 p-2', className)} {...props} />
}

export function SidebarFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="sidebar-footer" className={cn('flex flex-col gap-2 p-2', className)} {...props} />
}

export function SidebarContent({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="sidebar-content"
      className={cn('sidebar-scroll flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden', className)}
      {...props}
    />
  )
}

export function SidebarGroup({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="sidebar-group" className={cn('flex flex-col px-2 py-1', className)} {...props} />
}

export function SidebarGroupLabel({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="sidebar-group-label"
      className={cn(
        'flex h-7 shrink-0 items-center justify-between px-2 text-xs font-medium text-sidebar-foreground/60 rail:hidden',
        className,
      )}
      {...props}
    />
  )
}

export function SidebarSeparator({ className, ...props }: React.ComponentProps<'hr'>) {
  return <hr data-slot="sidebar-separator" className={cn('mx-2 border-sidebar-border', className)} {...props} />
}

export function SidebarMenu({ className, ...props }: React.ComponentProps<'ul'>) {
  return <ul data-slot="sidebar-menu" className={cn('flex flex-col gap-0.5', className)} {...props} />
}

export function SidebarMenuItem({ className, ...props }: React.ComponentProps<'li'>) {
  return <li data-slot="sidebar-menu-item" className={cn('group/menu-item relative', className)} {...props} />
}

export function SidebarMenuButton({
  asChild = false,
  isActive = false,
  tooltip,
  className,
  ...props
}: React.ComponentProps<'button'> & {
  asChild?: boolean
  isActive?: boolean
  tooltip?: string
}) {
  const isRail = useIsRail()
  const Comp = asChild ? Slot : 'button'
  const button = (
    <Comp
      data-slot="sidebar-menu-button"
      data-active={isActive}
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'flex h-8 w-full items-center gap-2 overflow-hidden rounded-md px-2 text-left text-sm outline-none',
        'transition-[width,height,padding] hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
        'focus-visible:ring-2 focus-visible:ring-sidebar-ring',
        'data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground',
        '[&>svg]:size-4 [&>svg]:shrink-0 [&>span]:truncate',
        'rail:size-8 rail:justify-center rail:p-0 rail:[&>span]:hidden rail:[&>.sidebar-extra]:hidden',
        className,
      )}
      {...props}
    />
  )
  if (!tooltip) return button
  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right" align="center" hidden={!isRail}>
        {tooltip}
      </TooltipContent>
    </Tooltip>
  )
}

/** A small action on the right of a menu row (hidden on the rail). */
export function SidebarMenuAction({ className, ...props }: React.ComponentProps<'button'>) {
  return (
    <button
      type="button"
      data-slot="sidebar-menu-action"
      className={cn(
        'absolute top-1 right-1 flex size-6 items-center justify-center rounded-md text-sidebar-foreground/60',
        'opacity-0 transition-opacity group-hover/menu-item:opacity-100 focus-visible:opacity-100',
        'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none',
        '[&>svg]:size-3.5 rail:hidden',
        className,
      )}
      {...props}
    />
  )
}

/** The page next to the sidebar. */
export function SidebarInset({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="sidebar-inset" className={cn('flex min-w-0 flex-1 flex-col', className)} {...props} />
}
