/**
 * The password rules of the backend (register, change-password, reset;
 * decision 8.124): 8 to 72 characters, at most 72 bytes in UTF-8 (bcrypt
 * reads no more). Pure, so the unit test covers it.
 */
export const PASSWORD_MIN = 8
export const PASSWORD_MAX_BYTES = 72

/** What is wrong with a new password, or null. */
export function passwordProblem(value: string): string | null {
  if (value.length < PASSWORD_MIN) return `Use at least ${PASSWORD_MIN} characters.`
  if (new TextEncoder().encode(value).length > PASSWORD_MAX_BYTES) {
    return `Use at most ${PASSWORD_MAX_BYTES} bytes (fewer characters if it has umlauts or symbols).`
  }
  return null
}

/** The sign-in page's notice after a password was changed or reset. */
export const PASSWORD_CHANGED_PARAM = 'notice'
export const PASSWORD_CHANGED_VALUE = 'password-changed'
