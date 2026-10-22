# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.4.0] - unreleased

Search and the location map.

### Added

- **"What fits?":** a Fits section in Browse's More filters finds pieces by size, whatever their
  orientation: *about this size* (within a tolerance in mm or %, default 10 %, closest first) or
  *can hold this size* (every side at least the asked one, least waste first). Each row shows how
  far off it is or how much it wastes, as a share of the piece and in m3 (per piece on batches). The
  list can also sort by volume, and the card view has a sort menu.
- **Near:** a Near section in Browse's More filters finds pieces around a point (a pasted "lat,
  lon"), by their current location or by their origin, within a radius in km or simply nearest
  first. Each row shows its distance, and the list sorts by it. A component page links to "Near
  this piece".
- **Origin coordinates:** the origin form of a piece takes the latitude and longitude of its
  origin place; until now they could be set only when the piece was created. In every location
  form a pasted "lat, lon" fills both boxes, and a comma after the latitude moves on to the
  longitude.
- **Location Map:** a new page next to the Similarity Map shows the pieces on a map, by their
  current location or by their origin, in clusters with counts. It takes the filters of Browse
  (with a "Show as list" link back), colours the pieces like the Similarity Map, opens a piece's
  preview on a click, and offers "Search near here" on a click into the map. The map images come
  from the tile server of FOSSGIS e.V. (tile.openstreetmap.de); only this page loads them.
- **Similar pieces:** a card on the component page shows the six pieces nearest in shape, over
  the whole shape descriptor rather than on the two-dimensional Similarity Map; size counts as
  well as the outline. "Show more" brings up to 24. The nearest pieces are also available at
  `GET /identities/{id}/similar`, with every Browse filter applied before the ranking.
- **MCP:** `search_components` takes `fit_mode`, `size_mm` and `tolerance`, `near_lat`,
  `near_lon`, `near_layer` and `radius_km` (each result with its distance), and `sort` and
  `order`; its description now says what the text query matches (name, id prefix, catalog
  number). The new tool `catalog_overview` counts the pieces of a search by material, original
  function, dataset, shape class and circulation, with the range of each side in mm, how many
  have a location and how many are not public. `similar_components` now ranks by the shape
  descriptor (with `basis`, `count` and the filters of `search_components`) instead of the
  distance on the Similarity Map.

### Changed

- **Registration:** without open domains the catalog is invite only, and the register page then
  asks for an invitation code and suggests no open sign-up. With open domains the page says that
  registration is open to certain domains and lists them behind a "?"; no page names a fixed
  university any more. `CSC_OPEN_REGISTRATION_DOMAINS` is now empty by default: a server that
  keeps open registration must set it explicitly.
- **Privacy page:** names the tile server of the Location Map and what it receives. The
  Content-Security-Policy allows images from that one host in addition.

### Fixed

- **Browse table:** at middle widths its columns no longer run into each other; the table keeps
  a minimum width for the columns shown and scrolls sideways inside its frame. The same for the
  admin Materials table.
- **Statistics:** one piece with a malformed size in the database can no longer make the
  statistics (and with them Analytics) fail for everyone.

### Security

- **Next.js 16.4.1:** the web app moves from Next.js 16.4.0 to 16.4.1, which fixes two critical
  advisories (GHSA-2464-fhr4-w9xw, code execution through the image optimizer with SVG files;
  GHSA-p3m5-59mp-jv5r, denial of service through Server Actions). The catalog was not reachable
  through either: it does not use the image optimizer and has no Server Actions. Upgraded as a
  precaution; `npm audit` is clean again.

### Server notes

- After the deploy, run `scripts/db_maintenance/backfill_geo_points.py --apply` once: it stores
  the location points the near search uses for the existing pieces (new and edited pieces get
  them on their own). Without `--apply` it only reports, and it exits with 4 while points are
  missing or out of date.
- After the deploy, run the map job once (`main_component_map.py`, or `--knn-only` for the
  similarity data alone): until it has run, similar pieces answer 409 and the card stays hidden.
  The similarity data is then rebuilt with the map on every scheduled run; a new or reshaped
  piece joins at the next run.

## [0.6.3.1] - 2026-10-21

A hardening release after 0.6.3.0.

### Changed

- **Viewer:** mesh edges stay crisp over the faces instead of breaking up at some angles; close
  zooms no longer cut a piece open, and small pieces open filling the view. A version switch
  while the mesh or the point cloud is Off loads nothing hidden.
- **Evidence:** a core record links to its paired rebound record; a piece with several
  reinforcement layouts shows all of them.
- **Geometry:** replacing the meshes or clouds of a draft also removes the files and markers
  of the dropped ones; a frame-only cache entry no longer carries descriptor data; the outline
  vertex limit counts holes.
- **Release tooling:** `invoke release-prep` sets the CHANGELOG date, writes `.zenodo.json` and
  runs the version checks in one step; `bump-version --gh` leaves the Session component alone
  when its client version already matches. The local launch entries and the old scripts work
  without a user path; the local server script is now `scripts/dev/serve_dump.py` (`invoke
  dev-local`; `invoke dev-migrated` still works and says so), migrating an old 0.5 dump only
  with `--migrate`; it writes `.dev/dev-local-credentials-<port>.txt` and `.dev/local-<port>.json`.

### Security

- **Failed access-token lookups are limited per address** (429 with `Retry-After`); valid tokens
  are never counted.
- **Token clean-up:** the tokens and connections of a deleted account are removed with it;
  revoked and expired tokens are deleted 90 days later.

### Server notes

- Existing token rows get their clean-up date from the daily user maintenance run (not while the
  read-only flag is set); no step needed.

## [0.6.3.0] - 2026-10-21

### Added

- **Access tokens** (decision 8.167): admins create personal access tokens in Settings (30 days,
  90 days or one year; shown once, stored only as a hash, at most 10 active), renew and revoke
  them; admins see and revoke every token on a new admin page. A token reads the catalog only
  where its scope allows; `GET /auth/token-check` tests one. The ground for the MCP layer and the
  Grasshopper device sign-in of this release.
- **Using CSC from Claude** (decision 8.168): an MCP endpoint at `https://<api host>/mcp` with
  nine read-only tools (search, components, versions, evidence, datasets, timeline, similar
  components). Add it as a custom connector in Claude; a browser window opens the consent
  page on the website, where an admin allows read access to the catalog as they see it in the
  web app. The connection renews itself for up to 90 days and can be revoked in the token
  list. Answers carry no e-mail addresses and mark everything that is not public.
- **Grasshopper signs in without a password** (decision 8.168): the Session component has a
  `SignIn` button (Windows). It opens the browser, you allow "Grasshopper on this computer" on
  the website, and the sign-in is stored for your Windows user (encrypted with DPAPI, one per
  server), outside every Grasshopper file. Later runs sign in by themselves and renew their
  token; `SignOut` ends the sign-in on the computer and the server. Each sign-in appears in the
  token list in Settings, where it can be revoked.

### Changed

- **Session component:** new inputs `SignIn` and `SignOut`; `Refresh` is gone, because the sign-in
  renews itself. Connected `Username` and `Password` still win and stay the way to sign in on
  macOS; with them the component signs in again by itself when its 6-hour token runs out.
  Update the components with `CSC_Update`.
- **Viewer:** a "Piece opacity" slider in the Overlay panel fades the mesh, proxy or point
  cloud so reinforcement and other overlays show through. The Mesh and Point cloud switches are
  labelled and have an "Off" choice instead of the "Show mesh" and "Show point cloud"
  checkboxes; "Show edges" moved to the overlays.

### Security

- **A password change or reset ends every access token of the account**: personal access
  tokens, Claude connections and Grasshopper sign-ins. Afterwards create a new token, allow
  Claude again and press `SignIn` again.

### Server notes

- `CSC_PAT_ROLES` (optional, default `admin`) names the roles that may create access tokens.
- The new collections `access_tokens`, `oauth_clients`, `oauth_requests`, `oauth_codes` and
  `oauth_used_refresh` need the same database rights as the others; their indexes are created
  at the start.
