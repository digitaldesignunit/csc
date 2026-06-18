function parseEnvFlag(value: string | undefined): boolean {
  if (!value) return false
  const normalized = value.trim().toLowerCase()
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on'
}

export function isGhInterfaceDeactivated(): boolean {
  return parseEnvFlag(process.env.GH_INTERFACE_DEACTIVATED)
}
