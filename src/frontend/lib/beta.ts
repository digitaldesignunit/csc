import pkg from '../package.json'

/**
 * Beta notice texts (issue #52). The version in them is never typed into the
 * server's `.env`: a `{version}` placeholder in the text is replaced by the
 * version of `package.json` (set by `invoke bump-version`, read like
 * `lib/cscClient.ts` reads it). A text without the placeholder stays as it is.
 */
export const BETA_VERSION_PLACEHOLDER = '{version}'

export function fillBetaVersion(text: string, version: string = pkg.version): string {
  return text.split(BETA_VERSION_PLACEHOLDER).join(version)
}

function parseEnvFlag(value: string | undefined): boolean {
  if (!value) return false
  const normalized = value.trim().toLowerCase()
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on'
}

function parseEnvString(value: string | undefined, fallback: string): string {
  if (!value?.trim()) return fallback
  const trimmed = value.trim()
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1)
  }
  return trimmed
}

export function isBetaPhaseEnabled(): boolean {
  return parseEnvFlag(process.env.BETA_PHASE)
}

export function getBetaBannerText(): string {
  return fillBetaVersion(parseEnvString(process.env.BETA_BANNER_TEXT, 'Beta {version}'))
}

export function getBetaLoginMessage(): string {
  return fillBetaVersion(
    parseEnvString(
      process.env.BETA_LOGIN_MESSAGE,
      'The Catalog of Second Chances is currently in a beta phase (version {version}). You may encounter incomplete features, breaking changes, or data updates. Thank you for helping us improve the platform.',
    ),
  )
}
