/**
 * The empty state of the Properties card (decision 8.118 Q1, amended): with no
 * property to show, a user who may add evidence gets a quiet link to the
 * evidence form; everyone else keeps the plain sentence. The card is only given
 * the link, so the permission (`canAddEvidence`) stays outside it.
 */
export type PropertiesEmpty =
  | { kind: 'none' }
  | { kind: 'plain' }
  | { kind: 'link'; href: string }

export function propertiesEmptyState(hasProperties: boolean, addEvidenceHref: string | null | undefined): PropertiesEmpty {
  if (hasProperties) return { kind: 'none' }
  return addEvidenceHref ? { kind: 'link', href: addEvidenceHref } : { kind: 'plain' }
}

/** The address of the evidence form of an element, or null when the user may not add evidence. */
export function addEvidenceHref(identityId: string, allowed: boolean): string | null {
  return allowed ? `/components/${encodeURIComponent(identityId)}/evidence/new` : null
}
