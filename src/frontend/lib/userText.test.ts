/**
 * The words of user text follow the data model (decisions 8.183, 8.194 and 8.196):
 *
 * - "Component" (or "element", an item of a batch), not "piece": no text a user
 *   sees in the web app says "piece" or "pieces".
 * - A recorded state is a "snapshot", never a "version" ("v1" is its number).
 *   "Version" stays for the software and a release, a file format and the
 *   number of a snapshot.
 * - The catalogue record of a component is a "component" and its UUID a
 *   "component id", never an "identity" -- except on the Data Model page, where
 *   the glossary term explains the model.
 * - "new state", "this state" and "current state" say "snapshot" too ("state"
 *   stays for the physical condition a snapshot records).
 *
 * The check reads the string literals, the template text and the JSX text of
 * every source of the app (comments, identifiers and the titles of tests are
 * not text), so a word cannot come back by a new label, a toast or a help text.
 *
 * Allowed: a word that is a code value or part of an id (a lane role `'piece'`,
 * the fan-out `'pieces'`, `exit-set-by-pieces`, an API path `/identities/..`),
 * "piece" in another sense ("a piece of software"), and the files named in
 * `ALLOWED` below, each for its reason.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

import ts from 'typescript'

const ROOT = process.cwd()
const BASES = ['app', 'components', 'lib']
const SKIP_DIRS = new Set(['node_modules', '.next', 'public', 'generated'])
const WORD = /\b[Pp]ieces?\b/

/** "piece" in another sense. */
const OTHER_SENSE = [/piece of software/i, /piece of information/i]

function* sources(dir: string): Generator<string> {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(entry.name)) continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) yield* sources(full)
    else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) yield full
  }
}

function isText(node: ts.Node): boolean {
  const k = node.kind
  return k === ts.SyntaxKind.StringLiteral || k === ts.SyntaxKind.NoSubstitutionTemplateLiteral
    || k === ts.SyntaxKind.TemplateHead || k === ts.SyntaxKind.TemplateMiddle || k === ts.SyntaxKind.TemplateTail
    || k === ts.SyntaxKind.JsxText || k === ts.SyntaxKind.RegularExpressionLiteral
}

