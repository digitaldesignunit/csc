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
  return parseEnvString(process.env.BETA_BANNER_TEXT, 'Beta')
}

export function getBetaLoginMessage(): string {
  return (
    parseEnvString(
      process.env.BETA_LOGIN_MESSAGE,
      'The Catalog of Second Chances is currently in a beta phase. You may encounter incomplete features, breaking changes, or data updates. Thank you for helping us improve the platform.',
    )
  )
}