- Set `CSC_PUBLIC_API_URL=https://<api host>` (no path) in the backend environment: it turns on
  `/mcp` and the OAuth server and is the address the connector is given. It also becomes the
  base of the links in the JSON-LD export (if it was unset so far, those links took the request's own address).
  After the restart, check that `https://<api host>/.well-known/oauth-protected-resource/mcp`
  answers, then add the connector once in claude.ai.
- The deploy installs the MCP Python SDK (`mcp`) and its dependencies (`cryptography` among them).
- In read-only mode `/mcp` and the token renewal keep working; a code issued just before the
  switch can still be exchanged once. New consents are refused until the flag is gone.

## [0.6.2.1] - 2026-10-20

### Changed

- **Similarity Map**: the component map is now called "Similarity Map" in the navigation, on
  the page and in the admin logs, so it is not mistaken for a location map. Its address is
  `/components/similarity-map`; the old `/components/map` is not redirected.
- **Grasshopper sign-ins last 6 hours** (decision 8.166) instead of 30 minutes, so longer
  sessions no longer need the Refresh input; the web keeps 30 minutes.

### Server notes

- `CSC_GH_TOKEN_HOURS` (optional, 1 to 24, default 6) sets the lifetime of Grasshopper sign-ins;
  no change is needed for the default.

## [0.6.2.0] - 2026-10-18

A robustness release (decision 8.150): the structural security items deferred by 8.144,
the inline geometry budget and the follow-ups of the open-data imports. No new features.

### Changed

- **Inline geometry budget** (decision 8.148): a version keeps at most 1000 mesh faces and
  1000 points inline. A mesh of more than 1000 faces is reduced to 1000 for the inline
  preview and its original goes up as `detailed.ply` (the rule "up to 8000 faces fully
  inline" is gone); every point cloud of more than 1000 points goes up in full. Applies
  to the shared Grasshopper library `csc_gh` (through `CSC_Update`, no component change),
  the robot scan processing, the geometry correction script and the open-data imports.
  The backend still accepts larger inline geometry; existing versions stay as they are.
  The tooltip of `FetchReducedGeometry` still says "at most 5000 points" until the next
  export of the components.

- **Settings** (decision 8.156): the backend reads its environment in one place,
  `src/backend/settings.py` (pydantic-settings), and checks it at start: required
  variables, `JWT_SECRET` of at least 32 bytes, positive upload limits, http(s) URLs,
  the worker count and log level. Secrets never appear in a printed or logged settings
  object. Variable names and defaults are unchanged.
- **Logging** (decision 8.157): the backend logs through Python's `logging` instead of
  `print`, into gunicorn's daily error log (API) or the dated cron logs; errors keep their
  traceback. No line holds user names, e-mail addresses, typed values, GitHub request
  URLs or the text of a rejected document.
- **Database outages** answer 503 with `Retry-After` instead of a bare 500, and the
  cause goes to the log.
- **Backend modules split** (decision 8.160): the snapshot routes into five modules, the identity routes into
  three, the Grasshopper interface routes into a package; unused 0.5 API models removed. Paths and
  answers are unchanged (the OpenAPI document is identical).
- **Database outages** also answer 503 on the routes that handled database errors themselves; other
  database errors keep their answer. The client log no longer holds the text of a malformed client
  header, and the request line holds the path without the query string.
- **Import tools** retry a request up to three times on 503 and on connection errors,
  honouring `Retry-After`; every other error stops at once.

- **One way to load a record** (decision 8.158): identities, versions, evidence, datasets,
  invitations and materials are loaded and checked by one helper per kind, so every route
  answers alike. Changed answers (paths and schemas are unchanged):
  - a path id that is not a UUID answers 404 "<Kind> not found" instead of 400 "Invalid ... id";
    a UUID in a body or query value stays 400;
  - "not found" texts no longer repeat the id ("Snapshot not found");
  - the file routes of a purged version answer 410 with the purge notice instead of 404;
  - a component whose current version is missing answers 409 "The component has no current
    state." instead of 500 (passport, compose and the exports reading through them);
  - the change log and earlier versions answer 401 to anonymous callers and 403 "Not allowed:
    view_history" to non-members; an outsider no longer gets a withdrawn piece's tombstone
    from `/changes`;
  - a material that does not exist answers 404 before the admin check (403 before).
  An unknown invitation code still answers 400, the same as a code for another address.
- **Change log** (decision 8.159): evidence entries name their action (`verify`, `attach`,
  `redact`, `publish`, `withdraw`, `reinstate`) instead of `patch`; status steps stay in each
  record's status history. Entries carry the record's modification time and are written
  after it; a log entry that cannot be written no longer fails the request. Existing
  entries are unchanged.
- **File markers** (mesh levels, `point_cloud_files`) are updated atomically, so uploads to
  the same version at once no longer lose each other's marker.
- **`CSC_Update`** (decision 8.155): user objects are checked against a list of hashes from
  the server; unchanged files are skipped, each download is checked before it is written,
  and a failed file keeps the old one while the rest goes on ("Update incomplete, run
  again"). The result counts installed, unchanged and failed files. A replaced script
  component is no longer repaired automatically: it shows a remark that its inputs and
  outputs may have changed and that it needs a recompute.
- `FetchReducedGeometry` states the inline limit correctly (at most 1000 points).
- **Maintenance page**: `csc_maintenance.sh on` creates the domain's own document root
  (`/var/www/virtual/$USER/<domain>`) when it is missing and `off` removes it again; it no
  longer stops on a server whose only document root is `~/html`, and never writes there.

### Added

- **Marker for uploaded point clouds**: a snapshot lists the indices of its uploaded full
  point clouds in `point_cloud_files` (set by the upload, removed by the delete, not
  writable by clients), so an import resumes without probing the file.
- **Read-only mode for maintenance** (decision 8.154): while the file `~/csc/shared/READ_ONLY`
  exists, the backend answers every write with 503 and `Retry-After`; reads and the sign-in
  stay up. All workers switch at once, without a restart. The web shows a banner and
  disables its write buttons, `/version` and `/health/db` report `read_only`, and the
  geometry runner, the component map, the user and the geometry maintenance skip their run.

### Security

- **Tokens** are read with PyJWT instead of python-jose: `HS256` only, `exp` and `sub`
  required, one verification per request. Tokens issued before the update stay valid.
- **Shared rate limits** (decision 8.152): sign-in, registration, verification mails, password
  reset and invitations count in the database, across all workers and restarts. The read
  limits (lists, map, downloads, exports) count per worker; they only shed load.
- **Failed sign-ins** (decision 8.162): at most 10 in 15 minutes per account, then 429 with
  `Retry-After`; an unknown account is answered the same way, and the counter holds no user
  name or address.
- **Request size** (decision 8.163): a body over its limit is refused with 413 before it is
  read (uploads by their upload limit, everything else 16 MB, `CSC_JSON_BODY_LIMIT_MB`).
- **Usernames** (decision 8.161): 3 to 32 characters, lowercase letters, digits, `.`, `_`, `-`,
  starting with a letter or digit. Every existing name already fits.
- **Release attestations** (decision 8.153): every release asset carries a GitHub build
  attestation, and the deploy checks the backend and the frontend bundle against it
  before it unpacks them; it stops if the check fails or `gh` is missing.
- In read-only mode the sign-in writes nothing; its per-address limit then counts in each
  worker's memory, and an existing account lock still holds.
- Database connections are capped at 20 per client; a one-off dataset update no longer
  runs at every start.
- **Content-Security-Policy** (decision 8.164): every page carries a policy built per
  request with a fresh nonce. Scripts run only by nonce, styles inline, everything else
  from the app's own origin; the exceptions are the Google map frame and images from the
  static host. The policy is enforced at once.

### Server notes

- `JWT_ALGORITHM`, if set, must be `HS256`; any other value stops the start.
- The database user needs `createIndex`, `insert`, `update` and `remove` on the new collection
  `rate_limit_counters` (its TTL index is created on first use). `CSC_RATE_LIMIT_STORAGE`
  (default: the MongoDB URI) selects the store of the shared limits.
- The read limits count per worker: the effective limit is the stated one times `CSC_WORKERS`.
- The deploy installs PyJWT and removes python-jose.
- Before the deploy, check the backend environment: `FRONTEND_URL`, `GITHUB_REPO_URL`
  and `CSC_PUBLIC_API_URL` must be http(s) URLs, the upload and photo limit variables
  positive, and `SMTP_DEV_MODE` off. The backend refuses to start otherwise and names
  the variable.
- The deploy installs one new package, `pydantic-settings`.
- `CSC_CSP_REPORT_ONLY=1` in the frontend `.env` is the emergency switch for the
  Content-Security-Policy: the same policy is then sent as report-only (violations are
  logged in the browser console, nothing is blocked). Restart the frontend after setting
  it, and remove it once the cause is fixed.
- Before the first deploy of 0.6.2.0, install the `gh` CLI binary in `~/bin` and store a
  token for it (deployment README). The 0.6.1.1 deploy script runs first and repeats
  itself with the new one, which needs `gh`.
- Put `touch ~/csc/shared/READ_ONLY` before and `rm ~/csc/shared/READ_ONLY` after every
  maintenance step (restore, purge, migration, deploy). The path is set by
  `CSC_READ_ONLY_FLAG`.
- Deploy the server before anyone runs the new `CSC_Update`: it needs
  `/ghinterface/userobject_manifest` and stops with a 404 against an older server. The old
  `CSC_Update` still updates itself through the old endpoints.
- `NEXT_PUBLIC_STATIC_BASE_URL` is fixed when the frontend is built (in CI): set it there,
  or set `NEXT_STATIC_BASE_URL` in the frontend environment, which is read at run time.
  Otherwise the policy blocks the images from the static host (the sidebar logo).

## [0.6.1.1] - 2026-10-13

A security patch (decision 8.144), from a read-only review of 0.6.1.0 in five areas:
backend authentication, injection and uploads, authorisation, infrastructure and
CI, and the frontend. The review found nothing critical or high; this release takes
the small fixes. The larger structural items (one load-and-authorise helper, a
shared rate-limit store, a Content-Security-Policy with nonces, signed checksums,
PyJWT, the module splits) go to 0.6.2. No change to the Grasshopper components and
no migration of records.

### Security

- **One sign-in verifier**: the web sign-in sends the credentials to `POST /auth/token`
and nowhere else, so the backend's rate limit sees every attempt. The frontend has
no database access any more (`mongodb`, `bcryptjs`, `lib/mongodb.ts` and the
`MONGODB_*` variables are gone), and its log line holds the outcome only, never
what was typed.
- **Headers**: the web app sends `frame-ancestors 'none'` with `X-Frame-Options:
DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
`X-Content-Type-Options: nosniff` and, on the canonical host only, HSTS (no
`includeSubDomains`).
- **Server-side calls** from the Browse, component and `/id` pages go to
`FASTAPI_URL` with the session's token, not to a base built from the request's Host
header.
- **Invitations**: in a dataset an admin has not reviewed yet, a moderator invites
only. `POST /invitations` and `POST /datasets/{did}/members` answer `invited` for
every address and send the same mail, so neither route tells whether an address has
an account. An existing account joins by opening the link in the mail signed in with
that address and accepting (`/invite`, `POST /invitations/accept`); a new address
registers with the code as before. Admins and moderators of a reviewed dataset keep
the direct add. At most 50 invitation mails per user per day (new, resent and
member-by-email; admins exempt), counted in the database, answered with 429. Member
e-mail addresses are shown to admins and to moderators of a reviewed dataset only.
Resend needs the caller's current `invite` permission, not the creation of the
invitation.
- **Logs hold no people**: no user names, e-mail addresses or typed identifiers in
the cron jobs, the web sign-in or the member notices; mail errors are logged by
kind. Every site log keeps 14 days, so the privacy page holds as written.
- **Error answers** carry no file path, stored document or driver message: a 500 has
one text, `/health/db` answers `{"ok": false}` with 503, and the cause goes to the
log. Validation messages meant for the client (422) stay.
- **Sign-in details**: a sign-in with an unknown identifier takes the same password
check as a real one; the verification token is stored as a SHA-256 hash (a link
mailed before the deploy works until it expires, at most 24 hours); the resend route
takes a typed body, always gives the same answer, sends in the background and sends
at most three mails an hour per address; a second registration for the same address
meets the unique index and answers 409; a `JWT_SECRET` under 32 bytes stops the
backend from starting; a token is looked up by its subject only.
- **Uploads**: photos are sniffed by their first bytes and decoded as JPEG, PNG or
WebP only, with a 40 megapixel cap checked before any pixel is decoded (also for
evidence images); meshes are loaded without their materials; the catalogue filters
`original_function`, `material` and `dataset` match their text exactly and have a
length cap.
- **Blocking work off the event loop**: OBJ conversion, mesh exports and photo
decoding run in worker threads; the mesh downloads are rate limited (120 a minute per
user or address) and OBJ conversion is refused for files above 50 MB.
- **Proxies**: gunicorn trusts the same proxies as the rate limiter
(`CSC_TRUSTED_PROXIES`); the PDF and CERO ETags hold the bases of their links, so a
request for another host is never served a document cached for this one.
- **Anonymous dataset list** shows a dataset by the same rule as its count:
published, not withdrawn, public.
- **CI**: every action is pinned to a commit (Dependabot proposes updates weekly);
the release workflow writes to the repository in its publish job only.

### Changed

- The invitation mail links to `/invite?code=...` for every recipient; a new page
shows what the invitation offers and takes the acceptance.
- The privacy page says that the sign-in cookie lasts at most 24 hours, that
accounts are deleted on request and that location data is removed from photos.
- The cron jobs write one dated log a day (`<job>_cronjob.<date>.log`) and one daily
line deletes the cron and deploy logs older than 14 days; the geometry runner and
the component map share a lock in `~/csc/shared/locks/heavy.lock` instead of
`/tmp`. The deploy gate writes `deploy.<date>.log`.
- `usermaintenance.py` also removes accounts whose verification expiry is stored as
text, and uses the configured database name.
- Pinned in `constraints.txt`: `fastapi`, `starlette`, `uvicorn`, `gunicorn` and
`reportlab`, to the versions the backend is tested with; `trimesh>=5`.

### Server notes

- Check the production `JWT_SECRET` first: it must be at least 32 bytes
(`openssl rand -hex 32` gives 64). The backend refuses to start with a shorter one.
Locally, put a longer `JWT_SECRET` into `src/backend/dev.env` (the example has one).
- `mkdir -p ~/csc/shared/locks`, then paste the new `crontab.example`; after its
first runs delete the old undated `~/csc/shared/logs/*_cronjob.log` files.
- The frontend `.env` loses `MONGODB_URI`, `MONGODB_DB` and `MONGODB_USERCOLLECTION`
(harmless if left).
- If `CSC_TRUSTED_PROXIES` is set, gunicorn now reads it too: check that every entry
is an address or a network (a typo stops the start with its name).
- The deploy builds a new venv (`trimesh>=5`, new pins).
- In the GitHub settings: let the `production` environment require a reviewer and
protect the tags `v*`.
- Nobody is signed out by this release, unless `JWT_SECRET` is changed.


## [0.6.1.0] - 2026-10-12

The first feature release after the cutover (decisions 8.129 to 8.143): a personal
profile, datasets that users create and run themselves, revised evidence forms, a
swimlane history with export, reinforcement read and written from Grasshopper,
designed mails, a privacy page, and a cleaner frontend toolchain. Phase A (the
operations part) already shipped as 0.6.0.4. No migration of existing records is
needed; one optional maintenance script normalises old reinforcement layouts.

### Added

- **Profile** (8.133): organisation, ROR id, ORCID (checksum checked), default role and
full name in Settings. "I performed this" copies them into an evidence record; the
server fills empty fields of a signed-in actor from the profile at write time (a
later profile change never rewrites old records). Redaction also blanks the profile.
- **User-created datasets** (8.139): every verified account may create up to
`CSC_MAX_DATASETS_PER_USER` (default 3) datasets and moderates them ("Your datasets"
in My work, "New dataset"). A new dataset is members-only and unreviewed: until an
admin marks it reviewed it cannot become catalogue-wide and its pieces cannot be made
public. Only empty datasets can be deleted; the last moderator cannot be removed.
Admins get a mail when a dataset is created.
- **Swimlane history** (8.140): the History card shows one lane per piece (parents
above, children below, cut and assemble links, evidence grouped per day and method)
on the new `GET /identities/{id}/history`; the whole timeline exports as SVG, PNG and
JSON.
- **Compact preview and id chips** (8.141): one side panel for Browse and the map
(rotate and zoom, step through rows); snapshot and record ids to see and copy, also
as a Grasshopper panel; `?snapshot=<id>` opens that version.
- **Grasshopper** (8.133 f, RL6, RL9, RL11): `Actor` has a `Me` input that builds the
signed-in user's actor from the profile; `ReinforcementLayout` takes the drawing's
link and retrieval date and a `ComponentPassport`, whose placement maps bars back to
stored coordinates; the new `FetchReinforcementLayout` reads layouts back (one branch
per layout, placed like the fetched mesh). Document units are used 1:1 as
millimetres, with a warning in other units. The release bundle carries
`DDU_CSC_GrasshopperInterface_0.6.1.0.gh`.
- **Mail templates** (8.138 e): the five mails as Jinja2 templates (HTML and text) in
the site's colours, without images; an admin page previews every mail and sends a
test to the admin's own address.
- **Privacy page** `/privacy`, linked from the footer, the account menu, the
registration and the mails; the imprint names the person responsible.
- Reinforcement bar colours in the viewer by layout or by diameter, with a legend.
- Corrections of evidence records carry their attachments over (keep or remove);
empty document fields of a published reinforcement layout can be filled once (8.142).
- `scripts/db_maintenance/layout_position_none.py` (stored `region` layouts to
`none`), `purge_datasets.py` (an escape hatch that removes datasets' components
without a trace), and `.zenodo.json`, generated per release (`invoke zenodo`).

### Changed

- **Evidence forms** (8.134): numbered sections with an outline, grouped method choice
with search, records as a compact table, foldable bars with bulk edits, a check
before saving; one shared date field with typing, month and year menus and a year
grid (8.143).
- Edge distance for picked points is measured against the proxy, so bumps in a scan
no longer trigger the warning (8.135).
- Provenance edits include the performers (with "Add me"), method and notes;
organisations may carry a link.
- Anonymous visitors no longer receive the accuracy note of reinforcement layouts;
the JSON-LD and the PDF passport carry the photo credit.
- The site's own logs rotate daily and are deleted after 14 days.
- Frontend: Next.js 16.4.0, lint packages 16.4 with no errors, no production audit
findings; images are served unoptimised and `sharp` is no longer bundled (its
binaries need a newer glibc than the server has).
- Credits: the DBU and BMBF funding logos and current links.

### Removed

- The HKS curve on the component page and HKS as a component-map basis are hidden
(the pooled descriptor carries little meaning; a revised HKS is planned for 0.6.2).
- The ELK lineage graph (replaced by the swimlane), the unused `bcrypt` package.

### Server notes

- New Python dependency (`jinja2`): the deploy builds a new venv. This is the first
deploy that re-runs itself with the release's own deploy script.
- Optional: `CSC_MAX_DATASETS_PER_USER` in `fastapi.ini` (default 3).
- Run `layout_position_none.py` once (dry run first) to convert old layouts.
- After the first midnight, check that `fastapi.log` rotated; send a test mail from
Admin > Mail templates and look at it in the usual mail clients.
- Grasshopper users: run `CSC_Update` (library `csc_gh` 261012) for the new and
changed components.

## [0.6.0.4] - 2026-10-10

An operations release (phase A of 0.6.1.0, decisions 8.136 and 8.137): less load
on the database, the geometry cron that checks only what changed, a deploy that
uses its own new script, and a maintenance page for cutovers. No change to the
web interface or the Grasshopper components.

### Changed

- **Geometry runner** (8.136): every write that changes a geometry input (a new
version or correction, a file upload, a geometry, colour or override edit, a
changed original function) marks the snapshot (`derivation_due`); `--due`
derives only marked snapshots and clears the mark only if no newer write came
in. The runner loads identities in batches instead of one request per snapshot.
- **Lists, map and counts** read only the snapshot fields a row needs; the full
snapshot is joined only for the rows of the requested page. Browse and the
catalogue lists move far less data out of the database.
- **Crontab** (`uberspaceconfig/crontab/crontab.example`): the geometry runner
every 20 minutes with `--due --limit 10`, a nightly full check at 3:30 with
`--sweep`, the component map once a day at 4:15; all share one lock.
- **Deploy**: a release whose deploy script differs from the installed one
installs it and runs again with it (once), so a fix to the deploy script works
in the same release. This release is still deployed by the 0.6.0.3 script; the
re-run applies from the next release on.
- `constraints.txt` pins `numba`, `llvmlite`, `pynndescent` and `umap-learn` to
the versions the server runs.

### Added

- **Maintenance mode** (8.137): `csc_maintenance.sh on | off | status` (with
`--dry-run`) switches the web domain to a static page that answers 503 while the
frontend is down, and back; the text comes from `~/csc/shared/maintenance.txt`
when present. See `uberspaceconfig/deployment/README.md`.
- `scripts/db_maintenance/copy_provenance_capture.py`: copies the provenance and
v0 capture details of one component to the others of a dataset through the API.

### Server notes

- Replace the crontab with `crontab.example` (set `MAILTO` or comment it out).
- Existing snapshots carry no mark after the deploy: the nightly run catches
earlier changes, or run `main_geometry.py --limit 200` once.
- Before relying on `csc_maintenance.sh on`, check on a test subdomain that
Apache serves the domain's own folder.

## [0.6.0.3] - 2026-10-10

A small interface release: the dark theme and the light / dark switch. No change
to the backend, the data model or the Grasshopper components.

### Changed

- **Dark theme**: blue-gray neutrals after GitHub's dark default (canvas
`#0d1117`, cards, menus and the sidebar `#151b23`, borders `#3d444d`, text
`#e6edf3`) instead of black; the DDU blue and magenta accents stay as they were.

### Added

- A light / dark switch in the top bar (sun / moon), one click away again; the
account menu and Settings keep the choice "System".

## [0.6.0.2] - 2026-10-10

An operations release (decisions 8.129 to 8.131): the frontend bundle, the
server's memory, the deploy, and a public switch in the web. No change to the
data model, the migration or the Grasshopper components.

### Added

- **Public switch** (8.131): "Edit details" has a "Public" switch for whoever
may edit the piece's metadata (a moderator of the dataset; the creator while it
is unpublished). Switching to public asks first and says what visitors without
an account then see; switching to private does not. A moderator of a dataset
can make all its published pieces public or private at once from the dataset
page, with the number they affect (`POST /datasets/{did}/public`, with
`dry_run`); every change is logged like a metadata edit, unpublished and
withdrawn pieces are left alone, and children never follow their parents.
- `crontab.example` in `uberspaceconfig/crontab/`: the complete production
crontab (geometry runner, component map, user and geometry maintenance), with
one `MAILTO` line for the maintainer.
- `CSC_WORKERS` (default 2) and `CSC_LOG_LEVEL` (default `info`) in
`fastapi.ini` set the gunicorn workers and the log level; a deploy no longer
resets them.

### Changed

- The geometry runner and the component map cron share one lock,
`/tmp/csc_heavy.lock`, so the two heavy jobs never run together: the runner
skips a run while it is held, the map waits up to 15 minutes.
- The deploy installs the backend with binary wheels only
(`--only-binary=:all:`) and `shapely` is capped at 2.1.2 (2.2.0 needs a newer
glibc than the server has): a missing wheel fails the deploy at once instead of
compiling on the server.
- The "Not public" notice on the component page says who sees the piece: every
signed-in user in a catalog dataset, only the members and the moderators in a
members dataset.
- The viewer of a piece without a scan says "No scan: overlays need a mesh or
point cloud." instead of an empty overlay menu.
- `migrate_06.py --dry-run` is documented to check the steps independently
(`--all --dry-run` stops at step 10); only the rehearsal checks the whole chain.

### Fixed

- The frontend release bundle nested `public/` as `public/public/` since
0.6.0.0, so the logo and the background meshes answered 404 in production. The
packaging copies the contents of `public/` now and fails when the logo is
missing or `public/public` exists.
- Several gunicorn workers starting together on an empty `materials`
collection hit a duplicate-key error and gunicorn stopped; seeding skips
duplicate keys now (and only those).

### Server notes

- Set `CSC_WORKERS="2"` and `CSC_LOG_LEVEL="info"` in `~/etc/services.d/fastapi.ini`
(`fastapi.ini.example`) and restart the service.
- Replace the crontab with `uberspaceconfig/crontab/crontab.example`
(`crontab -e`, put the maintainer's address in the `MAILTO` line).

## [0.6.0.1] - 2026-10-09

### Fixed

- The component map cron (`main_component_map.py`) and every other list of
identities without a page size failed on MongoDB Atlas' free tier with
`QueryExceededMemoryLimitNoDiskUseAllowed` (a blocking sort is capped at
32 MB there and `allowDiskUse` is ignored): the list sorted whole joined
documents, with the inline meshes of the external catalogue pieces. A sort on
an identity field now runs before the join, on the small identity documents;
a sort on a snapshot field without a limit sorts slim states and joins the
whole ones afterwards. The rows and their order are unchanged.
- The links of the JSON-LD export (`@context`) and the PDF passport named the
API with `http://` behind the Uberspace proxy. The optional
`CSC_PUBLIC_API_URL` (for example `https://api.2ndchances.build`) now sets the
address they use; unset, they use the request's own as before.

## [0.6.0.0] - 2026-10-09

The 0.6 data model: datasets and permissions, a moderated lifecycle for every
record, provenance and lineage, server-side geometry, an evidence system for
material properties, exports, a revised web interface and a rebuilt Grasshopper
bridge. The design is recorded in `docs/adr/` (`DATA_MODEL_SPEC.md`, decisions
up to 8.125 in `DESIGN_DECISIONS.md`, the phase plan in
`IMPLEMENTATION_PLAN_0.6.md`); the glossary is `CONTEXT.md`.

**Breaking.** The database is migrated once at the cutover (spec section 8,
`scripts/db_maintenance/migrate_06.py`); 0.5 clients are refused with 426
(`CSC_MIN_CLIENT_VERSIONS`), so Grasshopper users run `CSC_Update` (twice: the
0.5 updater installs the 0.6 UserObjects, the new one the `csc_gh` library) and
restart Rhino.

### Added

- **Datasets and memberships** with the roles contributor, reviewer and
moderator per dataset; visibility `members` (default) or `catalog`; public
pieces (`is_public`) for anonymous readers, who never see people (public tier).
Invitations bound to one address, the member editor by email, the admin user
list with filters.
- **Lifecycle for snapshots and evidence**: draft, pending, published,
rejected, withdrawn; recall, reinstate, purge with a 410 stub. Nobody publishes
directly: submitting moves a record to the moderation queue for every role, and
a moderator may publish their own record from the queue. Published claims are
frozen; a correction is a new record that supersedes the old one and keeps its
place in the version order. An empty capture field can be filled once.
- **Submit and edit in the web**: My work submits own drafts, snapshots and
evidence together (a refusal does not stop the others); a draft of evidence, or
for a moderator a pending one, is edited in the evidence form.
- **Change history** (`/changes`, `?as_of=`) for every record.
- **Provenance and lineage**: origin (incl. planned and in-place pieces with
deinstallation), exit and earlier cycles, cuts and merges with inherited fields,
DIN SPEC 91484 / DGNB fields, a managed `materials` list with waste-code
classes, batches with draws and the remaining quantity.
- **Geometry runner** (`main_geometry.py`): canonical frame, shape class,
fitted proxies (box, planar / linear prism, cylinder, hull) with deviation
maps, descriptors incl. heat kernel signatures, complexity and previews; stage
stamps make every result reproducible and stale on change. It also runs on
another machine (`--remote`), with a result cache (`--cache-dir`).
- **Evidence** (`component_evidence`): rebound hammer, cores, visual
inspection, reinforcement layout, documents and further methods, positioned on
the piece; verification with four eyes; attachments; a properties card folded
from all published evidence; one timeline for versions, cycles and evidence.
- **Exports**: component passport as JSON-LD (`compose?format=jsonld`,
`/context/v1.jsonld`), CERO for concrete and aerated concrete pieces and a PDF passport.
- **Web**: new component, cut, record new state and correct in one form; scan
path for unknown tags; component page with History (list / graph), Actions
menu and evidence; Browse as cards or table; My work; moderation tabs; the
component map coloured by shape class, dataset, material or circulation;
analytics; a generated reference of every Grasshopper component on the GH page.
- **Grasshopper**: shared library `csc_gh` installed by `CSC_Update`, declared
outputs, builders for actor, origin, metadata and capture, reinforcement
layout and generic evidence, bake to and sync with the Rhino document, D2P
bridge. Everything written from Grasshopper lands as a draft; completing and
submitting it happens in the web (My work).
- **Accounts**: password reset by mail; a password change signs out every other
session. Failed invitation mails are shown with Resend.
- `invoke rehearse`, `invoke dev-migrated`, `invoke test-changed / test-all /
test-release`, `check_invariants.py`.

### Changed

- Snapshot files (previews, photos, meshes, point clouds, proxies, capture
fixtures) are served only through the checked API routes; on the server they
move out of the web root (`~/csc_assets_private/`).
- Mails: one template with the `[CSC]` subject prefix, a `Reply-To` of the
acting moderator for invitations and member notices, sent off the event loop.
- Rate limits are keyed per token or per trusted client address
(`CSC_TRUSTED_PROXIES`, `CSC_PROXY_HOPS`).
- CI runs the API, frontend and deployment checks; the full suite runs locally
(`invoke test-all`, decision 8.114).

### Removed

- Designs (archived at the cutover), the 0.5 snapshot fields (`type`,
`extrusions`, `condition`, `validated`, `pca_frame`, ...), the 0.5 add-component
wizard, the orientation utility route and the separate descriptor and preview
cron jobs.
- `API_SECRET` in the frontend environment (never read); `NEXTAUTH_SECRET` is
independent of the backend's `JWT_SECRET`.


## [0.5.1.0] - 2026-09-28

Pre-work for the 0.6 data model: runtime, releases and deployment, client
identification, privacy, and a local test environment. No data-model change.

From this release on, backend, web frontend and Grasshopper interface share
**one version** and are released together as tag `v<version>`, built, released
and deployed by GitHub Actions (README, "Releases and deployment").

### Changed

- **One product version** in the `VERSION` file (`invoke bump-version`); CI
checks that backend, frontend and README agree. The per-component
`frontend-*` and `gh-interface-*` releases end; a release now carries
`csc-backend-<v>.tar.gz`, `csc-frontend-<v>.zip`, `csc-gh-interface-<v>.zip`
and `SHA256SUMS`.
- **Deployment**: tag push --> CI --> GitHub Release --> deploy after approval
(environment `production`). On Uberspace, releases unpack into
`~/csc/releases/<version>/`, `~/csc/current` points at the active one, venvs
are reused while requirements do not change, and a failed health check rolls
back automatically (`uberspaceconfig/deployment/csc_release_deploy.sh`).
Services and cron jobs run from `~/csc/current`; logs and frontend secrets
live in `~/csc/shared`.
- **Grasshopper updates follow the server**: `CSC_Update` and the interface
download use the GitHub release of the running backend instead of the `main`
branch, so merging to main no longer publishes UserObjects (`CSC_Update`
260928; `UPDATE_CHANNEL` is now empty by default and only for testers).
- The GH XML exports ship inside the backend release (`static/ghxml`); the
`ghxml_sync` cron job is no longer needed.
- Backend runs on **Python 3.13** (was 3.9, end of life). `src/backend/constraints.txt`
caps numpy, scipy, scikit-learn, robust-laplacian, pillow and contourpy at the
last releases with wheels for Uberspace 7 (glibc 2.17); `invoke check-server-wheels` verifies it.
- Passwords are hashed with `bcrypt` directly; passlib (unmaintained) fails on
bcrypt 5. Existing hashes stay valid. New passwords are limited to 72 bytes
in UTF-8 (was 72 characters).
- Snapshot photos keep only orientation, capture time and camera make / model
in their EXIF; GPS position, owner and serial numbers are removed on upload.
- The backend creates the `catalog_number` counter on startup if it is missing
(fresh or seeded databases); an existing counter is never touched.
- Frontend: Next.js 16.3.4 --> 16.3.6 (patch; with `eslint-config-next` and
`@next/eslint-plugin-next`); lint errors fixed so CI can enforce lint.



### Added

- `GET /version` (public): the backend's CSC version and release tag.
- `X-CSC-Client: <client>/<version>` header sent by the web frontend
(`web/0.5.1.0`) and the Grasshopper UserObjects (`gh-userobjects/0.5.1.0`,
`CSC_Session` 260928); the backend logs every request's client to
`logs/client_versions.log` (logging only --- 0.6 will reject outdated clients).
- CI (`.github/workflows/ci.yml`): backend tests on a MongoDB container, server
wheel check, deploy-script end-to-end test, frontend type check / lint /
build, Grasshopper source checks (changed components need a version bump and
a re-exported `.ghuser` / XML).
- `scripts/db_maintenance/migrate_strip_photo_gps.py`: removes the same metadata
from already stored photos without re-encoding them.
- Local development and tests (README): route tests against a throwaway
`mongod`, `invoke test | dev-backend | seed | create-user`, `dev.env.example`,
`.env.development.local.example`, `requirements-dev.txt`, an opt-in smoke test
against a local catalog dump.



### Removed

- The old deploy scripts (`csc_deploy*.sh`), the server-side frontend build
configs and the `frontend-standalone-release` / `grasshopper-folder-release`
workflows --- replaced by the release workflow and `csc_release_deploy.sh`.



### Fixed

- The Grasshopper interface download (web page, `/ghinterface/download`) and
`/ghinterface/version` handed out the newest release of the whole repository
--- a frontend bundle since `frontend-0.5.0.0-beta-1`. They now use the
interface asset of the backend's own release.
- `email-validator` was missing from `requirements.txt` although the user
models need it; a fresh server venv would not have started.
- `networkx` was missing from `requirements.txt` although trimesh needs it for
mesh sections; in a fresh venv the radial signature descriptors failed (found
by the new CI, which installs only the declared requirements).



## [Unreleased] - 2026-06-10



### Individual Versions

- CSC FastAPI Backend:  0.5.0.0
- CSC React Frontend:   0.5.0.0
- CSC Grasshopper Interface: 0.5.0.0



### Added



#### CSC FastAPI Backend

- Identity/snapshot catalog: `component_identities` + versioned `component_snapshots`; passport and CRUD per identity/snapshot
- Inline reinforcement bars: `geometry.reinforcements[]` (`{spec, diameter, points}`)
- Snapshot point-cloud PLY upload routes and photo slot routes
- `POST /utility/compute-snapshot-orientation` (PCA frame from box geometry)
- Public components: `is_public` flag; optional-auth read for all snapshots when public (`migrate_add_is_public_field.py`)
- Admin users API: `GET /users`, `PATCH /users/{user_id}`
- `/ghinterface/` router: version, download, src, xml, userobject
- Snapshot delete route; ETag on all-identities list
- Radial signature applies to every component type, not just extrusion
panels. Outlines are taken from the highest-resolution geometry available,
in order mesh (`detailed.ply` > `reduced.ply` > inline) > point cloud
(`0.ply` > inline preview) > extrusion profile. Meshes and clouds are
sectioned through the PCA centre plane; panels still rest-align the
resulting silhouette
- `GET /identities/map`: 2D component map from descriptors (PCA first paint,
UMAP preferred). Bases: concatenated radial-signature distances, or
concatenated scalar scores (box/sphere/line/planescore). Components
missing the chosen basis are omitted; response reports displayed/total
coverage. Default scope layouts are served from `component_map_cache`
(`source=auto|cache|live`); UMAP is precomputed by cron
- `main_component_map.py`: cron/worker that writes PCA+UMAP layouts into
`component_map_cache` for the Component Map page
- `main_descriptors_simple.py --recompute` walks every snapshot one at a
time and overwrites every applicable descriptor (optional `--limit N`)
- `/ghinterface/src*` and `/ghinterface/userobject*` accept a `channel`
query param (GitHub branch; default `main`) so `CSC_Update` can follow
a hardcoded `UPDATE_CHANNEL`
- `/ghinterface/` source/UserObject fetches use `/git/blobs` when a GitHub
token is set, and `download_url` (raw) without one, with fallback between
the two. 503s now include the underlying GitHub error (timeout, connect,
HTTP status) instead of a generic "service unavailable"
- GH XML sync clones the public repo without a GitHub token
- `GITHUB_CSC_GH_TOKEN` is optional (higher GitHub API rate limits only);
FastAPI starts and `/ghinterface/` works against the public repo without it



#### CSC React Frontend

- Add Component Wizard (identity + snapshot creation; orientation on submit)
- Multi-snapshot detail/history UI; updated admin validation queue
- Admin user management at `/admin/users`
- Public component viewing without login; `is_public` toggle on edit page
- Reinforcement visualization in component viewer
- Component Map at `/components/map` (nav under Browse Components): loads
cached UMAP/PCA layouts from `GET /identities/map`, with pan/zoom canvas
and displayed/total coverage messaging
- GH interface docs: `ListIdentitySnapshots`, `FetchAllSnapshots`, `FetchSnapshot`, `CreateReinforcement`, `PassportToD2P`



#### CSC Grasshopper Interface

- Identity/snapshot components: `CreateComponentIdentity`, `CreateComponentSnapshot`, `AddComponentIdentity`, `AddComponentSnapshot`
- `CSC_ListIdentitySnapshots`, `CSC_FetchAllSnapshots`, `CSC_FetchSnapshot`
- `CSC_CreateReinforcement`; reinforcement inputs on create/add; pipe baking in `CSC_BakeComponents`
- Session identity/snapshot catalog cache (v0.5)
- `CSC_Update`: hardcoded `UPDATE_CHANNEL` (default `main`) selects the
GitHub branch to pull sources and UserObjects from; the name must match
the remote branch exactly



### Changed



#### CSC FastAPI Backend

- Descriptors, previewgen, and geometry maintenance use snapshot model
- Designs schema aligned with identity references
- Radial signature outline extraction prefers on-disk `detailed.ply` (then
`reduced.ply`) over the inline mesh, and the full point-cloud PLY over the
inline preview. An extrusion profile is only used when no mesh or cloud
is available
- The `{identity, snapshots[]}` read model is now called a **passport**:
`ComposeIdentityResponse` --> `ComponentPassport`. The route paths
`GET /identities/{id}/compose` and `GET /schema/catalog-compose` are
unchanged, so released UserObjects keep working



#### CSC React Frontend

- Catalog UI adapted to identity/snapshot passport spec
- Design detail actions use client session; proxy allows anonymous public GETs
- Sidebar layout compacter; Next.js/npm updated
- Generated type `ComposeIdentityResponse` --> `ComponentPassport`; the GH
interface docs say "passport" instead of "compose JSON" throughout



#### CSC Grasshopper Interface

- Fetch/create components updated for identity/snapshot API
- `CSC_Update` uses `/ghinterface/` paths
- "Compose JSON" is now a **passport** everywhere in the interface:
`ComposeToD2P` --> `PassportToD2P`, the `FetchAllSnapshots` / `FetchSnapshot`
output pin `ComposeData` --> `Passport`, and the `CSC_Session` helpers
(`cached_get_compose` --> `cached_get_passport`, `compose_json_string` -->
`passport_json_string`). All UserObjects must be updated together



#### Documentation & Deployment

- README refreshed for 0.5; deploy scripts (`csc_deploy_*_v05.sh`); descriptor cron `--dry-run`



### Removed



#### CSC FastAPI Backend

- Legacy monolithic component routes/models
- `downloads` and `ghupdates` routers (--> `/ghinterface/`)



#### CSC Grasshopper Interface

- Legacy usrobject sources for dropped components



### Fixed



#### CSC FastAPI Backend

- Radial signature mesh sectioning no longer fails on open scanned surfaces
(e.g. rubble `detailed.ply`) whose faces are coplanar with the PCA centre
plane: the vertex silhouette is used when that single cut misses. Offset
and percentile cut heights are not retried, so outlines stay comparable
across PCA-aligned geometry
- Open-mesh centre-plane cuts (gappy or not-star-convex loops, e.g.
Scanned Rubble 30) wrap the intersection points in a convex hull so
every radial ray hits; a watertight simple section that already contains
its centroid is kept
- Version detection only accepts real declarations (`Version: <number>`), so
prose like "version-0 snapshot" in a component description no longer parses
as version `0` (affected `CSC_AddComponentIdentity`)
- `/ghinterface/src_names` reads source files concurrently and caches parsed
versions per blob sha instead of fetching every file serially on each call
- `/ghinterface/` routes reuse a short-lived directory listing cache, so an
`CSC_Update` install run no longer re-lists the repo once per file



#### CSC React Frontend

- GH interface cards used the wrong Grasshopper names `FetchComposeAllSnapshots` /
`FetchComposeSnapshot` (and output pin `ComposeJSON`); they now match
`FetchAllSnapshots` / `FetchSnapshot` with `Passport`, including screenshots



#### CSC Grasshopper Interface

- `CSC_Update` and `CSC_ExportScriptsAndSource`: same version-declaration fix
as the backend, so all three parsers agree on a component's version
- `CSC_Update`: source files without a parseable version are skipped instead
of aborting the whole update check
- `CSC_Update`: components with no source on the server (renamed or removed,
e.g. `CreateComponent`) are now reported as a warning instead of being
skipped silently while the UserObjects update anyway
- `CSC_Update`: longer request timeouts for source/UserObject downloads



## [0.4.7.0] - 2026-04-30



### Versions

- CSC FastAPI Backend:  0.4.7.0
- CSC React Frontend:   0.4.7.0
- CSC Grasshopper Interface: 0.4.5.6



### Changed



#### CSC FastAPI Backend

- **Sorting enhancements for component lists**: Added support for additional sort keys (`name`, `bbx.0`, `bbx.1`, `bbx.2`) and introduced `sortorder=asc|desc` handling for both regular and archived shallow component listing endpoints. Added archive-side sort key validation against the shared allowed-key list.



#### CSC React Frontend

- **Browse/archive table sorting UX**: Implemented clickable table-header sorting with URL-synced `sortkey` + `sortorder`, active sort indicators, per-column toggle between ascending/descending, and explicit reset-sort control.
- **Filter panel improvements**: Renamed filter section to **Filters & Settings**, added page-size control (`size`) inside the filter panel, and kept it URL-synced with pagination/search state.
- **Filter input UX**: Switched material and component type filters from free-text inputs to dropdown selectors populated from backend unique-value endpoints (including archive endpoints).
- **Component detail mobile action UX**: Replaced native browser confirmation popups for archive/restore/delete actions with in-app dialog confirmations for better mobile reliability and consistency.
- **Validation dashboard delete UX**: Replaced native delete confirmation popup with in-app dialog in admin validation page.
- **Browse page direct-ID entry UX**: Refined direct component-ID navigation field styling and prominence with a compact, more discoverable inline callout.



## [0.4.6.0] - 2026-04-22



### Versions

- CSC FastAPI Backend:  0.4.6.0
- CSC React Frontend:   0.4.6.0
- CSC Grasshopper Interface: 0.4.5.3



### Added



#### CSC FastAPI Backend

- **Component metadata edit endpoint**: Added `PATCH /components/{component_id}` (admin-only) to update simple component metadata. Accepts a partial `ComponentMetadataUpdate` payload covering `name`, `type`, `material`, `dataset`, `complexity`, `fragment`, `assembly`, `color` (RGB), and `location` (lat/lon). Structural and derived fields (geometry, bbx, frames, descriptors, processes, attributes, marker points, `reserved`, `validated`) are intentionally excluded; `lastmodified` is refreshed automatically on successful update.
- **Component ID validation for transmission**: `POST /component_id_transmission` now rejects IDs that already exist in the catalog (`status: component_id_exists`) to prevent reusing existing component IDs.



#### CSC React Frontend

- **Admin component metadata editor**: New route `/components/[component_id]/edit` with a dedicated `ComponentEditForm` UI for admins. Provides inputs for name, type (dropdown), material (with suggestions from `/materials`), dataset (with suggestions from `/datasets`), complexity, fragment/assembly flags, RGB color (color picker + R/G/B inputs), and geographic location (lat/lon). Only changed fields are sent in the `PATCH` request; non-admin or unauthenticated users are redirected.
- **Edit Metadata button in component detail card**: Added an "Edit Metadata" button to the admin action area on the component detail page that links to the new edit route (hidden for archived components).



#### CSC Grasshopper Interface

- **FetchTransmittedID component**: Added `DDU_CSC_FetchTransmittedID.py` to retrieve the currently pending transmitted ID using the shared `CSC_Session` auth state.



### Changed



#### CSC FastAPI Backend

- **Transmission router naming**: Renamed API module from `ghtransmit.py` to `idtransmission.py` and updated router registration/tag to `idtransmission` (no backwards-compat alias).



#### CSC Grasshopper Interface

- **Automatic consume after AddComponent success**: `DDU_CSC_AddComponent.py` now consumes `/component_id_transmission/consume` immediately after successful component creation (`201`) in a non-fatal way.



#### CSC React Frontend

- **Transmission UX robustness**: Improved `409` handling for ID transmission to support both overwrite conflict payloads and `component_id_exists` payloads without breaking UI flow.
- **Immediate ID availability feedback**: Added pre-transmit ID availability checks after scan/manual input in `ComponentIdTransmitter`, including disabled transmit while checking/when ID already exists.
- **Navigation and wording clarity**:
  - Grouped Components menu into **Explore**, **Capture**, and **Insights** sections.
  - Renamed **Identify Component** to **Scan & Identify**.
  - Renamed **Find Component** workflow to **Locate by ID** across route, page, component names, and links (`/findcomponent` -> `/locate-by-id`).
- **Page guidance improvements**: Added colored info boxes with explicit `Purpose / Input / Result` bullets on `Scan & Identify`, `Locate by ID`, and `Transmit ID`, including spacing/wording refinements for consistency and clarity.



#### Documentation

- **GH Interface credits**: Added credits for Alessandro Garruto in `gh-interface` component tips for `CSC_FindLargestFlatSide` and `CSC_MaxInscribedQuad`.



## [0.4.4.0] - 2026-04-21



### Versions

- CSC FastAPI Backend:  0.4.4.0
- CSC React Frontend:   0.4.4.0
- CSC Grasshopper Interface: 0.4.5.3



### Added



#### CSC FastAPI Backend

- **Component ID Transmission Router**: New router `ghtransmit.py` exposing
authenticated endpoints for transmitting a scanned component ID from the
web frontend to Grasshopper:
  - `GET /component_id_transmission` - fetch the current pending transmission
  for the authenticated user.
  - `POST /component_id_transmission` - store a pending transmission with
  `force_overwrite` flag. Returns `409 conflict` if a different pending ID
  already exists and the user has not confirmed overwrite.
  - `DELETE /component_id_transmission` - clear the pending transmission.
  - `POST /component_id_transmission/consume` - remove the pending
  transmission after the component has been successfully added to the
  database (supports matching `component_id` to avoid consuming newer
  scans).
- **Mongo Collection Wiring**: Registered `component_id_transmission`
collection on the app during startup. One document per user (natural key
`_id = user_id`).



#### CSC React Frontend

- **Transmit ID to Grasshopper Page**: New page at `/transmit-id` with a QR
scanner and manual input for transmitting a scanned component ID to
Grasshopper. Shows the current pending ID, allows clearing it, and handles
overwrite confirmation via a modal dialog when a different pending ID
already exists.
- `ComponentIdTransmitter` **Component**: New reusable client component
encapsulating the full scan/transmit/overwrite UX.
- **App Menu Entry**: Added "Transmit ID to GH" entry under the Components
section of the app menu.



### Changed

- **Versions**: Bumped backend and frontend to `0.4.4.0` to reflect the new
Grasshopper ID transmission feature.



## [0.4.5.3] - 2026-03-18



### Versions

- CSC FastAPI Backend:  0.4.2.0
- CSC React Frontend:   0.4.3.3
- CSC Grasshopper Interface: 0.4.5.3



### Changes

- **Environment Variables**: Updated FastAPI and shell scripts to use env vars



## [0.4.5.3] - 2026-03-16



### Versions

- CSC FastAPI Backend:  0.4.1.0
- CSC React Frontend:   0.4.3.3
- CSC Grasshopper Interface: 0.4.5.3



### Changes

- **Project Name**: Renamed the whole project to "Catalog" instead of "Catalogue" because it was just a shit choice in the beginning :')



## [0.4.5.0] - 2026-02-03



### Versions

- CSC FastAPI Backend:  0.4.1.0
- CSC React Frontend:   0.4.3.3
- CSC Grasshopper Interface: 0.4.5.0



### Changes



#### CSC Grasshopper Interface

- **CreateComponent**: Added optional Name input field
- **DisassembleComponent**: Added Name output field



## [0.4.3.3] - 2025-12-09



### Versions

- CSC FastAPI Backend:  0.4.1.0
- CSC React Frontend:   0.4.3.3
- CSC Grasshopper Interface: 0.4.3.0



### Added



#### CSC FastAPI Backend

- **Add Archive Router**: Add router and routes to handle component archiving instead of hard deletion



#### CSC React Frontend

- **Add Archive Feature and Page**: Add UI features and pages to support archiving of components.



## [0.4.3.2] - 2025-12-09



### Versions

- CSC FastAPI Backend:  0.4.0.4
- CSC React Frontend:   0.4.3.2
- CSC Grasshopper Interface: 0.4.3.0



### Changed



#### CSC React Frontend

- **QR Code Scanner**: Try to fix error verbosity during frame errors (no qr code detected)



## [0.4.3.1] - 2025-11-05



### Versions

- CSC FastAPI Backend:  0.4.0.4
- CSC React Frontend:   0.4.3.1
- CSC Grasshopper Interface: 0.4.3.0



### Changed



#### CSC React Frontend

- **GH Interface Page**: Fixed mobile layout of "Copy GH XML" Buttons



## [0.4.3.0] - 2025-11-05



### Versions

- CSC FastAPI Backend:  0.4.0.4
- CSC React Frontend:   0.4.3.0
- CSC Grasshopper Interface: 0.4.3.0



### Changed



#### CSC Grasshopper Interface

- **FetchGeometry**: Update populating of outputs to avoid double geometries as well as putting everything in one tree branch
- **All Components**: Got rid of everything basedpyright-related



## [0.4.3.0] - 2025-11-05



### Versions

- CSC FastAPI Backend:  0.4.0.4
- CSC React Frontend:   0.4.3.0
- CSC Grasshopper Interface: 0.4.2.0



### Changed



#### CSC React Frontend

- **Update to NextJS 16**: Upgrade to NextJS 16.0.5 using codemod.



## [0.4.2.1] - 2025-11-05



### Versions

- CSC FastAPI Backend:  0.4.0.4
- CSC React Frontend:   0.4.0.5
- CSC Grasshopper Interface: 0.4.2.0



### Added



#### CSC React Frontend

- **Added direct UUID lookup**: On the browse page you can now enter a UUID directly and go to its detail page



## [0.4.2.0] - 2025-11-02



### Versions

- CSC FastAPI Backend:  0.4.0.4
- CSC React Frontend:   0.4.0.4
- CSC Grasshopper Interface: 0.4.2.0



### Added



#### CSC FastAPI Backend

- **Added Analytics route**: Analytics route for retrieving database stats.



#### CSC React Frontend

- **Added Analytics page**: Analytics page for displaying database stats.
- **Added New GH Components**: Added new GH Components to gh interface page.



#### CSC Grasshopper Interface

- **Added FindLargestFlatSide Component**: Finds largest flat side and the corresponding plane in a Mesh.
- **Added FindMaximumQuadrilateral Component**: Finds largest quadrilateral polygon inside a boundary polyline.



## [0.4.0.3] - 2025-10-30



### Versions

- CSC FastAPI Backend:  0.4.0.3
- CSC React Frontend:   0.4.0.3
- CSC Grasshopper Interface: 0.4.1.0



### Added



#### CSC FastAPI Backend

- **GH XML Sync**: Automated sync script (`ghxml_sync.sh`) to mirror pasteable XML files from private GitHub repository using sparse checkout
- **GH XML API Routes**: New authenticated endpoints `/ghupdates/xml_names` and `/ghupdates/xml/{name}` to serve cached XML files
- **Config Integration**: Added `gh_xml_cache_dir` configuration support, loaded from `dbconfig.json` and available via `app.gh_xml_cache_dir`
- **Cron Job Configuration**: Added cron job configuration file for automatic XML sync every 30 minutes



#### CSC React Frontend

- **Copy-to-Clipboard for GH Components**: Added copy buttons on all Grasshopper component cards to copy XML directly to clipboard
- **CSC_Update Component Documentation**: Added component card for CSC_Update in Session Components section
- **Getting Started Enhancements**: Added "NEW! Automatic Updater" card with copy functionality and "Find out more" link



### Changed



#### CSC FastAPI Backend

- **GH Updates Router**: Enhanced to read XML cache directory from app state instead of hardcoded paths
- **Config Template**: Updated `dbconfig.template.json` to include `gh_xml_cache_dir` field



#### CSC React Frontend

- **GH Interface Page**: Enhanced component cards with copy-to-clipboard functionality and improved visual feedback
- **Copy Button UX**: Replaced alert-based feedback with visual state indicators (Check icon and "Copied!" text)



#### Documentation

- **README**: Added Grasshopper XML Sync CronJob setup instructions including configuration, testing, and cron job setup steps



## [0.4.0.2] - 2025-10-29



### Versions

- CSC FastAPI Backend:  0.4.0.1
- CSC React Frontend:   0.4.0.2
- CSC Grasshopper Interface: 0.4.0.0



### Changed



#### CSC React Frontend

- **QR Code Scanning**: Modularized QR Code Scanner



## [0.4.0.1] - 2025-10-27



### Versions

- CSC FastAPI Backend:  0.4.0.0
- CSC React Frontend:   0.4.0.1
- CSC Grasshopper Interface: 0.4.0.0



### Changed



#### CSC FastAPI Backend

- **Descriptor Computation**: Fixed Timestamps, added timestamp utility to use in all routes



#### CSC React Frontend

- **BackgroundMesh**: Fixed cutoff at bottom on Sign-In, Register and Home pages



## [0.4.0.0] - 2025-10-27



### Versions

- CSC FastAPI Backend:  0.4.0.0
- CSC React Frontend:   0.4.0.0
- CSC Grasshopper Interface: 0.4.0.0



### Added



#### CSC FastAPI Backend

- **Descriptor Computation**: Sphere score based on DCT approach
- **Geometry Maintenance**: Automated maintenance script and cronjob configuration
- **Utility Routes**: Descriptor output log checking endpoint
- **Email Service**: Enhanced email service integration



#### CSC React Frontend

- **BackgroundMesh**: Animated mesh on some pages as background with scale factor control
- **Theme Toggle**: Switch between light, dark, and system
- **Favicons**: Updated favicon set for all platforms
- **Architecture Charts**: Mermaid diagrams for documentation



#### CSC Grasshopper Interface

- **ComputeTSNE**: T-SNE computation component for dimensionality reduction
- **GetDescriptor**: Descriptor extraction component
- **CreateUUID**: UUID generation component
- **Enhanced Parameter Descriptions**: Better input parameter documentation



### Changed



#### CSC FastAPI Backend

- **PCA Frame**: Ensure right-handedness of PCA frame transformations
- **Environment Configuration**: Updated environment specifications



#### CSC React Frontend

- **Input Placeholders**: Improved registration form placeholders
- **Next.js**: Updated to latest 15.x version
- **Next Auth**: Updated authentication system
- **Design Viewer**: Refactored design and component viewer interfaces



#### CSC Grasshopper Interface

- **Assembly Behavior**: Changed assembly behavior
- **Component Updates**: Small fixes across components
- **Dev Files**: Updated development files
- **User Object Re-export**: Re-exported user objects with updates



## [0.3.1.2] - 2025-10-07



### Versions

- CSC FastAPI Backend:  0.3.1.0
- CSC React Frontend:   0.3.1.1
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.1



### Added



#### CSC React Frontend

- **Cookie Notice**: Added a cookie notice banner that informs users about the use of technically necessary cookies only. Users can accept or dismiss the notice, and their choice is remembered in local storage.
- **Cookie Settings Page**: Introduced a "Cookie Settings" section in the settings page, allowing users to review cookie usage and re-display the cookie notice if desired.



### Changed



#### CSC React Frontend

- **Session Handling Update**: Improved session state management .



## [0.3.1.1] - 2025-09-11



### Versions

- CSC FastAPI Backend:  0.3.1.0
- CSC React Frontend:   0.3.1.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.1



### Added



#### CSC Grasshopper Interface

- **Binary Geometry Caching**: Implemented high-performance binary caching for geometry data using Rhino's JSON serialization
- **JSON Mesh Serialization**: Added support for serializing Rhino meshes to JSON with full user data preservation
- **Enhanced Error Handling**: Improved error handling for mesh reconstruction and geometry processing
- **Cache Validation**: Added comprehensive validation for cached geometry data before use



### Changed



#### CSC Grasshopper Interface

- **Cache Storage Format**: Migrated from OBJ text files to pickled JSON strings for maximum performance
- **Mesh Processing**: Optimized mesh duplication and transformation for cached geometry baking
- **Error Recovery**: Enhanced error recovery to continue processing when individual meshes fail
- **Debug Output**: Cleaned up excessive debug logging while preserving important status messages



### Fixed



#### CSC Grasshopper Interface

- **BakeComponents Error**: Fixed "does not exist in ObjectTable" error when baking cached geometry
- **Mesh Reconstruction**: Fixed issues with reconstructing meshes from JSON when some meshes fail
- **Cache Validation**: Fixed validation logic to properly handle empty or invalid cached data
- **Cross-Component Imports**: Removed circular import dependencies between Grasshopper components



### Technical Details



#### Binary Caching Implementation

- Uses `Rhino.Geometry.Mesh.ToJSON()` with `SerializationOptions` for full data preservation
- Stores pickled JSON strings instead of raw mesh objects for pickle compatibility
- Implements `Rhino.Geometry.Mesh.FromJSON()` for mesh reconstruction
- Maintains ETag compatibility with existing caching system



#### Performance Improvements

- Eliminated OBJ parsing overhead for cached geometry
- Reduced file I/O operations through binary storage
- Improved mesh processing with bulk operations
- Enhanced error handling prevents cascade failures



## [0.3.1.0] - 2025-09-09



### Versions

- CSC FastAPI Backend:  0.3.1.0
- CSC React Frontend:   0.3.1.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.0



### Added



#### CSC FastAPI Backend

- **Geometry ETag Support**: Added ETag generation and conditional request support for geometry endpoints
- **HTTP Caching Headers**: Added Cache-Control headers for improved geometry file caching
- **Conditional Requests**: Support for If-None-Match headers with 304 Not Modified responses
- **File-based ETags**: ETag generation based on file modification time and size for reliable cache validation



#### CSC React Frontend

- **Geometry ETag Caching**: Enhanced ComponentViewer with ETag-based conditional requests for geometry files
- **Smart Cache Validation**: Automatic cache validation using ETag headers to avoid unnecessary re-downloads
- **Improved Performance**: Reduced bandwidth usage and faster loading for cached geometry files



### Changed



#### CSC FastAPI Backend

- **Geometry Endpoints**: Enhanced `/components/{id}/geometry_detailed` and `/components/{id}/geometry_reduced` with ETag support
- **Backward Compatibility**: All changes are additive and maintain full backward compatibility with existing clients



#### CSC React Frontend

- **Component Validation UI**: Updated Validate button to only be active for unvalidated components
- **Enhanced User Feedback**: Dynamic button text and tooltips based on component validation status
- **Geometry Cache Structure**: Enhanced cache to store ETag metadata alongside geometry data



## [0.3.0.0] - 2025-09-05



### Versions

- CSC FastAPI Backend:  0.3.0.0
- CSC React Frontend:   0.3.0.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.0



### Added



#### CSC FastAPI Backend

- **Multi-Mesh Support**: Added `meshes` field to `ComponentGeometry` model for supporting multiple meshes per component
- **Marker Points Field**: Added `marker_points` field to `ComponentModel` for storing coordinate triplets
- **OBJ-Only Geometry**: Updated geometry endpoints to support OBJ files with embedded vertex colors only
- **Database Migration Scripts**: Created comprehensive migration scripts for multi-mesh and field format updates
- **Schema Validation**: Enhanced component validation with proper field type checking and format validation



#### CSC React Frontend

- **Multi-Mesh Visualization**: Complete support for displaying multiple meshes in ComponentViewer
- **Vertex Color Support**: Full support for `v X Y Z R G B` vertex colors in OBJ files with smart normalization
- **Mesh Visibility Controls**: Individual checkbox controls to show/hide specific meshes in primitive mode
- **Manual OBJ Parsing**: Custom OBJ parser for reliable vertex color extraction and face triangulation
- **Smart Color Normalization**: Automatic detection and conversion of 0-255 to 0-1 color ranges
- **Consistent Geometry Display**: Unified positioning and scaling across primitive, reduced, and detailed modes



#### CSC Grasshopper Interface

- **Multi-Mesh Input Support**: All components now accept `List[Rhino.Geometry.GeometryBase]` for single or multiple meshes
- **OBJ File Generation**: Enhanced OBJ export with proper object declarations (`o object_0`, `o object_1`, etc.)
- **Vertex Color Embedding**: Automatic embedding of vertex colors in OBJ files using `v X Y Z R G B` format
- **PCA Assembly Processing**: New method for computing PCA on entire multi-mesh assemblies with proper centering
- **Coordinate System Mapping**: Correct Rhino (X,Y,Z) to OBJ (X,Z,-Y) coordinate transformation
- **Multi-Mesh Baking**: Support for baking multiple meshes as grouped components with individual metadata
- **Enhanced SyncWithRhinoDoc**: Groups multiple meshes by component ID instead of treating as separate components



#### Database Migration Tools

- **Marker Points Migration**: `migrate_marker_points_and_multi_mesh.py` - Adds marker_points field and converts single-mesh to multi-mesh format
- **Fragment Boolean Migration**: `migrate_fragment_boolean.py` - Ensures fragment field is properly typed as boolean
- **Color Format Migration**: `migrate_color_format.py` - Converts color fields to proper `[R, G, B]` integer format
- **OBJ File Migration**: `convert_obj_files.py` - Processes existing OBJ files to remove MTL references and standardize format



### Changed



#### CSC FastAPI Backend

- **Geometry Endpoints**: Updated to serve OBJ files only, removed MTL and texture file support
- **API Validation**: Enhanced validation for multi-mesh components and proper field format checking
- **Deprecated Endpoints**: Material and texture serving endpoints now return 404 with informative messages
- **Component Model**: Added validation to ensure `mesh` and `meshes` fields are not both present



#### CSC React Frontend

- **ComponentViewer Architecture**: Complete rewrite for multi-mesh support with consistent rendering pipeline
- **Geometry Loading**: Replaced OBJLoader with custom parser for reliable vertex color handling
- **Material System**: Switched to `MeshBasicMaterial` for proper vertex color display without lighting requirements
- **Bounds Integration**: Fixed primitive geometry positioning to work correctly with `Bounds` component
- **Performance Optimization**: Improved geometry caching and memory management for large multi-mesh components



#### CSC Grasshopper Interface

- **CreateComponent**: Updated to handle both single and multiple mesh inputs with unified processing pipeline
- **FetchGeometry**: Enhanced to parse multi-object OBJ files and return lists of geometry objects
- **DisassembleComponent**: Added support for creating multiple `Rhino.Geometry.Mesh` objects from `meshes` field
- **BakeComponents**: Updated to bake multiple meshes with proper grouping and metadata
- **AddComponent**: Simplified to handle OBJ-only uploads with proper file validation
- **SyncWithRhinoDoc**: Refactored to group meshes by component ID for proper component management



### Technical Improvements



#### Multi-Mesh Architecture

- **Unified Data Model**: Consistent handling of single and multiple meshes across all components
- **Backward Compatibility**: Existing single-mesh components continue to work seamlessly
- **Forward Compatibility**: New multi-mesh format supports future enhancements
- **Data Integrity**: Comprehensive validation ensures proper component structure



#### Geometry Processing

- **Smart Scaling**: Consistent scaling and positioning across all geometry modes
- **Coordinate Systems**: Proper mapping between Rhino and OBJ coordinate systems
- **Face Triangulation**: Automatic conversion of quads and N-gons to triangles for rendering
- **Vertex Color Handling**: Robust parsing and normalization of vertex colors in various formats



#### Performance & Reliability

- **Memory Management**: Proper cleanup and caching of geometry objects
- **Error Handling**: Comprehensive error handling with informative user feedback
- **Type Safety**: Eliminated all TypeScript `any` types with proper interfaces
- **Code Quality**: Resolved all linting errors and improved maintainability



#### Migration & Deployment

- **Database Safety**: All migration scripts include comprehensive validation and rollback capabilities
- **File System Migration**: Automated conversion of existing OBJ files to new format
- **Schema Validation**: Post-migration verification ensures data integrity
- **Documentation**: Comprehensive documentation for all migration processes



### Breaking Changes



#### CSC FastAPI Backend

- **Material/Texture Endpoints**: `get_component_material_detailed`, `get_component_material_reduced`, and `get_component_texture` now return 404
- **Geometry Upload**: `add_reduced_geometry` and `add_detailed_geometry` now only accept OBJ files



#### CSC Grasshopper Interface

- **Input Parameters**: All geometry inputs now expect `List[Rhino.Geometry.GeometryBase]` instead of single objects
- **OBJ File Format**: Generated OBJ files now use object declarations and embedded vertex colors only



### Migration Notes

- **Database Migration**: Run `migrate_marker_points_and_multi_mesh.py` to update existing components
- **File System Migration**: Run `convert_obj_files.py` to update existing OBJ files
- **Frontend Update**: No manual migration required - automatically handles both old and new formats
- **Grasshopper Update**: Update all components to new versions for multi-mesh support



## [0.2.9.0] - 2025-09-04



### Versions

- CSC FastAPI Backend:  0.2.9.0
- CSC React Frontend:   0.2.4.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.2.0



### Added



#### CSC FastAPI Backend

- **ETag-based Caching System**: Implemented comprehensive caching solution with ETag support for conditional requests
- **Component Schema Caching**: Added schema endpoint with ETag support for offline component creation
- **Cache-Control Headers**: Added proper HTTP caching headers for better performance
- **ETag Generation Utilities**: Created utility functions for generating ETags from component data and timestamps



#### CSC Grasshopper Interface

- **Local Cache Management**: Implemented `_ComponentCache` class for local storage with thread safety and TTL support
- **Cache Integration**: All fetch components now use intelligent caching with ETag validation
- **Schema-driven Component Creation**: `CreateComponent` now uses cached/fetched schema instead of hardcoded data
- **Status Output**: Added detailed status messages via dedicated output parameter for better user feedback
- **Cache Control Parameters**: Added `DisableCache` and `ClearCache` inputs to SignIn component



### Changed



#### CSC FastAPI Backend

- **API Endpoints**: Enhanced `/components`, `/components/{id}`, and `/schema/component` with ETag support
- **Conditional Requests**: Implemented 304 Not Modified responses for unchanged resources
- **Component Model**: Added optional `etag` field to ComponentModel for cache validation
- **Backward Compatibility**: All changes are additive and maintain full backward compatibility



#### CSC Grasshopper Interface

- **Authentication Core**: Enhanced `_AuthCore` with `cached_get` method for intelligent caching
- **Component Data Creation**: Completely rewrote `build_component_data_from_schema` to use actual schema
- **Dynamic Schema Usage**: Components now build data structures dynamically from fetched schema
- **Improved Error Handling**: Enhanced validation and error messages throughout all components



### Technical Improvements

- **Hybrid ETag Generation**: Combines `lastmodified` timestamp with key component fields for robust cache validation
- **Cross-platform Caching**: Supports Windows (`%APPDATA%`) and macOS (`~/Library/Application Support`) cache locations
- **Single Components Cache + Metadata Cache**: Efficient storage strategy avoiding data duplication
- **Thread Safety**: Implemented proper locking mechanisms for concurrent cache access
- **Schema Validation**: Dynamic component data creation ensures strict adherence to data model
- **Performance Optimization**: Reduced bandwidth usage through intelligent caching and conditional requests



## [0.2.8.0] - 2025-09-03



### Versions

- CSC FastAPI Backend:  0.2.8.0
- CSC React Frontend:   0.2.3.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.1.0



### Added



#### CSC Grasshopper Interface

- **Enhanced Component Management**: Improved component creation and management workflows
- **Better Error Handling**: Enhanced error messages and user feedback across all components



### Changed



#### CSC FastAPI Backend

- **Version Bump**: Updated to version 0.2.8.0 for new release cycle
- **API Stability**: Maintained backward compatibility while preparing for future enhancements



#### CSC React Frontend

- **Version Bump**: Updated to version 0.2.3.0 for new release cycle
- **UI Improvements**: Enhanced user interface components and interactions



#### CSC Grasshopper Interface

- **Version Standardization**: All components now use consistent version numbering
- **Component Updates**: Refreshed component versions for better tracking and maintenance



### Technical Improvements

- **Version Management**: Improved version tracking across all project components
- **Release Coordination**: Better synchronization between backend, frontend, and Grasshopper interface
- **Documentation**: Updated changelog with comprehensive version information



## [0.2.5.0] - 2025-08-26



### Versions

- CSC FastAPI Backend:  0.2.5.0
- CSC React Frontend:   0.2.2.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.0.0



### Added



#### CSC React Frontend

- **Component Reservation System Integration**: Complete frontend integration for the component reservation system
- **User Dashboard**: New dashboard page accessible from user menu with quick stats and navigation
- **Reserved Components Page**: Dedicated page showing all components reserved by the logged-in user
- **Reservation Management**: Users can reserve and release components directly from component detail pages
- **Enhanced Component Overview**: Added "Reserved" column showing reservation status and username
- **Improved Navigation**: Added dashboard link to AppMenu with organized section headlines



#### User Experience Enhancements

- **Reservation Buttons**: "Reserve Component" and "Release Component" buttons on component detail cards
- **Username Display**: Shows human-readable usernames instead of UUIDs for reserved components
- **Smart UI States**: Dynamic button text and states based on reservation status
- **Quick Actions**: Release components directly from the reserved components overview table



#### Technical Improvements

- **Type Safety**: Eliminated all TypeScript `any` types with proper interfaces
- **React Hooks**: Fixed useEffect dependency warnings with useCallback
- **Code Quality**: Resolved all linting errors and improved code maintainability
- **Responsive Design**: Enhanced mobile and desktop layouts for reservation management



#### CSC FastAPI Backend

- **Component Reservation System**: New API routes for managing component reservations
- **Reserve Component Endpoint**: `POST /reserve/{component_id}` allows users to reserve components
- **List Reserved Components Endpoint**: `GET /reserve/{user_identifier}` lists all components reserved by a user
- **Release Component Endpoint**: `DELETE /reserve/{component_id}` allows users to release their reservations
- **User Identification Support**: Reservation endpoints accept both UUID and username for user identification
- **PCA Frame Property**: Added `pca_frame` property to component model for future PCA transformation support
- **Reserved Property**: Added `reserved` property to component model to track component reservations



#### Database Schema Updates

- **Component Model Enhancement**: Extended `ComponentModel` with `pca_frame` and `reserved` properties
- **Migration Script**: Created `migrate_add_pca_frame_and_reserved.py` to update existing components
- **Backward Compatibility**: All new properties are optional and don't affect existing functionality



### Changed



#### CSC React Frontend

- **Component Overview Table**: Added new "Reserved" column with reservation status and username information
- **User Menu**: Enhanced UserItem component with dashboard navigation link
- **AppMenu Organization**: Added section headlines ("Main" and "Other") for better navigation structure
- **Component Detail Cards**: Added reservation management buttons alongside existing "Find Component" button



#### CSC FastAPI Backend

- **Component Model**: Updated `ComponentModel` and `UpdateComponentModel` with new reservation fields
- **API Router**: Added new reservation router (`reserve.py`) to handle component reservation operations
- **Security**: Implemented proper authorization - users can only manage their own reservations unless admin
- **Data Enrichment**: Enhanced component endpoints to include `reserved_by_username` for better user experience



### Technical Improvements

- **Reservation Logic**: Robust reservation system with conflict detection and proper error handling
- **Database Operations**: Efficient MongoDB operations for reservation management
- **API Design**: RESTful API design following FastAPI best practices
- **Error Handling**: Comprehensive error responses with appropriate HTTP status codes
- **Security**: Role-based access control for reservation management
- **Frontend-Backend Integration**: Seamless integration between reservation API and frontend components



## [0.2.4.0] - 2025-08-25



### Versions

- CSC FastAPI Backend:  0.2.4.0
- CSC React Frontend:   0.2.1.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.0.0



### Added



#### CSC React Frontend

- **Dual Date Format Support**: Enhanced `formatTimestamp` function to handle both old and new date formats
- **Migration Compatibility**: Frontend now works seamlessly with both legacy `DDMMYY-HHMMSS` and new ISO `YYYY-MM-DDTHH:MM:SSZ` formats
- **Error Resilience**: Improved error handling prevents crashes from unknown date formats



#### Database Migration Tools

- **Bounding Box Format Migration**: Script to convert from `[[minX, minY, minZ], [maxX, maxY, maxZ]]` to `[X, Y, Z]` (maximum extents)
- **Date Format Migration**: Script to convert dates from `DDMMYY-HHMMSS` to proper ISO format
- **Comprehensive Migration**: Handles both bounding box and date format updates in a single operation



### Changed



#### CSC React Frontend

- **Date Display Consistency**: All timestamps now display in uniform `YYYY.MM.DD HH:MM:SS` format regardless of source format
- **Backward Compatibility**: Existing functionality preserved while adding support for new ISO date format
- **Enhanced User Experience**: Filter menu now collapsed by default for better space management
- **Improved Component Display**: Increased ID button width for better component ID visibility



#### Database Schema

- **Bounding Box Format**: Updated from coordinate pairs to maximum extents for better performance and clarity
- **Date Format Standardization**: All dates now stored in ISO 8601 format for better compatibility and sorting
- **Migration Safety**: Preserves original creation dates while updating modification timestamps



### Technical Improvements

- **Robust Date Parsing**: Intelligent format detection with graceful fallbacks
- **Migration Scripts**: Comprehensive database migration tools with verification capabilities
- **Frontend Resilience**: Enhanced error handling prevents application crashes from data format issues
- **Code Quality**: Improved defensive programming and error logging throughout the system



## [0.2.3.0] - 2025-08-25



### Versions

- CSC FastAPI Backend:  0.2.3.0
- CSC React Frontend:   0.2.0.9
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.0.0



### Added



#### CSC FastAPI Backend

- **Enhanced Component Filtering**: Added comprehensive filtering capabilities to component API routes
- **Complexity Filtering**: New `complexity` parameter to filter components by complexity level (0-3)
- **Fragment Status Filtering**: New `fragment` parameter to filter components by fragment status
- **Bounding Box Dimension Filtering**: New range-based filters for component dimensions:
  - `bbx_min_x`, `bbx_min_y`, `bbx_min_z`: Minimum X, Y, Z values
  - `bbx_max_x`, `bbx_max_y`, `bbx_max_z`: Maximum X, Y, Z values
- **Improved API Documentation**: All query parameters now include descriptive documentation for better developer experience



### Changed



#### CSC FastAPI Backend

- **API Parameter Structure**: Updated all filter parameters to use FastAPI's `Query` with descriptive documentation
- **Consistent Filtering**: All three component routes (`/componentcount`, `/shallowcomponents`, `/components`) now support the same comprehensive filtering options
- **Enhanced OpenAPI Schema**: Better parameter documentation will improve the generated API documentation and Swagger UI
- **Backward Compatibility**: All existing functionality preserved - new filters are optional and don't affect current API usage



### Technical Improvements

- **MongoDB Query Optimization**: Efficient bounding box filtering using MongoDB's `$gte` and `$lte` operators
- **Parameter Validation**: Proper type hints and validation for all new filter parameters
- **Code Consistency**: Unified filtering logic across all component routes for maintainability
- **Professional API Standards**: Following FastAPI best practices for parameter documentation and validation



## [0.2.0.9] - 2025-08-22



### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.9
- CSC Sheetscan Module: 0.0.1.11
- **CSC Grasshopper Interface: 0.1.0.0**



### Added



#### CSC Grasshopper Interface (New Module)

- **Centralized Authentication System**: Implemented `AuthCore` class for JWT token management across all components
- **Sticky Storage Integration**: Components now share authentication state via Grasshopper's sticky storage
- **Comprehensive Error Handling**: Added runtime messages (Remark, Warning, Error) for better user feedback
- **Color Fallback System**: Enhanced mesh color handling with component color fallbacks and default gray
- **Parameter Documentation**: Added tooltips for all input/output parameters across all components
- **Consistent Coding Standards**: Unified import organization, pyright suppressions, and code structure



#### Updated Components

- **CSC_SignIn**: Complete authentication implementation with JWT token management
- **CSC_FetchAllComponents**: Updated to use centralized AuthCore pattern
- **CSC_FetchComponents**: Enhanced with AuthCore integration and improved error handling
- **CSC_DisassembleComponent**: Added descriptors output and comprehensive geometry processing
- **CSC_BakeComponents**: Enhanced with color fallbacks and improved user feedback



### Changed



#### CSC Grasshopper Interface

- **Authentication Flow**: Replaced scattered authentication logic with centralized AuthCore system
- **Component Architecture**: Standardized all components with consistent `__init__`, `_add`* methods, and error handling
- **Mesh Color Handling**: Implemented three-tier color fallback system (mesh colors --> component color --> default gray)
- **Output Format**: Descriptors now output as JSON strings for consistency with other components
- **Error Recovery**: All components now provide graceful error handling with clear user feedback
- **Code Quality**: Applied consistent pyright suppressions, import organization, and coding standards



#### Component-Specific Improvements

- **CSC_SignIn**: Added username tracking, refresh functionality, and comprehensive API error handling
- **CSC_FetchAllComponents**: Enhanced with proper authentication validation and runtime messaging
- **CSC_FetchComponents**: Improved individual component fetching with better error handling
- **CSC_DisassembleComponent**: Added descriptors output and enhanced geometry processing robustness
- **CSC_BakeComponents**: Improved baking process with better status tracking and error handling



### Technical Improvements

- **Memory Management**: Eliminated code duplication through centralized authentication
- **User Experience**: Consistent feedback across all components via multiple message channels
- **Robustness**: Enhanced error handling prevents crashes and provides clear user guidance
- **Maintainability**: Standardized code structure makes future updates easier and more consistent
- **Student Experience**: Professional-grade components with clear error messages and status updates



## [0.2.0.8] - 2025-08-21



### Added

- Enhanced authentication system with comprehensive error handling and user feedback
- Added Register button alongside Sign In button in UserItem component for non-authenticated users
- Added security notice on registration page warning users to use unique passwords
- Added cross-links between sign in and register pages for better user navigation



### Changed

- Improved sign in form error handling with specific error messages for different failure types
- Updated sign in and register pages to stick to top on mobile/narrow screens instead of centering
- Enhanced register page styling to match sign in page using consistent Card components
- Improved form validation with client-side checks and better error positioning



### Fixed

- Sign in form now properly displays error messages on authentication failures
- Register page layout now properly contains all elements within the form container
- Consistent styling between authentication pages for better user experience



## [0.2.0.7] - 2025-08-21



### Fixed

- Responsive layout issues when dynamically resizing window width
- Layout not properly adapting when switching between mobile and desktop viewports
- Sidebar visibility and positioning on resize events
- Component detail page responsive behavior when resizing from wide to narrow
- Fixed layout overflow issues caused by fixed minimum widths
- Component detail page width constraints - now properly adapts to viewport when resizing
- Fixed Card components expanding beyond container width on resize
- **Component detail page now properly constrains width to viewport (no more right-side overflow)**



### Changed

- Improved responsive behavior with proper resize event listeners
- Sidebar now dynamically shows/hides based on screen size
- Header and mobile menu properly adapt to viewport changes
- Layout structure changed from CSS Grid to Flexbox for better responsive behavior
- Added proper cleanup of resize event listeners
- Component detail page now uses flexible layout instead of fixed minimum widths
- Changed breakpoint from `md:` to `lg:` for better mobile experience
- Improved text sizing and button layout for different screen sizes
- Component detail page layout changed from CSS Grid to Flexbox for better width control
- Added explicit width constraints and overflow handling to Card components
- **Simplified component detail page width handling to match working overview page approach**
- **Enhanced ThemeToggle with hover effects - moon icon now uses accent color on hover**



### Added

- Dynamic screen size detection in Sidebar, Header, AppMenu, and ComponentDetailCard components
- Automatic mobile menu closing when resizing to desktop
- Proper z-index management for overlapping elements
- Responsive text sizing for ComponentViewer overlay UI
- Break-word handling for long component IDs
- Strict width constraints and overflow handling for component detail page



## [0.2.0.6] - 2025-08-21



### Changed

- Restructured frontend components folder organization:
  - `src/frontend/components/layout/` - Layout components (Header, Sidebar, Footer)
  - `src/frontend/components/auth/` - Authentication components (UserItem, SignInForm)
  - `src/frontend/components/components/` - Component-specific components
  - `src/frontend/components/common/` - Shared/common components (ThemeToggle, models)
- Updated all import statements to use correct absolute paths (`@/components/ui/...`)
- Fixed broken UI component imports after folder restructuring



## [0.2.0.5] - 2025-08-21



### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.5
- CSC Sheetscan Module: 0.0.1.11



### Added



#### CSC React Frontend

- Added responsive mobile navigation with burger menu
- Added mobile UserItem display in header
- Improved header design with better typography and spacing



### Changed



#### CSC React Frontend

- Redesigned header for better mobile and desktop experience
- Implemented collapsible mobile navigation menu
- Moved theme toggle to header for better accessibility
- Added smooth animations for mobile menu transitions
- Mobile menu automatically closes after navigation



## [0.2.0.4] - 2025-08-21



### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.4
- CSC Sheetscan Module: 0.0.1.11



### Fixed



#### CSC React Frontend

- Fixed sidebar menu hover behavior - buttons no longer stay "selected" after hovering
- Replaced Command components with proper navigation items for better UX
- Maintained card-like visual appearance while fixing persistent selection states



## [0.2.0.3] - 2025-08-21



### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.3
- CSC Sheetscan Module: 0.0.1.11



### Fixed



#### CSC React Frontend

- Fixed missing role field in user registration API - now automatically sets role to 'user' for new registrations
- Fixed Access card visibility on home page - now hidden when user is logged in



## [0.2.0.2] - 2025-08-20



### Versions

- CSC FastAPI Backend:  0.2.1.0
- CSC React Frontend:   0.2.0.2
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC React Frontend

- Changed routes to adapt to new preview image fetch method
- Ensure that prod builds locally without errors



## [0.2.0.2] - 2025-08-20



### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.1
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Add preview image route



## [0.2.0.1] - 2025-08-20



### Versions

- CSC FastAPI Backend:  0.2.1.0
- CSC React Frontend:   0.2.0.1
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC React Frontend

- Now builds in production mode



## [0.2.0.0] - 2025-08-19



### Versions

- CSC FastAPI Backend:  0.2.1.0
- CSC React Frontend:   0.2.0.0
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- First stable version with new and revamped backend



#### CSC React Frontend

- Completely revamped NextJS app using NextJS 15, builds in development mode
- Production build still failing



## [0.0.1.20] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.12
- CSC React Frontend:   0.1.4.18
- CSC Sheetscan Module: 0.0.1.11



### Added



#### CSC React Frontend

- Added BoundingBox display option



### Changed



#### CSC React Frontend

- Modified ComponentViewer interface to be an overlay on top of the 3d canvas



## [0.0.1.19] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.12
- CSC React Frontend:   0.1.4.17
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Modified componentcount route to work with a filter query (we will need this for correct pagination in frontend)



#### CSC React Frontend

- Reoriented all Rubble meshes according to PCA
- Recomputed primitive geometry with 300 faces
- Updated database, component geometry, component previews



## [0.0.1.18] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.10
- CSC React Frontend:   0.1.4.16
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Added material filter to components and shallowcomponents route



#### CSC React Frontend

- Added functionality to filter for materials and component types



## [0.0.1.17] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.9
- CSC React Frontend:   0.1.4.15
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Added routes to fetch detailed geometry, reduced mesh geometry, material and textures



#### CSC React Frontend

- Updated detailed and reduced geometry routing to fetch geometry using backend API



## [0.0.1.16] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.8
- CSC React Frontend:   0.1.4.14
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC React Frontend

- Fixed Tailwinds



## [0.0.1.15] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.8
- CSC React Frontend:   0.1.4.13
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC React Frontend

- Updated ComponentDetail display



## [0.0.1.14] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.8
- CSC React Frontend:   0.1.4.12
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Removed Materialthickness



#### CSC React Frontend

- Removed Materialthickness and adapted everything to use BBX extents



## [0.0.1.13] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.7
- CSC React Frontend:   0.1.4.11
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC React Frontend

- Updated ComponentViewer component to be able to display more detailed meshes on request



## [0.0.1.12] - 2024-12-14



### Versions

- CSC FastAPI Backend:  0.1.0.7
- CSC React Frontend:   0.1.4.10
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Modified component spec to enable SAS rubble imports



#### CSC React Frontend

- Modified Component Model and implementation to reflect changes in component spec



## [0.0.1.11] - 2024-10-23



### Versions

- CSC FastAPI Backend:  0.1.0.6
- CSC React Frontend:   0.1.4.9
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC React Frontend

- Added possibility to pre-set reference id in `frontend/components/ComponentLookup.tsx`
- Added possibility to pre-set reference id in `frontend/app/findcomponent/page.tsx`
- Added link to find component with pre-set reference id in `frontend/components/ComponentSheet.tsx`
- Added link to find component with pre-set reference id in `frontend/app/components/[component_id]/page.tsx`



## [0.0.1.10] - 2024-10-07



### Versions

- CSC FastAPI Backend:  0.1.0.6
- CSC React Frontend:   0.1.4.8
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Corrected docstring of single component fetch route



#### CSC React Frontend

- Added `components/[component_id]` API route to retrieve single component data
- Added working ComponentDetailPage (`frontend/app/components/[component_id]/page.tsx`)
- Modified `ComponentSheet` to link to component details page



## [0.0.1.9] - 2024-10-02



### Versions

- CSC FastAPI Backend:  0.1.0.5
- CSC React Frontend:   0.1.4.7
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC React Frontend

- Added proper imprint
- Fixed npm vulns



## [0.0.1.9] - 2024-06-21



### Versions

- CSC FastAPI Backend:  0.1.0.5
- CSC React Frontend:   0.1.4.6
- CSC Sheetscan Module: 0.0.1.11



### Changed



#### CSC FastAPI Backend

- Changed Component model to reflect current location as attribute



#### CSC React Frontend

- Extended DataTable for Components with location attribute



#### CSC Sheetscan Module

- Extended BaseModel & SheetModel with location



## [0.0.1.8] - 2024-06-12



### Versions

- CSC FastAPI Backend:  0.1.0.4
- CSC React Frontend:   0.1.4.5
- CSC Sheetscan Module: 0.0.1.10



### Changed



#### CSC React Frontend

- Extended DataTable for Components



## [0.0.1.7] - 2024-06-12



### Versions

- CSC FastAPI Backend:  0.1.0.4
- CSC React Frontend:   0.1.4.4
- CSC Sheetscan Module: 0.0.1.10



### Changed



#### CSC FastAPI Backend

- Fixed color definition in ComponentModel in `models.py`



#### CSC React Frontend

- Adapted table layout for component overview



## [0.0.1.6] - 2024-06-06



### Versions

- CSC FastAPI Backend:  0.1.0.3
- CSC React Frontend:   0.1.4.3
- CSC Sheetscan Module: 0.0.1.10



### Added



#### CSC FastAPI Backend

- Added preview generation routine



### Changed



#### CSC FastAPI Backend

- Moved database connection functions to `utility` module



## [0.0.1.5] - 2024-06-04



### Versions

- CSC FastAPI Backend:  0.1.0.2
- CSC React Frontend:   0.1.4.3
- CSC Sheetscan Module: 0.0.1.10



### Added



#### CSC React Frontend

- Add `ComponentViewerSkeleton.tsx` to display loading message during geometry load.



### Changed



#### CSC React Frontend

- Fix linting in all components.
- Change Sidebar width to `250px`



## [0.0.1.4] - 2024-06-04



### Versions

- CSC FastAPI Backend:  0.1.0.2
- CSC React Frontend:   0.1.4.2
- CSC Sheetscan Module: 0.0.1.10



### Added



#### CSC React Frontend

- Added lazy loading of components
- Added `fetch-components-shallow` route to API
- Added `fetch-component-geometry` route to API



#### CSC FastAPI Backend:

- Added API endpoints for retrieving component geometry and shallow components without geometry



### Changed



#### CSC React Frontend

- Components in the overview are now retrieved *shallow*, e.g. without geometry.
- Geometry is loaded on click during opening of the Component Detail Sheet.



## [0.0.1.3] - 2024-05-24



### Versions

- CSC FastAPI Backend:  0.1.0.1
- CSC React Frontend:   0.1.4.2
- CSC Sheetscan Module: 0.0.1.10



### Changed



#### CSC React Frontend

- Reformatted layout to incorporate Footer.
- Started reformatting of Component Overview DataTable



### Added



#### CSC React Frontend

- Added Credits Page `app/credits/page.tsx`
- Added Footer Component `components/Footer.tsx`
- Added Function `copyright_date` to `lib/utils.ts`



## [0.0.1.2] - 2024-05-24



### Versions

- CSC FastAPI Backend:  0.1.0.1
- CSC React Frontend:   0.1.4.1
- CSC Sheetscan Module: 0.0.1.10



### Fixed



#### CSC FastAPI Backend

- Updated `ComponentModel` in `models.py`
- Fixed response models in `routers.py`



#### CSC React Frontend

- Fixed timestamp printing in console



### Added



#### CSC React Frontend

- Added `timestamp_string` function to `lib/utils.ts`



## [0.0.1.1] - 2024-05-23



### Versions

- CSC FastAPI Backend:  0.1.0.0
- CSC React Frontend:   0.1.4.0
- CSC Sheetscan Module: 0.0.1.10



### Fixed



#### CSC React Frontend

- Fixed Caching (hopefully)



### Added

- Initiated `CHANGELOG.md`

