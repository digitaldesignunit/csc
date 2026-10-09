"""
The 0.5 -> 0.6 data migration (data model spec section 8.1, plan P2).

``mappings`` holds the pure functions (unit-tested without a database),
``steps`` applies them in run order. Command line:
``scripts/db_maintenance/migrate_06.py``; rehearsal on a local dump:
``scripts/db_maintenance/rehearse_06.py`` (``invoke rehearse``).
"""
