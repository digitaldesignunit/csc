import { NextRequest, NextResponse } from 'next/server'
import { create_headers } from '@/lib/headers'
import { timestamp_string } from '@/lib/utils'

/**
 * Fetch the component's texture file (.jpg) from the backend.
 * Retries once if receiving a 401 Unauthorized.
 */
const fetch_component_texture = async (
  component_id: string,
  retried: boolean = false
): Promise<ArrayBuffer> => {
  // Example: /components/<component_id>/texture
  const endpoint_url = `https://api.ddu.uber.space/components/${component_id}/texture`
  const headers = await create_headers()

  // Perform fetch for the texture file
  const textureData = await fetch(endpoint_url, {
    method: 'GET',
    mode: 'cors',
    headers,
    cache: 'no-cache',
  })
    .then(async (response) => {
      console.log(timestamp_string() + `: Get Component Texture Response Status: ${response.status}`)
      // Check for 401 → attempt a single retry
      if (response.status === 401 && !retried) {
        console.log(timestamp_string() + ': Response Unauthorized! Attempting Retry...')
        return await fetch_component_texture(component_id, true)
      }
      if (!response.ok) {
        throw new Error(`Texture fetch failed with status: ${response.status}`)
      }
      // Return the file contents as an ArrayBuffer, since it's binary image data
      return response.arrayBuffer()
    })
    .catch(async (err) => {
      if (!retried) {
        console.log(timestamp_string() + ': Get Component Texture Response Rejected! Retrying...')
        console.log('Error:', err)
        return await fetch_component_texture(component_id, true)
      } else {
        console.log(timestamp_string() + ': Get Component Texture 2nd Response Rejected! Aborting...')
        console.log('Error:', err)
        // Return an empty buffer or throw an error
        throw err
      }
    })

  return textureData
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url, process.env.NEXT_PUBLIC_BASE_URL)
  const component_id = searchParams.get('component_id') || ''

  try {
    // This returns the texture file's contents as an ArrayBuffer
    const textureData = await fetch_component_texture(component_id, false)

    // If there's no data, return a 404
    if (!textureData || textureData.byteLength === 0) {
      return NextResponse.json({ error: 'No texture data received' }, { status: 404 })
    }

    // Return the texture as binary data with the correct Content-Type
    return new NextResponse(textureData, {
      status: 200,
      headers: {
        'Content-Type': 'image/jpeg',
      },
    })
  } catch (err) {
    console.error(timestamp_string() + ': Fetch Component Texture Route Failed:', err)
    return NextResponse.json(
      { error: 'Fetch Component Texture Failed!' },
      { status: 500 }
    )
  }
}
