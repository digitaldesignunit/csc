/** Matches `/components/{uuid}` detail pages (not list, not edit). */
export const PUBLIC_COMPONENT_DETAIL_PATH = /^\/components\/[0-9a-f-]{36}$/i

export function isPublicComponentDetailPath(pathname: string): boolean {
  return PUBLIC_COMPONENT_DETAIL_PATH.test(pathname)
}

export function isAnonymousBackendReadPath(
  pathname: string,
  method: string,
): boolean {
  return (
    pathname.startsWith('/api/backend/')
    && (method === 'GET' || method === 'HEAD')
  )
}

export function allowsAnonymousCatalogRead(
  pathname: string,
  method: string,
): boolean {
  return (
    isPublicComponentDetailPath(pathname)
    || isAnonymousBackendReadPath(pathname, method)
  )
}
