#!/bin/bash
# Dump the production database to stdout, for a backup pulled over ssh.
#
#   csc_dump.sh archive   mongodump archive (gzip), restore with
#                         mongorestore --gzip --archive=<file>
#   csc_dump.sh json      tar.gz of one csc.<collection>.json per collection
#                         (a JSON array in relaxed Extended JSON, like a
#                         Compass export), the layout of mongodb_collections_local
#
# Install: copy to ~/bin/csc_dump.sh, chmod 700. Reads MONGODB_URI from
# ~/etc/services.d/fastapi.ini; writes only to stdout and a temp folder that is
# removed at the end. Progress and errors go to stderr.

set -euo pipefail

INI="$HOME/etc/services.d/fastapi.ini"
PYTHON="$HOME/csc/current/venv/bin/python"

URI=$(grep -o 'MONGODB_URI=[^,]*' "$INI" | head -1 | cut -d= -f2- | tr -d '"\r')
if [ -z "$URI" ]; then
    echo "csc_dump: MONGODB_URI not found in $INI" >&2
    exit 1
fi

case "${1:-}" in
    archive)
        mongodump --uri="$URI" --gzip --archive --quiet
        ;;
    json)
        TMP=$(mktemp -d)
        trap 'rm -rf "$TMP"' EXIT
        CSC_DUMP_URI="$URI" CSC_DUMP_DIR="$TMP" "$PYTHON" - <<'EOF'
import os
import sys

from bson import json_util
from bson.json_util import JSONOptions, JSONMode
from pymongo import MongoClient

client = MongoClient(os.environ['CSC_DUMP_URI'])
db = client.get_default_database(default='csc')
options = JSONOptions(json_mode=JSONMode.RELAXED)
for name in sorted(db.list_collection_names()):
    if name.startswith('system.'):
        continue
    # one document at a time: the server kills a process that holds a large
    # collection in memory
    path = os.path.join(os.environ['CSC_DUMP_DIR'], f'csc.{name}.json')
    count = 0
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('[')
        for doc in db[name].find(batch_size=50):
            if count:
                handle.write(',')
            handle.write(json_util.dumps(doc, json_options=options))
            count += 1
        handle.write(']')
    print(f'{name}: {count}', file=sys.stderr)
EOF
        tar czf - -C "$TMP" .
        ;;
    *)
        echo "usage: csc_dump.sh archive|json" >&2
        exit 2
        ;;
esac
