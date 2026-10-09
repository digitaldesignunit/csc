/**
 * What the invitation and member routes say about the mail (decision 8.124
 * b), as texts the pages show. A failed mail never undoes the invitation or
 * the membership; the registration link is never shown to the inviter (a code
 * sign-up counts as verified at once), so the remedy for a failure is Resend,
 * which mails a new code. Pure, so the unit test covers it.
 */
import type { InviteResult, MemberByEmailResult } from '@/generated/AccessModels'

export type InviteSummary = {
  sent: string[]
  failed: string[]
  existing: string[]
  /** One line for the toast. */
  toast: string
  /** The toast is a warning when any mail failed. */
  warning: boolean
}

export function summariseInvitations(results: InviteResult[]): InviteSummary {
  const sent = results.filter((r) => r.result === 'invited').map((r) => r.email)
  const failed = results.filter((r) => r.result === 'mail_failed').map((r) => r.email)
  const existing = results.filter((r) => r.result === 'exists').map((r) => r.email)
  const count = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`
  const parts = [`${count(sent.length, 'invitation')} sent`]
  if (failed.length) parts.push(`${count(failed.length, 'mail')} could not be sent: use Resend`)
  return { sent, failed, existing, toast: parts.join('; '), warning: failed.length > 0 }
}

export type MemberNotice = { text: string; warning: boolean }

/** The toast after "Add a person" in the member editor. */
export function memberNotice(result: Pick<MemberByEmailResult, 'email' | 'result' | 'mail_failed'>): MemberNotice {
  if (result.result === 'added') {
    return result.mail_failed
      ? { text: `${result.email} added; the notice mail could not be sent (the membership stands)`, warning: true }
      : { text: `${result.email} added and notified`, warning: false }
  }
  return result.mail_failed
    ? {
      text: `No account for ${result.email}: the invitation exists but its mail could not be sent. Use Resend in the invitations list`,
      warning: true,
    }
    : { text: `No account for ${result.email}: invitation sent`, warning: false }
}

/** The toast after Resend. */
export function resendNotice(result: Pick<InviteResult, 'email' | 'result'>): MemberNotice {
  return result.result === 'mail_failed'
    ? { text: `The mail to ${result.email} could not be sent again; the previous link no longer works. Try Resend again`, warning: true }
    : { text: `A new invitation went to ${result.email}; the old link no longer works`, warning: false }
}
