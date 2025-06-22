#!/bin/bash
# A script for preparing a public folder from a local one and syncing it to some cloud service.
# This is backed by `rclone` and uses `rsync`-style inclusion/exclusion files to determine what
# should be synced, while allowing a preparation script to pre-process files (e.g. to convert
# Markdown to PDF). When run in a given directory, it will check for the existence of
# `.publish.conf.d/`, which should contain a directory `targets/`. In there, there should be a
# configuration file for each sync target specifying what to include/exclude (e.g. `gdrive.conf`),
# and a `prep.sh` script that pre-processes everything. This script will be called with two
# arguments: an absolute path to the input directory (where *this* script is run from), and an
# absolute path to a temporary output directory. It is this temporary output directory that the
# `rsync`-style filter files will be computed against, and passing files will be synchronised.
#
# The `rclone` remote to use for syncing should be a directory to which each file in the temporary
# output directory that passes the filter will be synced, and it will be determined for a given
# target by the `.publish.conf.d/remotes/<target-name>` file, which should contain an `rclone` path
# to sync to (e.g. `gdrive:some/folder/`). This path will be quoted, so can contain spaces, and
# whether it has a trailing slash or not doesn't matter.
#
# Requirements:
#   - `rsync`
#   - `rclone`

set -e

INPUT_DIR="$(pwd)"
TARGETS_DIR="$INPUT_DIR/.publish.conf.d/targets"
REMOTES_DIR="$INPUT_DIR/.publish.conf.d/remotes"
PREP_SCRIPT="$INPUT_DIR/.publish.conf.d/prep.sh"

if [ ! -d "$INPUT_DIR/.publish.conf.d" ]; then
    echo "Error: '.publish.conf.d/' not found, please configure this directory for syncing."
    exit 1
fi

# Build a list of all the targets from known config files
all_targets=()
for config_file in "$TARGETS_DIR"/*.conf; do
    # This avoids checking `*.conf` if there are no targets
    [ -e "$config_file" ] || continue

    target_name=$(basename "$config_file" .conf)
    all_targets+=("$target_name")

    # Make sure there's a corresponding remote
    if [ ! -f "$REMOTES_DIR/$target_name" ] || [[ $(wc -l < "$REMOTES_DIR/$target_name") -ne 1 ]]; then
        echo "Error: target '$target_name' does not have a valid associated rclone remote ('$REMOTES_DIR/$target_name' should contain a single line for it)."
        exit 1
    fi
done

# If this stays empty, we'll just prepare, otherwise we'll sync too
sync_target=""
if [[ "$1" == "prep" ]]; then
    sync_target=""
elif [[ "$1" == "sync" ]]; then
    if [[ -n "$2" ]] && [[ " ${all_targets[@]} " =~ " $2 " ]]; then
        sync_target="$2"
    elif [[ -n "$2" ]]; then
        echo "Error: unknown sync target '$2'."
        exit 1
    else
        echo "Error: 'sync' requires a target to sync to."
        exit 1
    fi
else
    echo "Error: unknown command (expected 'prep' or 'sync')."
    exit 1
fi

# If we got here, we'll prepare regardless
OUTPUT_DIR="$(mktemp -d)"
if [ -f "$PREP_SCRIPT" ]; then
    echo "Running prep script..."
    bash "$PREP_SCRIPT" "$INPUT_DIR" "$OUTPUT_DIR"
    if [ $? -ne 0 ]; then
        echo "Error: prep script exited with non-zero status code."
        exit 1
    fi
    echo "Prep script completed successfully, output available in '$OUTPUT_DIR'."
else
    # No prep script, copy everything except `.publish.conf.d/`
    echo "Warning: no prep script found (should be called '.publish.conf.d/prep.sh')."
    rsync -a --exclude='.publish.conf.d/' "$INPUT_DIR/" "$OUTPUT_DIR/"
fi

if [[ "$sync_target" != "" ]]; then
    # Get the `rclone` password (unique to my setup)
    # NOTE: Most people will need to change this!
    export RCLONE_CONFIG_PASS="$(pass show securedb/rclone)"

    # We know the remote exists, grab it
    remote="$(cat "$REMOTES_DIR/$sync_target" | head -n 1)"
    # Now use `rsync` to filter everything into yet another folder
    SYNC_DIR="$(mktemp -d)"
    rsync -a --delete --filter="merge $TARGETS_DIR/$sync_target.conf" "$OUTPUT_DIR/" "$SYNC_DIR/"
    # And finally sync *that* with `rclone`
    echo "Syncing to '$target_name'..."
    rclone sync "$SYNC_DIR" "$remote"

    # And now clean up
    rm -rf "$SYNC_DIR"
    rm -rf "$OUTPUT_DIR"

    echo "Sync complete!"
fi
