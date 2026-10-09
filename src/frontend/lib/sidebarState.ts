/**
 * The sidebar choice (decision 8.29), shared by the server layout, which
 * reads the cookie for the first paint, and the client sidebar, which
 * writes it.
 */
export type SidebarChoice = 'auto' | 'expanded' | 'collapsed'

export const SIDEBAR_COOKIE = 'csc_sidebar'

export function parseSidebarChoice(value: string | undefined): SidebarChoice {
  return value === 'expanded' || value === 'collapsed' ? value : 'auto'
}
