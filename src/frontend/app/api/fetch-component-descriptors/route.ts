import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'
import { ComponentData } from '@/components/models'
import { timestamp_string } from '@/lib/utils'

const fetch_component_descriptors = async (
  component_id: string,
  retried: boolean = false
) => {
  const endpoint_url = `https://api.ddu.uber.space/components/${component_id}/descriptors`
  let headers = await create_headers()
  let component_descriptors: ComponentData = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers,
      cache: 'no-cache'
    }
  ).then( async (response) => {
    console.log(timestamp_string() + `: Get Component Descriptors Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log(timestamp_string() + ': Response Unauthorized! Attempting Retry...')
      return await fetch_component_descriptors(component_id, true)
    }
    return response.json()
  }).catch(async (err) => {
    if (!retried) {
      console.log(timestamp_string() + ': Get Component Descriptors Response Rejected!')
      console.log(`Error: ${err}`)
      console.log('Attempting retry...')
      return await fetch_component_descriptors(component_id, true)
    } else {
      console.log(timestamp_string() + ': Get Component Descriptors 2nd Response Rejected! Aborting...')
      console.log(`Error: ${err}`)
      return []
    }
  })
  return component_descriptors
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url, process.env.NEXT_PUBLIC_BASE_URL)
  const component_id = searchParams.get('component_id') || ''
  try {
    const component_descriptors = await fetch_component_descriptors(component_id, false)
    return NextResponse.json(component_descriptors, { status: 200 })
  } catch (err) {
    return NextResponse.json({ error: 'Fetch Component Descriptors Response Rejected!' }, { status: 500 })
  }
}