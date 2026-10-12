'use client'

/**
 * The last step of the form (decision 8.134 e): what saving will do ("6 test
 * areas as drafts on #709 ..., version 3, 2 files"), what is still missing or
 * wrong per section with a jump link to the field, and the save button.
 */
import { AlertTriangle, CheckCircle2, Loader2, Save } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { SECTION_ORDER, issuesOf, type Issue, type SectionId } from '@/lib/evidence/issues'

export default function CheckSection({
  summary,
  notices,
  issues,
  titles,
  onJump,
  onSave,
  saving,
  saveLabel,
}: {
  summary: string
  /** things to know before saving (a verification that resets) */
  notices: React.ReactNode[]
  issues: Issue[]
  titles: Record<SectionId, string>
  onJump: (issue: Issue) => void
  onSave: () => void
  saving: boolean
  saveLabel: string
}) {
  const groups = SECTION_ORDER
    .map((section) => ({ section, rows: issuesOf(issues, section) }))
    .filter((group) => group.rows.length > 0)
  return (
    <div className="space-y-4">
      <p className="text-sm font-medium">{summary}</p>
      {notices.map((notice, index) => (
        <div
          key={index}
          role="status"
          className="flex gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <div>{notice}</div>
        </div>
      ))}
      {groups.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300" role="status">
          <CheckCircle2 className="h-4 w-4" aria-hidden />Nothing is missing. The server checks the values when you save.
        </p>
      ) : (
        <div className="space-y-3" role="alert">
          <p className="text-sm text-muted-foreground">
            {issues.length} thing{issues.length === 1 ? '' : 's'} to look at before it can be saved:
          </p>
          {groups.map(({ section, rows }) => (
            <div key={section} className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{titles[section]}</p>
              <ul className="space-y-0.5">
                {rows.map((issue, index) => (
                  <li key={`${issue.message}-${index}`}>
                    <button
                      type="button"
                      onClick={() => onJump(issue)}
                      className={
                        issue.source === 'server'
                          ? 'text-left text-sm text-destructive underline-offset-2 hover:underline'
                          : 'text-left text-sm text-amber-800 underline-offset-2 hover:underline dark:text-amber-300'
                      }
                    >
                      {issue.message}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <Button onClick={onSave} disabled={saving}>
        {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
        {saveLabel}
      </Button>
    </div>
  )
}
