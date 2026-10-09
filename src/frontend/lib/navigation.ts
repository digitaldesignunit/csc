/**
 * The navigation shell's entries (decision 8.29): one list with the rules
 * for who sees what, so later phases only add entries (P3: moderators,
 * users and invitations, datasets; P4: materials; P7: add component, drafts).
 */
import type { LucideIcon } from 'lucide-react'
import {
  BookOpen,
  BriefcaseBusiness,
  ChartColumn,
  Database,
  Inbox,
  Layers,
  LayoutGrid,
  LogIn,
  PackagePlus,
  ScanQrCode,
  ScrollText,
  TriangleAlert,
  Users,
  Waypoints,
  Workflow,
} from 'lucide-react'

/** Who is looking: drives which entries show. */
export type NavViewer = {
  signedIn: boolean
  isAdmin: boolean
  /** Moderates at least one dataset (`GET /users/me`). */
  isModerator: boolean
  /** Holds the reviewer role in at least one dataset. */
  isReviewer: boolean
}

export type NavGroupId = 'catalog' | 'capture' | 'mywork' | 'moderation' | 'admin' | 'tools' | 'account'

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
  { id: 'account', label: 'Account' },
]

const signedIn = (v: NavViewer) => v.signedIn
const anyone = () => true

/**
 * The entries of the sidebar (decision 8.118 S3): every entry is a page, none
 * a filter or a mode. An anonymous visitor sees Browse, Map, Analytics (the
 * public tier), Grasshopper, API docs and Sign in.
 */
export const NAV_ENTRIES: NavEntry[] = [
  { id: 'browse', label: 'Browse', href: '/components', icon: LayoutGrid, group: 'catalog', visible: anyone },
  { id: 'map', label: 'Map', href: '/components/map', icon: Waypoints, group: 'catalog', visible: anyone },
  { id: 'analytics', label: 'Analytics', href: '/analytics', icon: ChartColumn, group: 'catalog', visible: anyone },
  { id: 'scan', label: 'Scan', href: '/scan', icon: ScanQrCode, group: 'capture', visible: signedIn },
  { id: 'add', label: 'Add component', href: '/add-component', icon: PackagePlus, group: 'capture', visible: signedIn },
  { id: 'mywork', label: 'My work', href: '/my-work', icon: BriefcaseBusiness, group: 'mywork', visible: signedIn },
  {
    // the inbox: snapshots, evidence and, for reviewers, verification
    id: 'queue',
    label: 'Queue',
    href: '/admin/validation',
    icon: Inbox,
    group: 'moderation',
    visible: (v) => v.isAdmin || v.isModerator || v.isReviewer,
  },
  {
    // moderators manage their datasets' members here; admin all datasets
    id: 'datasets',
    label: 'Datasets',
    href: '/admin/datasets',
    icon: Database,
    group: 'moderation',
    visible: (v) => v.isAdmin || v.isModerator,
  },
  { id: 'users', label: 'Users and invitations', href: '/admin/users', icon: Users, group: 'admin', visible: (v) => v.isAdmin },
  { id: 'materials', label: 'Materials', href: '/admin/materials', icon: Layers, group: 'admin', visible: (v) => v.isAdmin },
  { id: 'geometry', label: 'Geometry failures', href: '/admin/geometry', icon: TriangleAlert, group: 'admin', visible: (v) => v.isAdmin },
  { id: 'logs', label: 'Backend logs', href: '/admin/logs', icon: ScrollText, group: 'admin', visible: (v) => v.isAdmin },
  { id: 'gh', label: 'Grasshopper', href: '/gh-interface', icon: Workflow, group: 'tools', visible: anyone },
  {
    id: 'api-docs',
    label: 'API docs',
    href: 'https://api.2ndchances.build/docs#/',
    icon: BookOpen,
    group: 'tools',
    visible: anyone,
    external: true,
  },
  { id: 'signin', label: 'Sign in', href: '/auth/signin', icon: LogIn, group: 'account', visible: (v) => !v.signedIn },
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
  [/^\/$/, 'Home'],
  [/^\/credits$/, 'Credits'],
  [/^\/imprint$/, 'Imprint'],
  [/^\/components\/[^/]+\/edit$/, 'Component'],
  [/^\/components\/[^/]+\/evidence\/new$/, 'Add evidence'],
  [/^\/components\/[^/]+\/snapshot\/new$/, 'Component'],
  [/^\/components\/(?!map$)[^/]+$/, 'Component'],
  [/^\/auth\//, 'Account'],
  [/^\/add-component/, 'Add component'],
  [/^\/admin\/(validation|review)/, 'Moderation'],
  [/^\/(identify|locate-by-id|transmit-id)/, 'Scan'],
  [/^\/dashboard/, 'My work'],
  [/^\/settings/, 'Settings'],
]

/** The top bar's page title: the active entry, else a known page. */
export function pageTitle(pathname: string, search: URLSearchParams): string {
  for (const [pattern, title] of EXTRA_TITLES) {
    if (pattern.test(pathname)) return title
  }
  const entry = NAV_ENTRIES.find((e) => isEntryActive(e, pathname, search))
  return entry?.label ?? ''
}
