#!/bin/sh
# Rebuild the agent's working copy of the notes from fixtures/.
# Run it before each experiment, since the agent can delete notes.
cd "$(dirname "$0")" || exit 1
rm -rf tmp/sample_notes && mkdir -p tmp && cp -R fixtures/base_notes tmp/sample_notes
