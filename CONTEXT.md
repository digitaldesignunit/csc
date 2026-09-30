# Catalog of Second Chances (CSC)

A research catalog of reclaimed building components: what each physical piece is, where it came
from, what state it is in, and what is known about it --- so it can be designed with and reused.

## Language

### Components and records

**Component**:
A physical reclaimed building element the catalog tracks --- a beam, a panel, a lump of rubble.
_Avoid_: item, part

**Component identity**:
The catalog's permanent record of one physical component, from its arrival to long after its exit.
_Avoid_: entry, component (when the record is meant)

**Tag**:
The physical QR label on a component; it carries only the identity's UUID, never a URL.
_Avoid_: label, sticker

**Snapshot**:
One recorded state of a component --- its shape and state from a point in time until the next state.
_Avoid_: version (a snapshot *has* a version number), scan (one way to capture a snapshot's geometry)

**Snapshot photo**:
A general-impression picture of a component in one state, so people get an idea of it regardless of how its geometry is represented. Not evidence.
_Avoid_: inspection photo

**Capture**:
How a snapshot's geometry was recorded --- method, device, the coordinate system its stored coordinates are relative to, and the markers and fixtures that appear in it.
_Avoid_: scan metadata

**Fixture**:
An object captured together with a component that is not part of it --- e.g. the robot gripper holding a stone during scanning.
_Avoid_: part (parts belong to the component)

**Marker**:
A labelled reference point in a capture --- fixed on the capture rig, or stuck on the component.
_Avoid_: marker point

**Current snapshot**:
The published snapshot a component page and the passport show by default; set by a moderator, and falls back to the latest published one when it is withdrawn.

**State change**:
The component physically changed (cut, weathered, repaired); recorded as a new snapshot that starts later.
_Avoid_: update, edit

**Correction**:
A recorded fact was wrong; recorded as a new record that supersedes the wrong one, which stays retrievable.
_Avoid_: edit, fix, overwrite

**Draft**:
A record its author is still preparing --- editable, and visible only to the author and the dataset's moderators; submitting it hands it to moderation, and the author can recall it until a moderator acts.

**Publishing**:
The moderation act that makes a record visible in the catalog and lets it count.
_Avoid_: validation, approval

**Withdrawal**:
Marking a published record as not belonging in the catalog (wrong, duplicate, a problem in a photo); the dataset still sees it in full, everyone else only a tombstone.
_Avoid_: deletion, exit (exit is physical)

**Duplicate**:
An identity withdrawn because another identity describes the same physical component; it redirects there.

### Provenance and lifecycle

**Origin**:
How a component entered circulation: deinstallation, demolition, offcut, surplus, or unknown.
_Avoid_: salvage, source

**Deinstallation**:
Removal of a component from a construction work in which it had been installed (the CPR sense).
_Avoid_: salvage, dismantling, demolition (demolition output was not individually deinstalled)

**Offcut**:
Residue of a fabrication process, never installed --- e.g. the Corian panels.
_Avoid_: surplus, scrap

**Surplus**:
An unused whole product --- overstock, a return, a site leftover; never installed.
_Avoid_: offcut

**Construction work**:
A building or civil-engineering work a component was deinstalled from or installed into --- never the company involved.
_Avoid_: site, project, building (too narrow: bridges and roads count)

**Exit**:
How a component left circulation: split, merged, installed, recycled, disposed, returned, or lost.
_Avoid_: consumed

**In circulation**:
Having no exit --- available and reservable.
_Avoid_: active, unconsumed

**Reservation**:
A user's hold on a component in circulation, signalling that they intend to use it.

**Re-entry**:
An installed, returned or lost component coming back with a new origin; the previous origin--exit cycle is archived.

**Lineage**:
The split and merge relations between identities. Children inherit their parents' past --- origin, material, trade name, manufacture date, original function --- unless they state their own.

### Evidence and properties

**Evidence**:
An attributable, time-stamped record of one observation or claim about one component, at one test location or on one specimen.
_Avoid_: measurement (for the general case), test result

**Measurement**:
Evidence produced by an instrument --- a rebound-hammer reading set, a core compression test.
_Avoid_: using it for all evidence

**Claim**:
Evidence without an instrument --- an archival document, a visual inspection, an era heuristic, a manufacturer datasheet.

**Attachment**:
A file that belongs to one evidence record and documents it --- a lab report, an inspection photo of one finding. One file may be attached to several records.
_Avoid_: document (unqualified), photo (unqualified)

**Reinforcement layout**:
Evidence stating where the reinforcement bars inside a component run, with their grade and diameter, and on what basis (drawing, scan, exposed bars).
_Avoid_: reinforcements (as snapshot geometry)

**Destructive test**:
A test that damages the component, such as drilling a core; the test itself is the event, and no new snapshot is recorded for the hole.

**Verification**:
Confirmation that evidence is what it claims to be; independent of publishing. The recorder may self-attest their own work; `reviewed` and `accredited` need a second person, never the recorder or a performer.
_Avoid_: validation

**Condition grade**:
An inspector's overall visual judgment of a component in one state, for any material: 3 good, 2 average, 1 poor, 0 unusable as is. Recorded as evidence.
_Avoid_: condition (as a stored field of the snapshot)

**Finding**:
A specific visible defect recorded by a visual inspection --- spalling, cracking, corrosion --- graded by severity, 0 none to 3 severe.
_Avoid_: damage grade

**Property**:
What the catalog concludes about one quantity of a component --- a range, a confidence and the kind of evidence it rests on; always derived, never entered.
_Avoid_: attribute, value

**Source tier**:
The kind of evidence a property rests on, strongest first: destructive, non-destructive, archival, visual, heuristic --- or inherited from a parent.

**Fold**:
The rule that turns a component's published evidence into its properties: the strongest source tier present wins outright.

### Geometry and classification

**Original function**:
What the component was in its previous life, named by IFC element class (beam, slab, plate, ...).
_Avoid_: type, function (unqualified)

**Reuse function**:
The role a component is given in a new design; decided in design tools outside the catalog and never recorded on the component.

**Shape class**:
The shape category of one snapshot --- linear, planar, block, irregular or composite; derived from the geometry.
_Avoid_: type, form

**Frame**:
A snapshot's canonical orientation and size: the smallest box around the component, lying on its largest face with its length along X --- columns stand, length along Z. Stored as a transform from the coordinates the geometry was uploaded in, which are never changed.
_Avoid_: PCA frame, orientation; frame for any other coordinate system (a proxy has a *placement*, a capture a *coordinate system*)

**Proxy**:
A simple primitive (box, prism, cylinder, hull) standing in for a snapshot's shape, together with how far the real shape deviates from it.
_Avoid_: extrusion; bounding box (the frame's box is not a proxy)

**Deviation map**:
An image per proxy face recording how far the real surface departs from the proxy.

**Material**:
The generic material a component is mainly made of, from a controlled list (concrete, fired clay, mineral composite, ...).
_Avoid_: brand names (those are the trade name)

**Material class**:
The EU List of Waste (chapter 17) class of a component's material.

**Trade name**:
The brand or product name of the material, e.g. Corian.
_Avoid_: material

### People and permissions

**Dataset**:
The unit of membership, permission and visibility --- in practice one project or study (ZirKuS, SAS CITA scans). Every identity belongs to exactly one.
_Avoid_: campaign (the study is the dataset; the occasion --- one day's tests --- is stated by each evidence record), collection

**Contributor / Reviewer / Moderator**:
The three dataset roles, held in any combination: a contributor adds components, snapshots and evidence; a reviewer verifies evidence; a moderator publishes, corrects and manages members.

**Admin**:
The global role that holds every privilege in every dataset --- except reviewing a record they recorded or performed (four eyes).

**Invitation**:
A single-use registration code bound to one email address, issued by an admin or a dataset moderator, that lets someone outside the open registration domains create an account, or pre-assigns dataset roles to someone who has no account yet.
_Avoid_: invite code, access code

**Actor**:
A person or organization credited with an act --- who deinstalled, who drilled, who tested, who attested.
_Avoid_: user (a user is an account; an actor need not have one)

### Time

**Valid time**:
When something was true in reality --- a state began, a sample was taken, a result was produced.
_Avoid_: date (unqualified)

**Transaction time**:
When the catalog recorded or changed a record.
