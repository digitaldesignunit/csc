
let API_TOKEN: string = ''
let API_TIMEOUT_MINS = Number(process.env.API_TOKEN_TIMEOUT_MINS)
let token_expiry: number | null = null

export const get_token = () => API_TOKEN

export const set_token = (new_token: string) => {
  API_TOKEN = new_token
  // Convert timeout minutes from minutes to milliseconds
  token_expiry = Date.now() + (API_TIMEOUT_MINS * 60 * 1000)
}

export const is_token_expired = () => {
  if (!API_TOKEN || !token_expiry) {
    return true
  }
  return Date.now() > token_expiry
}