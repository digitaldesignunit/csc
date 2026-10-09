import assert from 'node:assert/strict'
import { test } from 'node:test'

import { resolveStatic } from './utils'

function withBase<T>(base: string, run: () => T): T {
  const previous = process.env.NEXT_PUBLIC_STATIC_BASE_URL
  process.env.NEXT_PUBLIC_STATIC_BASE_URL = base
  try {
    return run()
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_STATIC_BASE_URL
    else process.env.NEXT_PUBLIC_STATIC_BASE_URL = previous
  }
}

test('only public UI files under /static/ may come from the static host', () => {
  withBase('https://static.example.org/csc_assets', () => {
    assert.equal(resolveStatic('/static/gh-interface/a.png'), 'https://static.example.org/csc_assets/static/gh-interface/a.png')
    // catalogue files never do: previews, photos, meshes, proxies, capture fixtures
    for (const path of ['/snapshot_previews/x.webp', '/snapshot_photos/x/0.jpg', '/meshes/x/0/reduced.ply',
      '/pointclouds/x/0.ply', '/proxies/x/0/+z.png', '/capture/x/fixtures/0.ply']) {
      assert.equal(resolveStatic(path), path)
    }
  })
})

test('bundled files and absolute URLs stay as they are, and no base means no host', () => {
  withBase('https://static.example.org', () => {
    assert.equal(resolveStatic('/logo/ddu_logo_white.png'), '/logo/ddu_logo_white.png')
    assert.equal(resolveStatic('https://other.example.org/a.png'), 'https://other.example.org/a.png')
    assert.equal(resolveStatic('data:image/png;base64,AAAA'), 'data:image/png;base64,AAAA')
  })
  withBase('', () => {
    assert.equal(resolveStatic('/static/a.png'), '/static/a.png')
  })
})
