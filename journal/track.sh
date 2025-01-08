#!/bin/bash
# Wrapper script for a Birocrat script that asks questions about my day and produces a JSON
# object containing my answers. This can be used for habit tracking, confirming beliefs about
# how you feel in certain situations empirically, etc. Generally, this is a life tracking tool
# which I find very useful for making informed decisions.
#
# This takes the same date argument as `create.sh`, and produces a file like `2025-01-01.json`.
# It does *not* support tracking metrics for months or years, only days.
#
# Requirements:
#   - $ACE_JOURNALS_DIR: the directory containing daily journal files
#   - $ACE_LIFE_TRACKING_SCRIPT: the location of the Birocrat Lua script used for life tracking
#   - birocrat

set -e

# Read the date string
date_string="$1"

# Check the format of the date string
path=""

if [[ "$date_string" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    year="${date_string:0:4}"
    month="${date_string:5:2}"
    day="${date_string:8:2}"
    path="$ACE_JOURNALS_DIR/$year/$month/$day.json"
else
    echo "Invalid date format, this script only accepts full dates."
    exit 1
fi

# Check if the file already exists and is populated
if [ ! -s "$path" ] || [[ -z $(tr -d '[:space:]' < "$path") ]]; then
    # Create directory if it doesn't exist
    mkdir -p "$(dirname "$path")"

    # Ask the user questions
    result="$(birocrat "$ACE_LIFE_TRACKING_SCRIPT")"

    # Write the template to the file
    echo -e "$result" > "$path"
    echo "Tracker file for $date_string created."
else
    echo "Tracker file for $date_string already exists."
fi
