'use client'

/**
 * The actions of the component page (decision 8.118, Q1): Reserve / Release as
 * a visible button, everything else in one Actions menu --- a dropdown on
 * desktop, a bottom sheet on a phone --- grouped Record / Moderate. The caller
 * sees the entries their roles allow (`availableActions`); the backend checks
 * again. A visitor of a public piece gets the passport editions only.
 */
import { useMemo, useState, type ComponentType } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { toast } from 'sonner'
import {
  Archive,
  ArchiveRestore,
  ChevronDown,
  CircleSlash,
  Download,
  FileDown,
  FilePen,
  FilePlus2,
  Layers,
  LogIn,
  LogOut,
  MapPin,
  Pencil,
  Scissors,
  Star,
  Undo2,
  Wrench,
} from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ExitDialog, ReenterDialog, undoExit } from '@/components/lineage/CirculationActions'
import { DeinstallDialog, undoDeinstall } from '@/components/lineage/DeinstallActions'
import { WithdrawComponentDialog, reinstateComponent } from '@/components/moderation/IdentityModerationActions'
import SnapshotLifecycleActions, { type SnapshotAction } from '@/components/moderation/SnapshotLifecycleActions'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { backendJson } from '@/lib/backend'
import {
  availableActions,
  formatDay,
  versionOffers,
  type ActionKey,
  type VersionMode,
  type VersionRow,
} from '@/lib/componentDetail'
import { downloadExport, isCeroMaterial, passportExports } from '@/lib/exports'
import { useMe } from '@/lib/me'
import { buildGeometryDownloadItems } from '@/lib/snapshotGeometryDownloads'
import ComponentSnapshotGeometryDownload from '../ComponentSnapshotGeometryDownload'
import { type ExtendedUser } from '../componentDetailShared'

type Icon = ComponentType<{ className?: string }>

