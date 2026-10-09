/**
 * The pure parts of the Grasshopper page (plan P11 stage 3, decision 8.118
 * C-5): the component reference the backend parses from the release's sources
 * (`GET /ghinterface/reference`), grouped by subcategory and filtered by a
 * search.
 */
export type RefInput = { name: string; description: string }
export type RefOutput = { name: string; nickname: string; description: string }
export type RefComponent = {
  file: string
  name: string
  nickname: string
  category: string
  subcategory: string
  description: string
  version: string
  inputs: RefInput[]
  outputs: RefOutput[]
  /** The source has an OUTPUTS list at all (absent in the 0.5 sources). */
  outputs_declared?: boolean
}
export type Reference = {
  ref: string
  components: RefComponent[]
  skipped: { file: string; note: string }[]
}

/**
 * The maintainer tools (subcategory 0) are in the sources but not in the
 * reference a user reads; CSC_Update is the exception, it is the way in.
 */
export const HIDDEN_SUBCATEGORY = /^0\b/
export const UPDATE_FILE = 'DDU_CSC_Update.py'

/** "2 Catalog Interface" -> "Catalog Interface": the number only sorts. */
export function subcategoryTitle(subcategory: string): string {
  return subcategory.replace(/^\d+\s*/, '').trim() || 'Other'
}

export function visibleComponents(components: RefComponent[]): RefComponent[] {
  return components.filter((c) => !HIDDEN_SUBCATEGORY.test(c.subcategory) || c.file === UPDATE_FILE)
}

/** The components matching the search (name, nickname, description, ports). */
export function searchComponents(components: RefComponent[], query: string): RefComponent[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return components
  return components.filter((c) => {
    const texts = [
      c.name, c.nickname, c.description,
      ...c.inputs.flatMap((i) => [i.name, i.description]),
      ...c.outputs.flatMap((o) => [o.name, o.description]),
    ]
    return texts.some((t) => t.toLowerCase().includes(needle))
  })
}

/** Groups in the order of their subcategory number, each with its components by name. */
export function groupBySubcategory(
  components: RefComponent[],
): { key: string; title: string; components: RefComponent[] }[] {
  const groups = new Map<string, RefComponent[]>()
  for (const c of [...components].sort((a, b) =>
    a.subcategory.localeCompare(b.subcategory, 'en', { numeric: true })
    || a.name.localeCompare(b.name, 'en'))) {
    const key = c.subcategory
    groups.set(key, [...(groups.get(key) ?? []), c])
  }
  return [...groups.entries()].map(([key, items]) => ({ key, title: subcategoryTitle(key), components: items }))
}

/** The first sentence of a description, for the closed row. */
export function firstSentence(text: string): string {
  const end = text.search(/\.(\s|$)/)
  return end > 0 ? text.slice(0, end + 1) : text
}

const SCREENSHOT_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']

/**
 * The screenshot of a component: the file `csc_<lowercase name>.<ext>` among
 * the files of public/gh-interface, exact name only (a renamed component does
 * not take over the screenshot of its 0.5 ancestor, which shows old ports).
 */
export function screenshotFor(component: { name: string }, files: string[]): string | null {
  for (const ext of SCREENSHOT_EXTENSIONS) {
    const wanted = `csc_${component.name.toLowerCase()}.${ext}`
    const found = files.find((f) => f.toLowerCase() === wanted)
    if (found) return found
  }
  return null
}

/** The name of the user object XML on the server: the source file without `.py`. */
export function xmlNameOf(component: { file: string }): string {
  return component.file.replace(/\.py$/i, '')
}

/** A description as readable paragraphs (the source keeps its line breaks). */
export function paragraphsOf(text: string): string[] {
  return text.split(/\n+/).map((p) => p.trim()).filter(Boolean)
}

/** What an empty output table says: "None" only when OUTPUTS is declared and empty. */
export function noOutputsText(component: { outputs: unknown[]; outputs_declared?: boolean }): string {
  return component.outputs_declared === true ? 'None' : 'Outputs not declared in this release'
}
