#!/bin/bash
# Creates a new Zettelkasten note, prompting the user for a name, which will
# be converted into a filename.
#
# Requirements:
#   - $ACE_ZK_DIR

set -e

read -p "Enter the title of this note: " title
# Remove special characters, lowercase, and convert spaces to underscores
title_parsed=$(echo "$title" | sed 's/[^a-zA-Z0-9 ]//g' | tr ' ' '_' | tr '[:upper:]' '[:lower:]')

mkdir -p "$ACE_ZK_DIR"

if [ -f "$ACE_ZK_DIR/$title_parsed.md" ]; then
    echo "Note already exists!"
    exit 1
fi

echo -e "---\ntitle: $title\n---" > "$ACE_ZK_DIR/$title_parsed.md"
nvim "$ACE_ZK_DIR/$title_parsed.md"
