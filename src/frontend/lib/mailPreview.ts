/**
 * The admin page "Mail templates" (decision 8.138 e): what the page needs
 * from a preview. The response of `GET /admin/mail-templates` lists every
 * mail with its rendered HTML and plain text.
 */
export type MailPreview = {
  kind: string
  label: string
  when: string
  subject: string
  reply_to?: string | null
  html: string
  text: string
}

export type MailPreviews = { to?: string | null; mails: MailPreview[] }

const DARK_QUERY = '@media (prefers-color-scheme: dark)'

/**
 * The HTML as a client in dark mode shows it: the mail carries its dark colours
 * in a `prefers-color-scheme: dark` block, and an iframe follows the browser's
 * setting, not the page's. The block is made unconditional for the preview.
 */
export function forcedDark(html: string): string {
  return html.split(DARK_QUERY).join('@media all')
}

export type PreviewScheme = 'light' | 'dark'
export type PreviewWidth = 'desktop' | 'phone'

/** The HTML for the chosen scheme. */
export function previewHtml(html: string, scheme: PreviewScheme): string {
  return scheme === 'dark' ? forcedDark(html) : html
}

/** The width of the frame: a phone is 375 px, a desktop mail client about 680. */
export const PREVIEW_WIDTHS: Record<PreviewWidth, number> = { desktop: 680, phone: 375 }

/** Why a test send failed, for the page: the backend's reason, else a general one. */
export function testFailure(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'The test mail could not be sent'
}
