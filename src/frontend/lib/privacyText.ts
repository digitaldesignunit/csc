/**
 * What the privacy page says: the data, the reasons, the legal basis and how
 * long it is kept. Kept apart from the page so that a test can hold the
 * statements to the code (the sign-in cookie, the photos, the logs).
 */

/** The day this text was last changed: the one place to edit with the text. */
export const LAST_UPDATED = '23 October 2026'

/** The controller's address for requests: the one on the Imprint. */
export const CONTACT_EMAIL = 'max.eschenbach@tu-darmstadt.de'

/** What is processed, why, on which legal basis, how long. */
export const ROWS: { what: string; why: string; basis: string; kept: string }[] = [
  {
    what: 'Account: username, e-mail address, password (stored as a salted hash only), role and dataset memberships; your full name if you give it.',
    why: 'To sign you in and to show who added or changed a record.',
    basis: 'Art. 6(1)(b) GDPR',
    kept: 'Until you ask for the account to be deleted; it is deleted on request.',
  },
  {
    what: 'Profile (optional): organisation, ROR, ORCID and your usual role. It is copied into the records you make.',
    why: 'To fill in "performed by" for you.',
    basis: 'Art. 6(1)(a) GDPR, your consent',
    kept: 'Until you change or clear it; copies stay in your records.',
  },
  {
    what: 'Contributions: components, evidence records, photos and files, with your username. Names and ORCID in "performed by" are shown to signed-in users only. The location data (GPS position) in the metadata of a photo is removed when it is uploaded; the orientation, the capture time and the camera model are kept.',
    why: 'The catalogue itself: a documented record of re-used building components.',
    basis: 'Art. 6(1)(f) GDPR, the research interest in a documented catalogue',
    kept: 'Published records are withdrawn, not deleted; on request the personal data in them is redacted.',
  },
  {
    what: 'E-mails: address verification, password reset, invitations and notices about records.',
    why: 'To run your account and the review of contributions. No newsletters.',
    basis: 'Art. 6(1)(b) GDPR',
    kept: 'The site keeps no copy of sent mails.',
  },
  {
    what: "Server logs: the hosting provider's web server logs your IP address, the time and the requested page. The site's own request log keeps the time, the requested page, the status and the name of your browser or program (no IP address).",
    why: 'Operation and security.',
    basis: 'Art. 6(1)(f) GDPR',
    kept: "The hosting provider keeps its logs for a short period; the site's own log is deleted after 14 days.",
  },
  {
    what: 'Map tiles: the Location Map page loads its map images from the tile server of FOSSGIS e.V. (Germany, tile.openstreetmap.de), which therefore receives your IP address and your browser data when you open that page. No other page loads them.',
    why: 'To show the map.',
    basis: 'Art. 6(1)(f) GDPR',
    kept: 'The site stores nothing of it; FOSSGIS e.V. keeps its server logs under its own rules.',
  },
  {
    what: 'Cookies and your device: the sign-in cookie, and on your device the theme, your Browse columns, the elements you opened last and this notice being closed.',
    why: 'Sign-in and your settings. No tracking, no statistics, no advertising.',
    basis: 'Section 25(2) TDDDG, needed for the service',
    kept: 'The sign-in cookie lasts at most 24 hours; the rest stays on your device until you clear it.',
  },
]
