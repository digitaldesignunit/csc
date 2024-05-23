import { NextRequest, NextResponse } from 'next/server'
import { set_token } from '@/lib/tokencache'

export async function POST() {
  const token_url: string = process.env.API_TOKEN_URL as string;
  const username: string = process.env.API_USER as string;
  const password: string = process.env.API_PASS as string;

  const form_data = new URLSearchParams({
    'grant_type': 'password',
    'username': username,
    'password': password,
  })

  // execute fetch
  let tokendata = await fetch(
    token_url,
    {
      method: 'POST',
      mode: 'cors',
      headers: 
      {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: form_data.toString(),
      cache: 'no-cache',
    }
  ).then(async (response) => {
    console.log(`Fetch Token Response Status: ${response.status}`)
    let data = await response.json()
    return data
  }).catch((err) => {
    console.log('Fetch Token Response Rejected! Aborting...')
    console.log(err)
    NextResponse.json({ error: 'Fetch Token Response Rejected!' }, { status: 500 })
  })
  let token = await tokendata.access_token
  set_token(token);
  return NextResponse.json(tokendata, { status: 200 })
}