/** The texts of a source that say "piece": [line, text]. */
export function pieceTexts(file: string, text: string): [number, string][] {
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const found: [number, string][] = []
  const visit = (node: ts.Node) => {
    if (isText(node)) {
      const start = node.getStart(sf)
      const segment = text.slice(start, node.getEnd())
      if (WORD.test(segment)) {
        const single = /^['"`]\s*[Pp]ieces?\s*['"`]$/.test(segment.trim())
        const inId = /[-_/][Pp]ieces?\b|\b[Pp]ieces?[-_/]/.test(segment)
        const other = OTHER_SENSE.some((re) => re.test(segment))
        if (!single && !inId && !other) {
          found.push([text.slice(0, start).split('\n').length, segment.replace(/\s+/g, ' ').slice(0, 100)])
        }
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

test('no text of the web app says "piece" (8.183)', () => {
  const problems: string[] = []
  for (const base of BASES) {
    for (const file of sources(path.join(ROOT, base))) {
      const rel = path.relative(ROOT, file).replace(/\\/g, '/')
      for (const [line, segment] of pieceTexts(file, fs.readFileSync(file, 'utf-8'))) {
        problems.push(`${rel}:${line}: ${segment}`)
      }
    }
  }
  assert.deepEqual(problems, [], `say "component" instead (an item of a batch is an "element"):\n${problems.join('\n')}`)
})

test('the check sees a label, a template and JSX text, and lets a code value and an id pass', () => {
  assert.equal(pieceTexts('a.tsx', "const a = 'Draw pieces'").length, 1)
  assert.equal(pieceTexts('a.tsx', 'const a = `${n} pieces left`').length, 1)
  assert.equal(pieceTexts('a.tsx', 'const a = <p>The piece is public</p>').length, 1)
  assert.equal(pieceTexts('a.tsx', 'const a = <p aria-label="Piece opacity" />').length, 1)
  assert.equal(pieceTexts('a.ts', "if (lane.role === 'piece') {}").length, 0)
  assert.equal(pieceTexts('a.ts', "const key = 'viewer-piece-opacity'").length, 0)
  assert.equal(pieceTexts('a.ts', "const key = 'exit-set-by-pieces'").length, 0)
  assert.equal(pieceTexts('a.ts', "const a = 'This piece of software is part of a thesis'").length, 0)
  // a comment and an identifier are not text
  assert.equal(pieceTexts('a.ts', '// the piece is public\nconst pieces = piece.length').length, 0)
})

// --- identity, version and state (decision 8.196) ---------------------------------------------------

const IDENTITY = /(?<![\w/.-])[Ii]dentit(?:y|ies)(?![\w/-])/
const VERSION = /(?<![\w/.-])[Vv]ersions?(?![\w/-])/
const NEW_STATE = /(?<![\w/.-])(?:(?:[Nn]ew|[Tt]his|[Cc]urrent) states?|[Rr]ecord(?:ed)? state)(?![\w/-])/

/** Where a term stays, and why. A path is a file, or a folder when it ends in a slash. */
const ALLOWED: Record<'identity' | 'version' | 'state', string[]> = {
  // the Data Model page explains the model; "identity" is the glossary term there
  identity: ['lib/dataModelText.ts', 'lib/dataModelExamples.ts', 'lib/dataModelTabs.ts', 'components/reference/', 'app/reference/'],
  // the release of the software (the Grasshopper page, the beta banner) and the Grasshopper XML format
  version: ['app/gh-interface/GHInterfacePageClient.tsx', 'lib/beta.ts', 'lib/utils.ts'],
  // the Data Model page defines "state" (the physical condition a snapshot records)
  state: ['lib/dataModelText.ts', 'lib/dataModelExamples.ts', 'components/reference/'],
}

/** "version number" and a file format say version in its other senses. */
const VERSION_OTHER_SENSE = [/version numbers?/i, /<\?xml version/i]

/**
 * The texts of a source that say `term` as a word of prose: [line, text]. A text
 * of one lower-case token is a code value, a key or an id and passes; a lone
 * capitalised word ("Versions", "Identity") is a label and does not.
 */
export function termTexts(file: string, text: string, term: RegExp, otherSense: RegExp[] = []): [number, string][] {
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const found: [number, string][] = []
  const visit = (node: ts.Node) => {
    if (isText(node) && node.kind !== ts.SyntaxKind.RegularExpressionLiteral) {
      const start = node.getStart(sf)
      const segment = text.slice(start, node.getEnd())
      const body = segment.replace(/^['"`}]|['"`]$|\$\{$/g, '').trim()
      if (term.test(segment) && !otherSense.some((re) => re.test(segment))) {
        const k = node.kind
        // a piece of a template or JSX text is prose, whatever its length; a lone quoted token is a code value
        const prose = /\s/.test(body) || k === ts.SyntaxKind.JsxText || k === ts.SyntaxKind.TemplateHead
          || k === ts.SyntaxKind.TemplateMiddle || k === ts.SyntaxKind.TemplateTail
        const label = /^[A-Z][a-z]+s?$/.test(body)
        if (prose || label) found.push([text.slice(0, start).split('\n').length, segment.replace(/\s+/g, ' ').slice(0, 100)])
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

function allowed(kind: keyof typeof ALLOWED, rel: string): boolean {
  return ALLOWED[kind].some((p) => (p.endsWith('/') ? rel.startsWith(p) : rel === p))
}

function termProblems(kind: keyof typeof ALLOWED, term: RegExp, otherSense: RegExp[] = []): string[] {
  const problems: string[] = []
  for (const base of BASES) {
    for (const file of sources(path.join(ROOT, base))) {
      const rel = path.relative(ROOT, file).replace(/\\/g, '/')
      if (allowed(kind, rel)) continue
      for (const [line, segment] of termTexts(file, fs.readFileSync(file, 'utf-8'), term, otherSense)) {
        problems.push(`${rel}:${line}: ${segment}`)
      }
    }
  }
  return problems
}

test('no text of the web app says "identity" outside the Data Model page (8.196 a)', () => {
  const problems = termProblems('identity', IDENTITY)
  assert.deepEqual(problems, [], `say "component" or "component id" instead:\n${problems.join('\n')}`)
})

test('no text of the web app calls a snapshot a "version" (8.196 c)', () => {
  const problems = termProblems('version', VERSION, VERSION_OTHER_SENSE)
  assert.deepEqual(problems, [], `say "snapshot" instead ("v1" is its number):\n${problems.join('\n')}`)
})

test('no text of the web app says "new state", "this state" or "current state" for a snapshot (8.196 c)', () => {
  const problems = termProblems('state', NEW_STATE)
  assert.deepEqual(problems, [], `say "snapshot" instead ("state" is the physical condition):\n${problems.join('\n')}`)
})

test('the check sees prose and labels, and lets a code value, a path and another sense pass', () => {
  const v = (code: string) => termTexts('a.tsx', code, VERSION, VERSION_OTHER_SENSE).length
  assert.equal(v("const a = 'Correct a version'"), 1)
  assert.equal(v('const a = `Delete the ${n} versions`'), 1)
  assert.equal(v('const a = <p>This version is withdrawn</p>'), 1)
  assert.equal(v('const a = <h3>Versions</h3>'), 1)
  assert.equal(v("const a = { label: 'Version' }"), 1)
  assert.equal(v("if (event.kind === 'version') {}"), 0)
  assert.equal(v("const k = 'manage-versions'"), 0)
  assert.equal(v("const p = '/api/backend/version'"), 0)
  assert.equal(v("const a = 'Enter the version number'"), 0)
  assert.equal(v("const a = '<?xml version=\"1.0\"?>'"), 0)
  assert.equal(v('// a version of the page\nconst version = 1'), 0)
  const i = (code: string) => termTexts('a.tsx', code, IDENTITY).length
  assert.equal(i("const a = 'Enter a valid identity UUID'"), 1)
  assert.equal(i("const a = <Field label='Identity id' />"), 1)
  assert.equal(i("const a = { label: 'Identity' }"), 1)
  assert.equal(i('const url = `/identities/${id}/compose`'), 0)
  assert.equal(i("const s = 'identity'"), 0)
  assert.equal(i("const s = scope === 'identity'"), 0)
  const s = (code: string) => termTexts('a.tsx', code, NEW_STATE).length
  assert.equal(s("const a = 'Record new state'"), 1)
  assert.equal(s("const a = 'Record state'"), 1)
  assert.equal(s("const a = 'The physical state of the beam'"), 0)
})
