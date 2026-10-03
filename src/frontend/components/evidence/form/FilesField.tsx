'use client'

/**
 * Files that belong to every record of a submission (a lab report for
 * several cores, a drawing for several pieces): chosen once, stored once
 * per record by the server (decision 7.3). Signed-in users download them
 * (8.13); the "?" carries the backend's notice about private persons.
 */
import { useRef, useState } from 'react'
import { FileText, Paperclip, X } from 'lucide-react'

import Help from '@/components/evidence/Help'
import { Button } from '@/components/ui/button'
import { ATTACHMENT_ACCEPT, MAX_ATTACHMENT_TEXT, fileProblem } from '@/lib/evidence/photos'

export default function FilesField({
  files,
  onChange,
  help,
  label = 'Files for all records',
}: {
  files: File[]
  onChange: (next: File[]) => void
  help: string
  label?: string
}) {
  const input = useRef<HTMLInputElement>(null)
  const [refused, setRefused] = useState<string[]>([])
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        <span className="text-xs font-medium">{label}</span>
        <Help text={help} label="Files" />
      </div>
      <input
        ref={input}
        type="file"
        multiple
        accept={ATTACHMENT_ACCEPT}
        className="sr-only"
        aria-label={label}
        onChange={(event) => {
          const picked = Array.from(event.target.files ?? [])
          setRefused(picked.map(fileProblem).filter((m): m is string => m !== null))
          const fine = picked.filter((file) => fileProblem(file) === null)
          if (fine.length) onChange([...files, ...fine])
          event.target.value = ''
        }}
      />
      <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => input.current?.click()}>
        <Paperclip className="mr-1 h-3.5 w-3.5" />Add a PDF or an image
      </Button>
      <p className="text-xs text-muted-foreground">Up to {MAX_ATTACHMENT_TEXT} per file.</p>
      {refused.length > 0 && (
        <ul role="alert" className="space-y-0.5">
          {refused.map((message) => <li key={message} className="text-xs text-destructive">{message}</li>)}
        </ul>
      )}
      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1 text-sm">
              <span className="flex min-w-0 items-center gap-1.5">
                <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{file.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{Math.max(1, Math.round(file.size / 1024))} kB</span>
              </span>
              <Button type="button" variant="ghost" size="icon" className="h-6 w-6"
                onClick={() => onChange(files.filter((_, i) => i !== index))} aria-label={`Remove ${file.name}`}>
                <X className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
