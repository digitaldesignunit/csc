import { get_token, is_token_expired, set_token } from '@/lib/tokencache';

export async function create_headers() {
  if (is_token_expired()) {
    const token_response = await fetch(
      `${process.env.NEXT_PUBLIC_BASE_URL}/api/fetch-token`,
      {
        method: 'POST',
        cache: 'no-store'
      }
    )
    if (!token_response.ok) {
      throw new Error('Failed to fetch token');
    }
    const token_data = await token_response.json();
    set_token(token_data.access_token);
  }
  const token = get_token();
  return { 'Authorization': `Bearer ${token}` };
}