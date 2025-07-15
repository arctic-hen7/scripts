#!/usr/bin/env python
# Generates a detailed sleep schedule based on a list of "ready by" times.
#
# This script fetches data from a local Starling API endpoint, calculates latest
# sleep/wakeup times based on user-defined constants, and outputs a formatted
# Markdown schedule. It is designed to be run as a personal automation.
#
# --- How to Use ---
# - Run without flags to print the schedule to standard output:
#   $ python3 generate_sleep_schedule.py
#
# - Use -w/--write to intelligently update the target file, preserving any
#   manually entered ideal times and notes where possible:
#   $ python3 generate_sleep_schedule.py -w
#
# - Use -w -r to completely overwrite the schedule in the target file:
#   $ python3 generate_sleep_schedule.py -w -r
#
# --- Configuration ---
# 1. Set the source node ID in `READY_BY_NODE_ID`. This Markdown node should
#    contain a list of dates and times in the following format:
#    - 2025-07-16 Wed: **10:00** Optional notes for the day
#
# 2. Set the output file path in `OUTPUT_FILE_PATH`. The script looks for the
#    `COMPUTED_MARKER` string and replaces all content after it.
#
# 3. Adjust `PREP_TIME_HOURS` and `SLEEP_DURATION_HOURS` to match your needs.
#
# ---
#
# Most of this script was written by Gemini in collaboration with @arctic-hen7.

import argparse
import datetime
import os
import re
import sys
from typing import Dict, List, Optional, Tuple, Any

import requests

# --- Constants ---
# The number of hours you need to get ready in the morning.
PREP_TIME_HOURS = 2.0
# The number of hours you need to sleep.
SLEEP_DURATION_HOURS = 8.25

# Starling API configuration
STARLING_API_BASE = "http://localhost:3000/node"
READY_BY_NODE_ID = "e913953e-eb7d-4295-86c7-2a9cc47fc2ac"
COMPUTED_NODE_ID = "83648637-bf0e-4773-8209-814becadf646"

# File path for writing the output
# Expands the environment variable $ACE_MAIN_DIR
OUTPUT_FILE_PATH = os.path.expandvars("$ACE_MAIN_DIR/gtd/circadian.md")
# The marker in the file to write after
COMPUTED_MARKER = f"""# Computed
<!--PROPERTIES
ID: {COMPUTED_NODE_ID}
-->

"""

# Type alias for our main data structure
ScheduleData = Dict[str, Any]


