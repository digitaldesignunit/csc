/**
 * The navigation shell's entries (decision 8.29): one list with the rules
 * for who sees what, so later phases only add entries (P3: moderators,
 * users and invitations, datasets; P7: add component, drafts).
 */
import type { LucideIcon } from 'lucide-react'
import {
  Archive,
  BookOpen,
  Bookmark,
  ChartColumn,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
  ScanQrCode,
  ScrollText,
  Send,
  Users,
  Waypoints,
  Workflow,
} from 'lucide-react'

/** Who is looking: drives which entries show. */
export type NavViewer = {
  signedIn: boolean
  isAdmin: boolean
  /** Moderates at least one dataset; known from P3 on (false until then). */
  isModerator: boolean
}

export type NavGroupId = 'catalog' | 'capture' | 'mywork' | 'moderation' | 'admin' | 'tools'

export type NavEntry = {
  id: string
  label: string
  href: string
  icon: LucideIcon
  group: NavGroupId
  visible: (viewer: NavViewer) => boolean
  /** Opens in a new tab (marked with an "external" arrow). */
  external?: boolean
  /** Active for this exact query, e.g. `circulation=exited`. */
  query?: Record<string, string>
}

export const NAV_GROUPS: { id: NavGroupId; label: string }[] = [
  { id: 'catalog', label: 'Catalog' },
  { id: 'capture', label: 'Capture' },
  { id: 'mywork', label: 'My work' },
  { id: 'moderation', label: 'Moderation' },
  { id: 'admin', label: 'Admin' },
  { id: 'tools', label: 'Tools' },
]

const signedIn = (v: NavViewer) => v.signedIn
const anyone = () => true

export const NAV_ENTRIES: NavEntry[] = [
  { id: 'browse', label: 'Browse', href: '/components', icon: LayoutGrid, group: 'catalog', visible: signedIn },
  { id: 'map', label: 'Map', href: '/components/map', icon: Waypoints, group: 'catalog', visible: signedIn },
  {
    id: 'exited',
    label: 'Out of circulation',
    href: '/components?circulation=exited',
    query: { circulation: 'exited' },
    icon: Archive,
    group: 'catalog',
    visible: signedIn,
  },
  { id: 'analytics', label: 'Analytics', href: '/analytics', icon: ChartColumn, group: 'catalog', visible: signedIn },
  { id: 'identify', label: 'Scan & Identify', href: '/identify', icon: ScanQrCode, group: 'capture', visible: signedIn },
  { id: 'transmit', label: 'Transmit ID', href: '/transmit-id', icon: Send, group: 'capture', visible: signedIn },
  { id: 'dashboard', label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, group: 'mywork', visible: signedIn },
  { id: 'reserved', label: 'Reserved', href: '/dashboard/reserved', icon: Bookmark, group: 'mywork', visible: signedIn },
  {
    id: 'queue',
    label: 'Moderation queue',
    href: '/admin/validation',
    icon: Inbox,
    group: 'moderation',
    visible: (v) => v.isAdmin || v.isModerator,
  },
  { id: 'users', label: 'Users', href: '/admin/users', icon: Users, group: 'admin', visible: (v) => v.isAdmin },
  { id: 'logs', label: 'Backend logs', href: '/admin/logs', icon: ScrollText, group: 'admin', visible: (v) => v.isAdmin },
  { id: 'gh', label: 'GH Interface', href: '/gh-interface', icon: Workflow, group: 'tools', visible: signedIn },
  {
    id: 'api-docs',
    label: 'API docs',
    href: 'https://api.2ndchances.build/docs#/',
    icon: BookOpen,
    group: 'tools',
    visible: anyone,
    external: true,
  },
]

/** The groups with their visible entries, empty groups dropped. */
export function visibleNav(viewer: NavViewer) {
  return NAV_GROUPS
    .map((group) => ({
      ...group,
      entries: NAV_ENTRIES.filter((e) => e.group === group.id && e.visible(viewer)),
    }))
    .filter((group) => group.entries.length > 0)
}

/**
 * Whether an entry is the current page. Entries with a `query` need it;
 * an entry without one does not match while another entry's query holds
 * (Browse is not active on "Out of circulation").
 */
export function isEntryActive(
  entry: NavEntry,
  pathname: string,
  search: URLSearchParams,
): boolean {
  if (entry.external) return false
  const path = entry.href.split('?')[0]
  const pathMatches = path === '/'
    ? pathname === '/'
    : pathname === path || pathname.startsWith(`${path}/`)
  if (!pathMatches) return false
  if (entry.query) {
    return Object.entries(entry.query).every(([k, v]) => search.get(k) === v)
  }
  // a longer or query-specific sibling wins
  return !NAV_ENTRIES.some((other) => {
    if (other === entry || other.external) return false
    const otherPath = other.href.split('?')[0]
    if (otherPath === path) {
      return !!other.query
        && Object.entries(other.query).every(([k, v]) => search.get(k) === v)
    }
    return otherPath.startsWith(`${path}/`)
      && (pathname === otherPath || pathname.startsWith(`${otherPath}/`))
  })
}

const EXTRA_TITLES: [RegExp, string][] = [
  [/^\/$/, 'About'],
  [/^\/credits$/, 'Credits'],
  [/^\/imprint$/, 'Imprint'],
  [/^\/components\/[^/]+\/edit$/, 'Component'],
  [/^\/components\/(?!map$)[^/]+$/, 'Component'],
  [/^\/auth\//, 'Account'],
  [/^\/add-component/, 'Add component'],
]

/** The top bar's page title: the active entry, else a known page. */
export function pageTitle(pathname: string, search: URLSearchParams): string {
  for (const [pattern, title] of EXTRA_TITLES) {
    if (pattern.test(pathname)) return title
  }
  const entry = NAV_ENTRIES.find((e) => isEntryActive(e, pathname, search))
  return entry?.label ?? ''
}
