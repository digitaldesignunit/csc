/**
 * Which footer a page gets (plan P11 stage 3, decision 8.118 C-4): the full
 * footer only on the public pages, one thin line in the signed-in app, none
 * inside a form. The Imprint stays one tap away from every page: it is in the
 * thin line and in the account menu.
 */
export type FooterMode = 'full' | 'thin' | 'none'

const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
const FORM_PATHS = [
  /^\/add-component(\/|$)/,
  new RegExp(`^/components/${UUID}/(snapshot/new|evidence/new|edit)(/|$)`, 'i'),
]
const PUBLIC_PATHS = [/^\/$/, /^\/auth(\/|$)/, /^\/credits$/, /^\/imprint$/]
const PUBLIC_CATALOG_PATHS = [/^\/components$/, new RegExp(`^/components/${UUID}$`, 'i')]

export function footerMode(pathname: string, signedIn: boolean): FooterMode {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  if (FORM_PATHS.some((p) => p.test(path))) return 'none'
  if (PUBLIC_PATHS.some((p) => p.test(path))) return 'full'
  // Browse and a component page are public pages for a visitor, app pages for a member
  if (!signedIn && PUBLIC_CATALOG_PATHS.some((p) => p.test(path))) return 'full'
  return 'thin'
}
