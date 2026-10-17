/**
 * The username rule of the backend (registration; decision 8.161): lowercase
 * letters and digits, then dots, underscores and hyphens, 3 to 32 characters,
 * starting with a letter or digit. The input is lowercased first, as on the
 * server. Pure, so the unit test covers it.
 */
export const USERNAME_PATTERN = /^[a-z0-9][a-z0-9._-]{2,31}$/

export const USERNAME_HINT =
  '3 to 32 characters: letters, digits, dot, underscore, hyphen; starts with a letter or digit. You can sign in with any case.'

/** What is wrong with a new username, or null. */
export function usernameProblem(value: string): string | null {
  const name = value.trim().toLowerCase()
  if (!name) return 'Username is required.'
  if (!USERNAME_PATTERN.test(name)) return `Username: ${USERNAME_HINT}`
  return null
}
