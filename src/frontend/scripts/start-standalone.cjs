#!/usr/bin/env node
/**
 * Start Next standalone with explicit env loading.
 *
 * `node server.js` alone can miss `.env.local` / `.env` depending on Next version
 * and how supervisord launches the process — which makes /api/auth/* return 500.
 *
 * Usage (from the standalone root, next to server.js):
 *   node start-standalone.cjs
 */
const fs = require('fs')
const path = require('path')

function stripQuotes(value) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1)
  }
  return value
}

function loadEnvFile(filePath, { override = false } = {}) {
  if (!fs.existsSync(filePath)) return false
  const text = fs.readFileSync(filePath, 'utf8')
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq <= 0) continue
    const key = line.slice(0, eq).trim()
    const value = stripQuotes(line.slice(eq + 1).trim())
    if (!key) continue
    if (!override && process.env[key] !== undefined) continue
    process.env[key] = value
  }
  return true
}

const root = process.cwd()

// Match Next's general idea: base files first, then local overrides.
const loaded = []
for (const name of ['.env', '.env.production']) {
  if (loadEnvFile(path.join(root, name), { override: false })) loaded.push(name)
}
for (const name of ['.env.local', '.env.production.local']) {
  if (loadEnvFile(path.join(root, name), { override: true })) loaded.push(name)
}

const required = [
  'NEXTAUTH_SECRET',
  'NEXTAUTH_URL',
  'MONGODB_URI',
  'MONGODB_DB',
  'MONGODB_USERCOLLECTION',
  'FASTAPI_URL',
]

const missing = required.filter((key) => !process.env[key] || !String(process.env[key]).trim())
console.log(
  `[start-standalone] cwd=${root} loaded=[${loaded.join(', ') || 'none'}] node=${process.version}`
)
if (missing.length) {
  console.error(`[start-standalone] Missing required env: ${missing.join(', ')}`)
  console.error(
    '[start-standalone] Add them to .env or .env.local next to server.js, then restart frontend.'
  )
  process.exit(1)
}

console.log(
  `[start-standalone] NEXTAUTH_URL=${process.env.NEXTAUTH_URL} — starting server.js`
)

require('./server.js')
