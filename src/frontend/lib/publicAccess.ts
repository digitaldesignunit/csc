/** Matches `/components/{uuid}` detail pages (not list, not edit). */
export const PUBLIC_COMPONENT_DETAIL_PATH = /^\/components\/[0-9a-f-]{36}$/i

/** The pages an anonymous visitor may open besides a component's page: Browse,
 *  the map and Analytics show the public tier only (decision 8.118 Q8); the
 *  Grasshopper page has no account data. */
export const PUBLIC_CATALOG_PAGES = ['/components', '/components/map', '/analytics', '/gh-interface']

export function isPublicComponentDetailPath(pathname: string): boolean {
  return PUBLIC_COMPONENT_DETAIL_PATH.test(pathname)
}

/** The component screenshots of the Grasshopper page (public/gh-interface). */
export const PUBLIC_GH_SCREENSHOT_PATH = /^\/gh-interface\/[\w.-]+\.(jpe?g|png|webp)$/i

export function isPublicCatalogPage(pathname: string): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  return PUBLIC_CATALOG_PAGES.includes(path)
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
    || isPublicCatalogPage(pathname)
    || (PUBLIC_GH_SCREENSHOT_PATH.test(pathname) && (method === 'GET' || method === 'HEAD'))
    || isAnonymousBackendReadPath(pathname, method)
  )
}
