'use client'

/**
 * The files of one evidence record (spec 3.3.4, decisions 7.3, 8.13):
 * list, download (signed-in users only), add, remove. Before publish the
 * author removes; after publish only moderator(D) removes, with a reason
 * (`gdpr` also blanks the file name), and the entry stays as a tombstone.
 * Names are rendered as text, never as markup; downloads go through the
 * backend route only.
 */
import { useRef, useState } from 'react'
import { useSession } from 'next-auth/react'
import { Download, FileText, Loader2, Paperclip, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import ReasonDialog from '@/components/moderation/ReasonDialog'
import { Button } from '@/components/ui/button'
import type { EvidenceView } from '@/generated'
import { BackendError } from '@/lib/backend'
import { attachmentUrl, removeAttachment, uploadAttachment, type AttachmentEntry } from '@/lib/evidence/api'
import { ATTACHMENT_ACCEPT, MAX_ATTACHMENT_TEXT, fileProblem, prepareUpload } from '@/lib/evidence/photos'
import { useMe } from '@/lib/me'
import { formatDay } from '@/lib/utils'

function sizeText(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1000))} kB`
}

export default function EvidenceAttachments({
  record,
  dataset,
  onChanged,
  uploadHelp,
}: {
  record: EvidenceView
  dataset: string | null | undefined
  onChanged: () => void
  uploadHelp?: string
}) {
  const { data: session } = useSession()
  const { me, moderates, rolesIn } = useMe()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<AttachmentEntry | null>(null)

  const signedIn = Boolean(session?.user)
  const entries = (record.attachments ?? []) as AttachmentEntry[]
  const isAuthor = !!me && record.recorded_by_user_id === me._id
  const isModerator = moderates(dataset)
  const published = record.status === 'published' || record.status === 'withdrawn'
  // as the routes decide (7.0): a draft: author or moderator; pending:
  // moderator; after publish contributor(D) adds, moderator(D) removes
  const canAdd = record.status !== 'withdrawn' && record.status !== 'rejected' && (
    record.status === 'draft' ? isAuthor || isModerator
      : record.status === 'pending' ? isModerator
        : rolesIn(dataset).includes('contributor')
  )
  const canRemove = published ? isModerator : isAuthor || isModerator

  const add = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const problem = Array.from(files).map(fileProblem).find((m) => m !== null)
    if (problem) {
      toast.error(problem)
      if (input.current) input.current.value = ''
      return
    }
    setBusy(true)
    try {
      for (const file of Array.from(files)) {
        await uploadAttachment(await prepareUpload(file), [record._id])
      }
      toast.success('File attached')
      onChanged()
    } catch (err) {
      toast.error(err instanceof BackendError ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  const live = entries.filter((e) => !e.removed)
  const gone = entries.filter((e) => e.removed)

  return (
    <div className="space-y-2">
      {entries.length === 0 && (
        <p className="text-xs text-muted-foreground">No files.</p>
      )}
      <ul className="space-y-1.5">
        {live.map((entry) => {
          const isImage = entry.media_type.startsWith('image/')
          return (
            <li key={entry.index} className="flex items-center gap-2 rounded-md border border-border p-1.5 text-sm">
              {isImage && signedIn ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={attachmentUrl(record._id, entry.index)}
                  alt={entry.name ? `Photo ${entry.name}` : `Photo ${entry.index}`}
                  loading="lazy"
                  className="h-12 w-12 shrink-0 rounded object-cover"
                />
              ) : (
                <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{entry.name || `File ${entry.index}`}</p>
                <p className="text-xs text-muted-foreground">
                  {entry.media_type}, {sizeText(entry.size)}
                  {entry.uploaded_at ? `, ${formatDay(entry.uploaded_at)}` : ''}
                  {' '}<span title={entry.sha256}>sha256 {entry.sha256.slice(0, 8)}</span>
                </p>
              </div>
              {signedIn ? (
                <Button asChild variant="ghost" size="icon" className="h-8 w-8">
                  <a href={attachmentUrl(record._id, entry.index)} download aria-label={`Download ${entry.name || entry.index}`}>
                    <Download className="h-4 w-4" />
                  </a>
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground">Sign in to download</span>
              )}
              {canRemove && (
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive"
                  onClick={() => setRemoving(entry)} aria-label={`Remove ${entry.name || entry.index}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </li>
          )
        })}
        {gone.map((entry) => (
          <li key={entry.index} className="rounded-md border border-dashed border-border px-2 py-1 text-xs text-muted-foreground">
            File {entry.index} removed{entry.removed?.at ? ` ${formatDay(entry.removed.at)}` : ''}
            {entry.removed?.reason ? `: ${entry.removed.reason}` : ''}
            {entry.sha256 ? ` (sha256 ${entry.sha256.slice(0, 8)})` : ''}
          </li>
        ))}
      </ul>
      {canAdd && (
        <div className="flex flex-wrap items-center gap-2">
          <input ref={input} type="file" multiple accept={ATTACHMENT_ACCEPT} className="sr-only"
            aria-label="Add files" onChange={(e) => void add(e.target.files)} />
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" disabled={busy}
            onClick={() => input.current?.click()}>
            {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Paperclip className="mr-1 h-3.5 w-3.5" />}
            Add a file (up to {MAX_ATTACHMENT_TEXT})
          </Button>
          {uploadHelp && <p className="text-xs text-muted-foreground">{uploadHelp}</p>}
        </div>
      )}
      <ReasonDialog
        open={removing !== null}
        onOpenChange={(open) => { if (!open) setRemoving(null) }}
        title={`Remove ${removing?.name || 'the file'}`}
        description={published
          ? 'The file is deleted and its entry stays as a tombstone with your reason. Use the reason gdpr when it shows a person: the file name is blanked too.'
          : 'The file is deleted; the entry stays marked as removed.'}
        confirmLabel="Remove"
        destructive
        onConfirm={async (reason) => {
          if (!removing) return
          await removeAttachment(record._id, removing.index, reason || undefined)
          toast.success('File removed')
          onChanged()
        }}
      />
    </div>
  )
}
