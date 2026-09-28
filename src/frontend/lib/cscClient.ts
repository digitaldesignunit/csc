import pkg from '../package.json'

/**
 * Identifies the web frontend to the backend on every server-side request
 * (`X-CSC-Client: web/<version>`, data model spec §7.4). The version comes
 * from package.json so it moves with each release.
 */
export const CSC_CLIENT_HEADERS: Record<string, string> = {
  'X-CSC-Client': `web/${pkg.version}`,
}
