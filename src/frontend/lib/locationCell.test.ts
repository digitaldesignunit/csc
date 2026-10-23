/**
 * The location in the Browse table is a plain link (decision 8.176): no embedded
 * Google map, no iframe, no preview on hover. It opens Google Maps in a new tab
 * only on a click.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import LocationCell from '../components/components/overview/ComponentOverviewDataTableLocationCell'

const html = renderToStaticMarkup(createElement(LocationCell, { coords: { lat: 49.8728, lon: 8.6512 } }))

test('the location cell renders one link to Google Maps and no frame', () => {
  assert.ok(!/<iframe|<embed|<object/i.test(html), html)
  assert.equal((html.match(/<a /g) ?? []).length, 1)
  assert.match(html, /href="https:\/\/www\.google\.com\/maps\/place\/49\.872800,8\.651200"/)
  assert.match(html, /target="_blank"/)
  assert.match(html, /rel="noopener noreferrer"/)
  assert.match(html, /title="Open in Google Maps"/)
})

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (name === 'node_modules' || name === '.next' || name === 'generated') return []
    if (statSync(path).isDirectory()) return sources(path)
    return /\.(ts|tsx)$/.test(name) && !/\.test\.ts$/.test(name) ? [path] : []
  })
}

test('no page embeds a Google map: the only iframe is the sandboxed mail preview (a srcdoc frame)', () => {
  const root = join(__dirname, '..')
  const frames: string[] = []
  for (const dir of ['app', 'components', 'lib']) {
    for (const file of sources(join(root, dir))) {
      const text = readFileSync(file, 'utf8')
      assert.ok(!/maps\.google\.com|output=embed/.test(text), file)
      if (/<iframe/.test(text)) frames.push(file.slice(root.length + 1).replace(/\\/g, '/'))
    }
  }
  assert.deepEqual(frames, ['app/admin/mail-templates/page.tsx'])
  const mail = readFileSync(join(root, 'app', 'admin', 'mail-templates', 'page.tsx'), 'utf8')
  assert.match(mail, /sandbox=""/)
  assert.match(mail, /srcDoc=/)
})
