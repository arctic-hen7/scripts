#!/bin/bash
# Shorthand script for creating and opening the journal for the given date. If this
# isn't given a date, it will open today's journal.
#
# Requirements:
#   - $ACE_JOURNALS_DIR
#   - nvim

set -e
SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

date="$1"
if [[ "$date" == "" ]]; then
    date=$(date +%Y-%m-%d)
fi

bash "$SELF_DIR/create.sh" "$date" | tail -n 1 | xargs nvim
