/**
 * "Element", not "piece" (decision 8.183): no text a user sees in the web app
 * says "piece" or "pieces". The check reads the string literals, the template
 * text and the JSX text of every source of the app (comments, identifiers and
 * the titles of tests are not text), so the word cannot come back by a new
 * label, a toast or a help text.
 *
 * Allowed: a word that is a code value or part of an id (a lane role `'piece'`,
 * the fan-out `'pieces'`, `exit-set-by-pieces`), and "piece" in another sense
 * ("a piece of software").
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
  assert.deepEqual(problems, [], `say "element" instead:\n${problems.join('\n')}`)
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
