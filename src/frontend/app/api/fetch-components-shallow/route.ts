import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'
import { ComponentData } from '@/components/models'
import { timestamp_string } from '@/lib/utils'

const fetch_components_shallow = async (
  page_num: string,
  page_size: string,
  sortkey: string,
  comptype: string,
  material: string,
  retried: boolean = false
) => {
  const endpoint_url = `https://api.ddu.uber.space/shallowcomponents?page=${page_num}&size=${page_size}&sortkey=${sortkey}&comptype=${comptype}&material=${material}`
  let headers = await create_headers()
  let components: Array<ComponentData> = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers,
      cache: 'no-cache'
    }
  ).then( async (response) => {
    console.log(timestamp_string() + `: Get Components Shallow Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log(timestamp_string() + ': Response Unauthorized! Attempting Retry...')
      return await fetch_components_shallow(page_num, page_size, sortkey, comptype, material, true)
    }
    return response.json()
  }).catch(async (err) => {
    if (!retried) {
      console.log(timestamp_string() + ': Get Components Shallow Response Rejected!')
      console.log(`Error: ${err}`)
      console.log('Attempting retry...')
      return await fetch_components_shallow(page_num, page_size, sortkey, comptype, material, true)
    } else {
      console.log(timestamp_string() + ': Get Components Shallow 2nd Response Rejected! Aborting...')
      console.log(`Error: ${err}`)
      return []
    }
  })
  return components
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url, process.env.NEXT_PUBLIC_BASE_URL)
  const page_num = searchParams.get('page') || '1'
  const page_size = searchParams.get('size') || '10'
  const sortkey = searchParams.get('sortkey') || '_id'
  const comptype = searchParams.get('comptype') || ''
  const material = searchParams.get('material') || ''
  try {
    const components = await fetch_components_shallow(page_num, page_size, sortkey, comptype, material, false)
    return NextResponse.json(components, { status: 200 })
  } catch (err) {
    return NextResponse.json({ error: 'Fetch Components Response Rejected!' }, { status: 500 })
  }
}