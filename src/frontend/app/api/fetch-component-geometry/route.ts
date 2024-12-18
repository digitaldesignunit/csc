import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'
import { ComponentData } from '@/components/models'
import { timestamp_string } from '@/lib/utils'

const fetch_component_geometry = async (
  component_id: string,
  retried: boolean = false
) => {
  const endpoint_url = `https://api.ddu.uber.space/components/${component_id}/geometry`
  let headers = await create_headers()
  let component_geometry: ComponentData = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers,
      cache: 'no-cache'
    }
  ).then( async (response) => {
    console.log(timestamp_string() + `: Get Component Geometry Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log(timestamp_string() + ': Response Unauthorized! Attempting Retry...')
      return await fetch_component_geometry(component_id, true)
    }
    return response.json()
  }).catch(async (err) => {
    if (!retried) {
      console.log(timestamp_string() + ': Get Component Geometry Response Rejected!')
      console.log(`Error: ${err}`)
      console.log('Attempting retry...')
      return await fetch_component_geometry(component_id, true)
    } else {
      console.log(timestamp_string() + ': Get Component Geometry 2nd Response Rejected! Aborting...')
      console.log(`Error: ${err}`)
      return []
    }
  })
  return component_geometry
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url, process.env.NEXT_PUBLIC_BASE_URL)
  const component_id = searchParams.get('component_id') || ''
  try {
    const component_geometry = await fetch_component_geometry(component_id, false)
    return NextResponse.json(component_geometry, { status: 200 })
  } catch (err) {
    return NextResponse.json({ error: 'Fetch Components Response Rejected!' }, { status: 500 })
  }
}