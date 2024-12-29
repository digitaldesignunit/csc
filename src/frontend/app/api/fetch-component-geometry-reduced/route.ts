import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'
import { timestamp_string } from '@/lib/utils'

/**
 * Fetch the component's reduced geometry (OBJ file) from the backend.
 * Retries once if receiving a 401 Unauthorized.
 */
const fetch_component_geometry_reduced = async (
  component_id: string,
  retried: boolean = false
): Promise<string> => {
  const endpoint_url = `https://api.ddu.uber.space/components/${component_id}/geometry_reduced`
  const headers = await create_headers()

  // Perform fetch for the OBJ file
  const objFileData = await fetch(endpoint_url, {
    method: 'GET',
    mode: 'cors',
    headers,
    cache: 'no-cache',
  })
    .then(async (response) => {
      console.log(timestamp_string() + `: Get Component Reduced Geometry Response Status: ${response.status}`)
      // Check for 401 → attempt a single retry
      if (response.status === 401 && !retried) {
        console.log(timestamp_string() + ': Response Unauthorized! Attempting Retry...')
        return await fetch_component_geometry_reduced(component_id, true)
      }
      // Return the file contents as text, because it’s an OBJ file
      return response.text()
    })
    .catch(async (err) => {
      if (!retried) {
        console.log(timestamp_string() + ': Get Reduced Geometry Response Rejected! Retrying...')
        console.log('Error:', err)
        return await fetch_component_geometry_reduced(component_id, true)
      } else {
        console.log(timestamp_string() + ': Get reduced Geometry 2nd Response Rejected! Aborting...')
        console.log('Error:', err)
        return ''
      }
    })

  return objFileData
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url, process.env.NEXT_PUBLIC_BASE_URL)
  const component_id = searchParams.get('component_id') || ''

  try {
    // This returns the OBJ file's contents as a string
    const objFileData = await fetch_component_geometry_reduced(component_id, false)

    if (!objFileData) {
      return NextResponse.json({ error: 'No OBJ data received' }, { status: 404 })
    }

    // Return the OBJ file as text with correct Content-Type
    return new NextResponse(objFileData, {
      status: 200,
      headers: {
        'Content-Type': 'model/obj',
      },
    })
  } catch (err) {
    console.error(timestamp_string() + ': Fetch Reduced Geometry Route Failed:', err)
    return NextResponse.json(
      { error: 'Fetch Reduced Geometry Failed!' },
      { status: 500 }
    )
  }
}
