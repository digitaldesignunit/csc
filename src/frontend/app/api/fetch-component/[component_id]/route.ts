import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'
import { ComponentData } from '@/components/models'
import { timestamp_string } from '@/lib/utils'

const fetch_component = async (
  component_id: string,
  retried: boolean = false
) => {
  const endpoint_url = `https://api.ddu.uber.space/components/${component_id}`
  let headers = await create_headers()
  let component: ComponentData = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers,
      cache: 'no-cache'
    }
  ).then( async (response) => {
    console.log(timestamp_string() + `: Get Component Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log(timestamp_string() + ': Response Unauthorized! Attempting Retry...')
      return await fetch_component(component_id, true)
    }
    return response.json()
  }).catch(async (err) => {
    if (!retried) {
      console.log(timestamp_string() + ': Get Component Response Rejected!')
      console.log(`Error: ${err}`)
      console.log('Attempting retry...')
      return await fetch_component(component_id, true)
    } else {
      console.log(timestamp_string() + ': Get Component 2nd Response Rejected! Aborting...')
      console.log(`Error: ${err}`)
      return []
    }
  })
  return component
}

export async function GET(
  request: NextRequest,
  { params }: { params: { component_id: string } }
) {
  const { component_id } = params;
  try {
    const component = await fetch_component(component_id, false)
    return NextResponse.json(component, { status: 200 })
  } catch (err) {
    return NextResponse.json({ error: 'Fetch Component Response Rejected!' }, { status: 500 })
  }
}