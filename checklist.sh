#!/bin/bash
# Reprompts the user to select every item on a checklist until they have.
#
# Requirements:
#   - gum

# Use a hash table to store the items as keys
declare -A items
# Read each line from `stdin` into the set, skipping comments and empty lines
while IFS= read -r line; do
    if [[ -n $line && $line != \#* ]]; then
        items["$line"]=1
    fi
done

# Loop until the user has selected everything
while [ ${#items[@]} -gt 0 ]; do
    # Prompt the user; their choices will be returned on separate lines
    choices="$(gum choose --no-limit "${!items[@]}")"
    # Remove the things they chose from the set
    while IFS= read -r line; do
        unset items["$line"]
    done <<< "$choices"
done