// RESERVE -----------------------------------------------------------------------
/** Reserve for your project, or release; visible next to the Actions menu. */
export function ReserveButton({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const identityId = String(identity._id ?? '')
  const router = useRouter()
  const { data: session } = useSession()
  const { moderates } = useMe()
  const [busy, setBusy] = useState(false)
  const reservedBy = typeof identity.reserved === 'string' ? identity.reserved : ''
  const reserved = identity.is_reserved === true || !!reservedBy
  const userId = (session?.user as ExtendedUser | undefined)?.id

  if (!session?.user || identity.exit || identity.withdrawn) return null

  const run = async (method: 'POST' | 'DELETE', done: string) => {
    setBusy(true)
    try {
      await backendJson(`/identities/${encodeURIComponent(identityId)}/reserve`, { method })
      toast.success(done)
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  if (!reserved) {
    return (
      <Button size="sm" className="h-8 text-xs" disabled={busy} title="Reserve for your project"
        onClick={() => void run('POST', 'Reserved for you')}>
        Reserve
      </Button>
    )
  }
  const canRelease = !!reservedBy && (userId === reservedBy || moderates(identity.dataset))
  return canRelease ? (
    <Button size="sm" variant="destructive" className="h-8 text-xs" disabled={busy}
      title={userId === reservedBy ? 'Release this component' : 'Release this reservation (moderator)'}
      onClick={() => void run('DELETE', 'Released')}>
      Release
    </Button>
  ) : (
    <Button size="sm" variant="destructive" className="h-8 text-xs" disabled title="Reserved by another user">
      Reserved
    </Button>
  )
}

// VERSIONS ----------------------------------------------------------------------
const VERSION_COPY: Record<VersionMode, { title: string; text: string; only?: SnapshotAction[] }> = {
  correct: {
    title: 'Correct a version',
    text: 'A correction replaces a published version; it goes through review like any new state.',
    only: ['correct'],
  },
  promote: {
    title: 'Make a version current',
    text: 'The current version is the one the catalog shows.',
    only: ['promote'],
  },
  'withdraw-version': {
    title: 'Withdraw a version',
    text: 'It leaves lists and the public view; dataset members keep the full record.',
    only: ['withdraw'],
  },
  'manage-versions': {
    title: 'Versions awaiting action',
    text: 'Submit, recall, publish, reject, reinstate or delete a version.',
  },
}

function VersionDialog({ mode, rows, identityId, dataset, caller, open, onOpenChange }: {
  mode: VersionMode
  rows: SnapshotSummaryItem[]
  identityId: string
  dataset: string | null | undefined
  caller: { isModerator: boolean; isContributor: boolean; meId?: string | null }
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const copy = VERSION_COPY[mode]
  // only the versions this caller can act on in this dialog
  const shown = rows.filter((row) => versionOffers(mode, {
    _id: row._id, version: row.version, status: row.status, is_current: row.is_current,
    superseded_by: row.superseded_by, added_by_user_id: row.added_by_user_id,
  }, caller))
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.text}</DialogDescription>
        </DialogHeader>
        {shown.length === 0 ? (
          <p className="text-sm text-muted-foreground">No version to choose.</p>
        ) : (
          <ul className="space-y-2">
            {shown.map((row) => (
              <li key={row._id} className="rounded-md border border-border bg-muted/20 p-2.5 text-sm">
                <p className="mb-1.5 flex flex-wrap items-baseline gap-x-2">
                  <span className="font-medium">v{row.version}</span>
                  <span className="text-xs text-muted-foreground">
                    {row.status}{row.is_current ? ', current' : ''}{row.superseded_by ? ', corrected' : ''}
                    {row.effective_from ? `, since ${formatDay(row.effective_from, row.effective_from_precision)}` : ''}
                  </span>
                </p>
                <SnapshotLifecycleActions
                  snapshot={row}
                  dataset={dataset}
                  identityId={identityId}
                  size="sm"
                  only={copy.only}
                  onChanged={() => onOpenChange(false)}
                />
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  )
}

// THE MENU ----------------------------------------------------------------------
type MenuItem = {
  key: ActionKey
  label: string
  icon: Icon
  href?: string
  onSelect?: () => void
  disabled?: boolean
  destructive?: boolean
}

type Dialogs = 'exit' | 'reenter' | 'deinstall' | 'withdraw-component' | 'geometry' | VersionMode | null

export default function ComponentActionsMenu({ catalog, snapshots }: {
  catalog: CatalogComponent
  snapshots: SnapshotSummaryItem[]
}) {
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const identityId = String(identity._id ?? '')
  const router = useRouter()
  const { data: session } = useSession()
  const { me, isAdmin, moderates, rolesIn } = useMe()
  const wide = useMediaQuery('(min-width: 640px)')
  const [dialog, setDialog] = useState<Dialogs>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

  const signedIn = !!session?.user
  const dataset = identity.dataset
  const items = useMemo(
    () => buildGeometryDownloadItems(String(snapshot._id ?? identity.current_snapshot_id ?? ''), snapshot),
    [snapshot, identity.current_snapshot_id],
  )
  const versions: VersionRow[] = snapshots.map((s) => ({
    _id: s._id, version: s.version, status: s.status, is_current: s.is_current,
    superseded_by: s.superseded_by, added_by_user_id: s.added_by_user_id,
  }))
  const caller = {
    isModerator: moderates(dataset),
    isContributor: isAdmin || rolesIn(dataset).includes('contributor'),
    meId: me?._id ?? null,
  }
  const actions = availableActions({
    identity,
    versions,
    signedIn,
    ...caller,
    hasGeometryFiles: items.length > 0,
    isCero: isCeroMaterial(identity.material),
  })

  const refresh = () => router.refresh()
  const exportsOf = passportExports(identityId, identity.catalog_number, identity.material)
  const download = (url: string, filename: string) => {
    downloadExport(url, filename).catch((err: unknown) =>
      toast.error(err instanceof Error ? err.message : 'Download failed'))
  }
  const enc = encodeURIComponent(identityId)
  const catalogue: Record<ActionKey, MenuItem> = {
    pdf: { key: 'pdf', label: 'Download passport (PDF)', icon: FileDown,
      onSelect: () => download(exportsOf.pdf, exportsOf.pdfFilename) },
    cero: { key: 'cero', label: 'Download CERO (Turtle)', icon: FileDown,
      onSelect: () => exportsOf.cero && download(exportsOf.cero, exportsOf.ceroFilename) },
    geometry: { key: 'geometry', label: 'Download geometry', icon: Download, onSelect: () => setDialog('geometry') },
    locate: { key: 'locate', label: 'Locate', icon: MapPin, href: `/scan?mode=locate&reference_id=${enc}` },
    cut: { key: 'cut', label: 'Cut a piece from it', icon: Scissors, href: `/add-component?mode=cut&parent=${enc}` },
    draw: { key: 'draw', label: 'Draw pieces', icon: Scissors, href: `/add-component?mode=cut&parent=${enc}` },
    state: { key: 'state', label: 'Record new state', icon: FilePlus2, href: `/components/${enc}/snapshot/new?mode=state` },
    edit: { key: 'edit', label: 'Edit details', icon: Pencil, href: `/components/${enc}/edit` },
    correct: { key: 'correct', label: 'Correct a version...', icon: FilePen, onSelect: () => setDialog('correct') },
    promote: { key: 'promote', label: 'Make a version current...', icon: Star, onSelect: () => setDialog('promote') },
    'withdraw-version': { key: 'withdraw-version', label: 'Withdraw a version...', icon: Archive,
      onSelect: () => setDialog('withdraw-version') },
    'manage-versions': { key: 'manage-versions', label: 'Versions awaiting action...', icon: Layers,
      onSelect: () => setDialog('manage-versions') },
    exit: { key: 'exit', label: 'Take out of circulation', icon: LogOut, onSelect: () => setDialog('exit') },
    'undo-exit': { key: 'undo-exit', label: 'Undo exit', icon: Undo2, onSelect: () => void undoExit(identityId, refresh) },
    'exit-set-by-pieces': { key: 'exit-set-by-pieces', label: 'Exit set by its pieces: withdraw them to undo',
      icon: CircleSlash, disabled: true },
    reenter: { key: 'reenter', label: 'Re-enter circulation', icon: LogIn, onSelect: () => setDialog('reenter') },
    deinstall: { key: 'deinstall', label: 'Record deinstallation', icon: Wrench, onSelect: () => setDialog('deinstall') },
    'undo-deinstall': { key: 'undo-deinstall', label: 'Undo deinstallation', icon: Undo2,
      onSelect: () => void undoDeinstall(identityId, refresh) },
    'withdraw-component': { key: 'withdraw-component', label: 'Withdraw component', icon: Archive,
      destructive: true, onSelect: () => setDialog('withdraw-component') },
    'reinstate-component': { key: 'reinstate-component', label: 'Reinstate component', icon: ArchiveRestore,
      onSelect: () => void reinstateComponent(identityId, refresh) },
  }
  const record = actions.record.map((key) => catalogue[key])
  const moderate = actions.moderate.map((key) => catalogue[key])
  if (record.length === 0 && moderate.length === 0) return null

  const trigger = (
    <Button type="button" variant="outline" size="sm" className="h-8 gap-1 text-xs" aria-haspopup="menu">
      Actions<ChevronDown className="h-3.5 w-3.5" />
    </Button>
  )

  const rowClass = 'flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-sm hover:bg-accent disabled:opacity-50'
  const renderSheetItem = (item: MenuItem) => {
    const Icon = item.icon
    const body = (
      <>
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className={item.destructive ? 'text-destructive' : undefined}>{item.label}</span>
      </>
    )
    return item.href ? (
      <Link key={item.key} href={item.href} className={rowClass} onClick={() => setSheetOpen(false)}>{body}</Link>
    ) : (
      <button key={item.key} type="button" className={rowClass} disabled={item.disabled}
        onClick={() => { setSheetOpen(false); item.onSelect?.() }}>
        {body}
      </button>
    )
  }

  const renderMenuItem = (item: MenuItem) => {
    const Icon = item.icon
    const body = (
      <>
        <Icon className="h-4 w-4" />
        <span className={item.destructive ? 'text-destructive' : undefined}>{item.label}</span>
      </>
    )
    return item.href ? (
      <DropdownMenuItem key={item.key} asChild><Link href={item.href}>{body}</Link></DropdownMenuItem>
    ) : (
      <DropdownMenuItem key={item.key} disabled={item.disabled} onSelect={() => item.onSelect?.()}>{body}</DropdownMenuItem>
    )
  }

  return (
    <>
      {wide ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            {record.length > 0 && (
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-xs text-muted-foreground">Record</DropdownMenuLabel>
                {record.map(renderMenuItem)}
              </DropdownMenuGroup>
            )}
            {record.length > 0 && moderate.length > 0 && <DropdownMenuSeparator />}
            {moderate.length > 0 && (
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-xs text-muted-foreground">Moderate</DropdownMenuLabel>
                {moderate.map(renderMenuItem)}
              </DropdownMenuGroup>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <>
          <span onClick={() => setSheetOpen(true)}>{trigger}</span>
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetContent side="bottom" className="max-h-[85dvh] overflow-y-auto rounded-t-xl pb-6">
              <SheetHeader className="pb-0">
                <SheetTitle>Actions</SheetTitle>
                <SheetDescription className="sr-only">What you can do with this component</SheetDescription>
              </SheetHeader>
              <div className="space-y-1 px-2">
                {record.length > 0 && (
                  <>
                    <p className="px-3 pt-1 text-xs font-medium text-muted-foreground">Record</p>
                    {record.map(renderSheetItem)}
                  </>
                )}
                {moderate.length > 0 && (
                  <>
                    <p className="px-3 pt-2 text-xs font-medium text-muted-foreground">Moderate</p>
                    {moderate.map(renderSheetItem)}
                  </>
                )}
              </div>
            </SheetContent>
          </Sheet>
        </>
      )}

      {dialog === 'geometry' && (
        <ComponentSnapshotGeometryDownload catalog={catalog} open onOpenChange={(open) => !open && setDialog(null)} />
      )}
      {dialog === 'exit' && (
        <ExitDialog identityId={identityId} inPlace={identity.origin?.planned === true} open
          onOpenChange={(open) => !open && setDialog(null)} />
      )}
      {dialog === 'reenter' && identity.exit && (
        <ReenterDialog identityId={identityId} exit={identity.exit} open
          onOpenChange={(open) => !open && setDialog(null)} />
      )}
      {dialog === 'deinstall' && (
        <DeinstallDialog identity={identity} open onOpenChange={(open) => !open && setDialog(null)} />
      )}
      {dialog === 'withdraw-component' && (
        <WithdrawComponentDialog identityId={identityId} open onOpenChange={(open) => !open && setDialog(null)} />
      )}
      {(dialog === 'correct' || dialog === 'promote' || dialog === 'withdraw-version'
        || dialog === 'manage-versions') && (
        <VersionDialog mode={dialog} rows={snapshots} identityId={identityId} dataset={dataset} caller={caller} open
          onOpenChange={(open) => !open && setDialog(null)} />
      )}
    </>
  )
}
