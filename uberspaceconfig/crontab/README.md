# Uberspace Crontab

- `crontab.example` is the complete production crontab of CSC: the geometry
  runner, the component map, user maintenance and geometry maintenance. On
  Uberspace they are all in one crontab.
- To install it, open the editor with `crontab -e` in the ssh shell and paste
  the whole file; it replaces the whole crontab (`crontab -l > ~/crontab.backup`
  first, if the server has lines of its own).
- The first line is `MAILTO="<maintainer email>"` and applies to all the lines
  after it: put the real address only in the server's crontab, never in this
  repository.
- The two heavy jobs (geometry runner, component map) share the lock
  `/tmp/csc_heavy.lock`, so they never run together: the runner skips a run while
  the lock is held (`flock -n`), the map waits up to 15 minutes (`flock -w 900`).
- Adjust timings if you deem it necessary; the file has LF line endings
  (`.gitattributes`), keep them.
- A `.crontab` file in this folder is a local copy for the maintainer and is
  ignored by git (`.gitignore`).
