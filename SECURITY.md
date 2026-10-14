# Security Policy

## Supported versions

Only the version running on https://2ndchances.build (shown at `https://api.2ndchances.build/version`) and the
Grasshopper interface of the latest GitHub release receive security fixes. Older releases are not patched; update
with `CSC_Update` or the latest release bundle.

## Reporting a vulnerability

Please do **not** open a public issue, pull request or discussion for a vulnerability.

- Use GitHub's private vulnerability reporting: "Report a vulnerability" on the Security tab of this repository.
- If that is not available to you, write to the contact address in the imprint (https://2ndchances.build/imprint).

Please include what is affected (website, API, Grasshopper interface, deployment), how to reproduce it, and what an
attacker could do with it. Do not include real passwords, tokens or other people's personal data; a description of
where they appear is enough.

## What to expect

- We confirm the report as soon as we can, usually within a week.
- We assess it, fix it in a patch release and tell you when the fix is deployed.
- We credit you in the release notes if you wish.

CSC is a research prototype maintained by a small team; there is no bug bounty.

## Good faith

Testing against the live catalogue must not harm it or its users: no denial of service, no access to or change of
data that is not yours, no social engineering, and stop as soon as you reach personal data. Prefer a local instance
(see "Local development and tests" in the README). We will not pursue reports made in good faith under these rules.
