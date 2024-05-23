import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'

const fetch_componentcount = async (
  retried: boolean = false
) => {
  const endpoint_url = 'https://api.ddu.uber.space/componentcount'
  let headers = await create_headers()
  let count: Number = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers,
      cache: 'no-cache'
    }
  ).then( async (response) => {
    console.log(`Component Count Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log('Response Unauthorized! Attempting Retry...')
      return await fetch_componentcount(true)
    }
    return response.json()
  }).catch(async (err) => {
    if (!retried) {
      console.log('Component Count Response Rejected!')
      console.log(`Error: ${err}`)
      console.log('Attempting retry...')
      return await fetch_componentcount(true)
    } else {
      console.log('Component Count 2nd Response Rejected! Aborting...')
      console.log(`Error: ${err}`)
      return []
    }
  });
  return count
}

export async function GET(request: NextRequest) {
  try {
    const count: Number = await fetch_componentcount(false)
    return NextResponse.json(count, { status: 200 });
  } catch (err) {
    return NextResponse.json({ error: 'Fetch Components Response Rejected!' }, { status: 500 });
  }
}