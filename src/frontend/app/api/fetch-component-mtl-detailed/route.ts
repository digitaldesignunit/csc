import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'
import { timestamp_string } from '@/lib/utils'

/**
 * Fetch the component's detailed material (.mtl) from the backend.
 * Retries once if receiving a 401 Unauthorized.
 */
const fetch_component_material_detailed = async (
  component_id: string,
  retried: boolean = false
): Promise<string> => {
  // Example: /components/<component_id>/material_detailed
  const endpoint_url = `https://api.ddu.uber.space/components/${component_id}/material_detailed`
  const headers = await create_headers()

  // Perform fetch for the MTL file
  const mtlFileData = await fetch(endpoint_url, {
    method: 'GET',
    mode: 'cors',
    headers,
    cache: 'no-cache',
  })
    .then(async (response) => {
      console.log(timestamp_string() + `: Get Detailed Material Response Status: ${response.status}`)
      // Check for 401 → attempt a single retry
      if (response.status === 401 && !retried) {
        console.log(timestamp_string() + ': Response Unauthorized! Attempting Retry...')
        return await fetch_component_material_detailed(component_id, true)
      }
      // Return the file contents as text, because it’s an MTL file
      return response.text()
    })
    .catch(async (err) => {
      if (!retried) {
        console.log(timestamp_string() + ': Get Detailed Material Response Rejected! Retrying...')
        console.log('Error:', err)
        return await fetch_component_material_detailed(component_id, true)
      } else {
        console.log(timestamp_string() + ': Get Detailed Material 2nd Response Rejected! Aborting...')
        console.log('Error:', err)
        return ''
      }
    })

  return mtlFileData
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url, process.env.NEXT_PUBLIC_BASE_URL)
  const component_id = searchParams.get('component_id') || ''

  try {
    // This returns the MTL file's contents as a string
    const mtlFileData = await fetch_component_material_detailed(component_id, false)

    if (!mtlFileData) {
      return NextResponse.json({ error: 'No MTL data received' }, { status: 404 })
    }

    // Return the MTL file as text with a suitable Content-Type
    // MTL does not have an official MIME type, but text/plain is typical
    return new NextResponse(mtlFileData, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
      },
    })
  } catch (err) {
    console.error(timestamp_string() + ': Fetch Detailed Material Route Failed:', err)
    return NextResponse.json(
      { error: 'Fetch Detailed Material Failed!' },
      { status: 500 }
    )
  }
}
