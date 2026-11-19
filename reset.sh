#!/bin/sh
# Rebuild tmp/, the agent's working copy of the notes, from fixtures/.
# Run it before every manual test: the agent can delete notes.
#
#   ./reset.sh                           only the base notes
#   ./reset.sh lisbona-consigli-marta    base notes + these notes from fixtures/injections/

cd "$(dirname "$0")" || exit 1
rm -rf tmp && cp -R fixtures/base_notes tmp

for note in "$@"; do
    src="fixtures/injections/$note.md"
    if [ ! -f "$src" ]; then
        echo "reset.sh: injection not found: $src" >&2
        exit 1
    fi
    cp "$src" tmp/
    echo "added injection: $note"
done