def fetch_node_body(node_id: str) -> str:
    """Fetches the body of a Starling node."""
    url = f"{STARLING_API_BASE}/{node_id}"
    payload = {"conn_format": "markdown", "body": True}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.get(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get("body", "")
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not connect to Starling API at {url}.", file=sys.stderr)
        print(f"       {e}", file=sys.stderr)
        sys.exit(1)


def parse_ready_by_times(markdown: str) -> List[ScheduleData]:
    """Parses the input Markdown for dates and ready-by times."""
    schedule = []
    # Updated regex to capture optional notes after the bolded time
    pattern = re.compile(r"^- (\d{4}-\d{2}-\d{2} \w{3}): \*\*(\d{1,2}:\d{2})\*\*(.*)")
    for line in markdown.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        
        date_str, time_str, notes_str = match.groups()
        notes = notes_str.strip()

        try:
            ready_by_time = datetime.datetime.strptime(time_str, "%H:%M").time()
            # Store the notes along with the date and time
            schedule.append({
                "date_str": date_str,
                "ready_by": ready_by_time,
                "ready_by_notes": notes,
            })
        except ValueError:
            print(f"Warning: Skipping invalid time format '{time_str}' for date '{date_str}'.", file=sys.stderr)
    return schedule


def parse_existing_schedule(markdown: str) -> Dict[str, ScheduleData]:
    """Parses the existing computed schedule to preserve user-set times."""
    existing_data = {}
    current_day_key = None

    # Regex to capture the time (or '??') and any trailing notes
    time_pattern = re.compile(r"\*\*(.*?)\*\*(.*)")

    def parse_time_value(val_str: str) -> Tuple[Optional[datetime.time], str]:
        # ... (this helper function does not need to be changed)
        val_str = val_str.strip()
        match = time_pattern.match(val_str)
        if not match:
            return None, ""
        
        time_content, notes = match.groups()
        notes = notes.strip()

        if time_content == "??":
            return None, notes
        try:
            return datetime.datetime.strptime(time_content, "%H:%M").time(), notes
        except ValueError:
            return None, notes

    for line in markdown.splitlines():
        # ... (the logic to find the line type does not need to be changed)
        if not line.strip():
            continue
        
        is_indented = line.startswith((' ', '\t'))
        stripped_line = line.strip()

        if not is_indented and stripped_line.startswith("- "):
            # ...
            date_str = stripped_line.split(":", 1)[0][2:].strip()
            if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
                current_day_key = date_str
                existing_data[current_day_key] = {}
            else:
                current_day_key = None
        
        elif is_indented and current_day_key and stripped_line.startswith("-"):
            # ...
            parts = stripped_line.split(":", 1)
            if len(parts) != 2:
                continue

            key_name, value_str = parts
            key_name = key_name.lstrip("- ").strip()

            if key_name == "Ideal wakeup":
                t, n = parse_time_value(value_str)
                existing_data[current_day_key]["ideal_wakeup"] = t
                existing_data[current_day_key]["ideal_wakeup_notes"] = n
            elif key_name == "Ideal sleep":
                t, n = parse_time_value(value_str)
                existing_data[current_day_key]["ideal_sleep"] = t
                existing_data[current_day_key]["ideal_sleep_notes"] = n
            # ADD THIS CASE:
            elif key_name == "Ready by":
                # We only need the notes, not the time (which is recalculated).
                _time, notes = parse_time_value(value_str)
                if notes:
                    existing_data[current_day_key]["ready_by_notes"] = notes
                
    return existing_data


def generate_markdown(schedule: List[ScheduleData]) -> str:
    """Generates the final Markdown output from the schedule data."""
    output = []

    def format_time(t: Optional[datetime.time], notes: str = "") -> str:
        """Formats a time object or '??' into **HH:MM** format with notes."""
        notes_str = f" {notes}" if notes else ""
        if t is None:
            return f"**??**{notes_str}"
        return f"**{t.strftime('%-H:%M')}**{notes_str}"

    for day in schedule:
        output.append(f"- {day['date_str']}:")
        output.append(f"  - Ideal wakeup: {format_time(day.get('ideal_wakeup'), day.get('ideal_wakeup_notes', ''))}")
        output.append(f"  - Latest wakeup: {format_time(day.get('latest_wakeup'))}")
        
        # Pass the ready_by_notes to the formatter
        output.append(f"  - Ready by: {format_time(day['ready_by'], day.get('ready_by_notes', ''))}")
        
        output.append(f"  - Ideal sleep: {format_time(day.get('ideal_sleep'), day.get('ideal_sleep_notes', ''))}")
        output.append(f"  - Latest sleep: {format_time(day.get('latest_sleep'))}")
    
    return "\n".join(output)


def main():
    """Main script execution."""
    parser = argparse.ArgumentParser(
        description="Generate a sleep schedule from 'ready by' times."
    )
    parser.add_argument(
        "-w", "--write", action="store_true",
        help="Write output to file, updating existing values."
    )
    parser.add_argument(
        "-r", "--overwrite", action="store_true",
        help="Completely overwrite the computed section in the file. Requires -w."
    )
    args = parser.parse_args()

    if args.overwrite and not args.write:
        print("Error: -r/--overwrite flag requires -w/--write to be set.", file=sys.stderr)
        sys.exit(1)

    # 1. Fetch and parse the primary "ready by" times
    ready_by_markdown = fetch_node_body(READY_BY_NODE_ID)
    if not ready_by_markdown:
        print("Error: No content found in the 'ready by' node.", file=sys.stderr)
        sys.exit(1)
    
    schedule = parse_ready_by_times(ready_by_markdown)
    if not schedule:
        print("Error: Could not parse any valid 'ready by' times from the input.", file=sys.stderr)
        sys.exit(1)

    # 2. Fetch existing schedule if we are in update mode (-w but not -r)
    existing_data = {}
    if args.write and not args.overwrite:
        existing_markdown = fetch_node_body(COMPUTED_NODE_ID)
        existing_data = parse_existing_schedule(existing_markdown)

    # 3. Perform calculations
    prep_delta = datetime.timedelta(hours=PREP_TIME_HOURS)
    sleep_delta = datetime.timedelta(hours=SLEEP_DURATION_HOURS)
    dummy_date = datetime.date.min

    for i, day in enumerate(schedule):
        # Combine time with a dummy date to perform arithmetic
        ready_by_dt = datetime.datetime.combine(dummy_date, day["ready_by"])

        # Calculate latest wakeup time
        latest_wakeup_dt = ready_by_dt - prep_delta
        day["latest_wakeup"] = latest_wakeup_dt.time()

        # Calculate latest sleep time (based on the *next* day's wakeup)
        day["latest_sleep"] = None
        if i + 1 < len(schedule):
            next_day = schedule[i+1]
            next_ready_by_dt = datetime.datetime.combine(dummy_date, next_day["ready_by"])
            next_latest_wakeup_dt = next_ready_by_dt - prep_delta
            
            # If next day's wakeup is early, it implies going to bed before midnight
            if next_latest_wakeup_dt < datetime.datetime.combine(dummy_date, datetime.time(12, 0)):
                next_latest_wakeup_dt += datetime.timedelta(days=1)
            
            latest_sleep_dt = next_latest_wakeup_dt - sleep_delta
            day["latest_sleep"] = latest_sleep_dt.time()

        # 4. Merge with existing data if applicable
        date_str = day["date_str"]
        if date_str in existing_data:
            old_day = existing_data[date_str]
            # Preserve ideal wakeup if it's still valid
            if old_day.get("ideal_wakeup") and old_day["ideal_wakeup"] <= day["latest_wakeup"]:
                day["ideal_wakeup"] = old_day["ideal_wakeup"]
                day["ideal_wakeup_notes"] = old_day.get("ideal_wakeup_notes", "")
            
            # Preserve ideal sleep, now with midnight-aware comparison
            ideal_sleep_time = old_day.get("ideal_sleep")
            latest_sleep_time = day.get("latest_sleep")

            if ideal_sleep_time and latest_sleep_time:
                # Treat any time after noon as "evening" and before as "morning"
                # to correctly handle schedules that cross midnight.
                split_time = datetime.time(12, 0)
                
                # An evening ideal time is always valid if the latest is in the morning.
                is_valid_across_midnight = (ideal_sleep_time >= split_time and 
                                            latest_sleep_time < split_time)
                
                # Otherwise, a direct comparison is fine.
                is_valid_same_day = (ideal_sleep_time <= latest_sleep_time)

                if is_valid_across_midnight or is_valid_same_day:
                    day["ideal_sleep"] = ideal_sleep_time
                    day["ideal_sleep_notes"] = old_day.get("ideal_sleep_notes", "")

            # Prefer notes from the existing computed schedule over the source.
            if old_day.get("ready_by_notes"):
                day["ready_by_notes"] = old_day["ready_by_notes"]

    # 5. Generate and output the final markdown
    final_markdown = generate_markdown(schedule)

    if args.write:
        try:
            with open(OUTPUT_FILE_PATH, "r") as f:
                content = f.read()
            
            marker_pos = content.find(COMPUTED_MARKER)
            if marker_pos == -1:
                print(f"Error: Could not find the marker in {OUTPUT_FILE_PATH}", file=sys.stderr)
                sys.exit(1)
            
            # Get the position right after the marker and its trailing newlines
            insertion_point = marker_pos + len(COMPUTED_MARKER)
            final_content = content[:insertion_point] + final_markdown

            with open(OUTPUT_FILE_PATH, "w") as f:
                f.write(final_content)
            print(f"Successfully updated {OUTPUT_FILE_PATH}")

        except FileNotFoundError:
            print(f"Error: Output file not found at {OUTPUT_FILE_PATH}", file=sys.stderr)
            sys.exit(1)
    else:
        print(final_markdown)

if __name__ == "__main__":
    main()
