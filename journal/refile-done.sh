#!/bin/bash
# Refiles the node with the given ID from wherever it is in the Starling system to the daily
# journal file to record it as done.

set -e

SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

if [ ! $# -ge 1 ]; then
    echo "Usage: bash refile-done.sh <node-id>"
    exit 1
fi

id="$1"
target_date="$2"
if [[ "$target_date" == "" ]]; then
    target_date="$(date +"%Y-%m-%d")"
fi

# Make sure the relevant journal file is ready (i.e. has a *Tasks* heading)
bash "$SELF_DIR/create.sh" "$target_date"

# Use Starling to get the ID of the root in the journal file
date_path="${target_date//-/\%2F}"
root_id=$(curl -sX GET "http://localhost:3000/root-id/journals%2F$date_path.md" | jq -r .)
# Then use that root ID to get the child *Tasks* ID
tasks_id=$(curl -sX GET "http://localhost:3000/node/$root_id" -H "Content-Type: application/json" -d '{"conn_format": "markdown", "children": true}' | jq -r '.children[] | select(.[1] == "Tasks") | .[0]')

