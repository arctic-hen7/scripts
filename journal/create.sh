#!/bin/bash
# Simple script that ensures the journal file for the given date exists and has the correct
# headings for later programmatic manipulation. This can be given year, month, and day dates,
# and Sundays will include weekly journal headings automatically.
#
# Requirements:
#   - $ACE_JOURNALS_DIR: the directory containing daily journal files

set -e

# Function to check if a date is a Sunday
is_sunday() {
    day_of_week=$(date -d "$1" +%u)
    if [ "$day_of_week" -eq 7 ]; then
        return 0
    else
        return 1
    fi
}

YEAR_TEMPLATE="---
title: YEAR
---

# Yearly Journal Entry

PLACEHOLDER"

MONTH_TEMPLATE="---
title: MONTH
---

# Monthly Journal Entry

PLACEHOLDER"

DAY_TEMPLATE="---
title: DAY
---

# Tasks
# Daily Journal Entry

PLACEHOLDER

# Gratitude Journal

1.
2.
3.

# Goals for Tomorrow

-"

SUNDAY_APPEND="

# Weekly Journal Entry

PLACEHOLDER

# Goals for Next Week
-"

# Read the date string
date_string="$1"

# Check the format of the date string
path=""
template=""

if [[ "$date_string" =~ ^[0-9]{4}$ ]]; then
    year="$date_string"
    template=${YEAR_TEMPLATE//YEAR/$date_string}
elif [[ "$date_string" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    year="${date_string%-*}"
    month="${date_string#*-}"
    path="$ACE_JOURNALS_DIR/$year/$month/index.md"
    template=${MONTH_TEMPLATE//MONTH/$date_string}
elif [[ "$date_string" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    year="${date_string:0:4}"
    month="${date_string:5:2}"
    day="${date_string:8:2}"
    path="$ACE_JOURNALS_DIR/$year/$month/$day.md"
    template=${DAY_TEMPLATE//DAY/$date_string}
    if is_sunday "$date_string"; then
        template+="$SUNDAY_APPEND"
    fi
else
    echo "Invalid date format."
    exit 1
fi

# Check if the journal path exists and has non-whitespace content
if [ ! -s "$path" ] || [[ -z $(tr -d '[:space:]' < "$path") ]]; then
    # Create directory if it doesn't exist
    mkdir -p "$(dirname "$path")"

    # Write the template to the file
    echo -e "$template" > "$path"
    echo "Journal file for $date_string created."
    echo "$path"
else
    echo "Journal file for $date_string already exists."
    echo "$path"
fi
