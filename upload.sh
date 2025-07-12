#!/bin/bash
# Uploads the given file/folder to cloud storage with `rclone` and returns a public
# view link that can be shared.
#
# Requirements:
#   - `rclone`
#
# Notes:
#   This script is somewhat specific to my setup, and you may need to change the `rclone`
#   password handling, as well as the remote it pushes to.

set -e

# Get the `rclone` password (unique to my setup)
export RCLONE_CONFIG_PASS="$(pass show securedb/rclone)"
RCLONE_SHARED_REMOTE="shared"

# Parse arguments: we push to each wing by default, and can choose to pull as well or skip entirely.
# Throughout this process, we check the existence of each wing the user defines to make sure we have
# only valid wings in these arrays.
target=""
should_overwrite=false # True -> doesn't ask before overwriting
fail_on_overwrite=false # True -> doesn't ask before *failing* if overwrite needed
while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes-overwrite)
            if ! $fail_on_overwrite; then
                should_overwrite=true
            else
                echo "Error: can't have '--yes-overwrite' and '--no-overwrite' together."
                exit 1
            fi
            shift
            ;;
        -n|--no-overwrite)
            if ! $should_overwrite; then
                fail_on_overwrite=true
            else
                echo "Error: can't have '--yes-overwrite' and '--no-overwrite' together."
                exit 1
            fi
            shift
            ;;
        *)
            if [[ "$target" != "" ]]; then
                echo "Error: unknown option: $1"
                exit 1
            else
                target="$1"
            fi
            shift
            ;;
    esac
done

if [[ "$target" == "" ]]; then
    echo "Error: must specify a file/folder to upload."
    exit 1
fi

target_name="$(basename "$target")"

# Check if the file already exists in shared cloud storage (if we're overwriting though, no need)
if ! $should_overwrite; then
    set +e
    rclone lsf --files-only "$RCLONE_SHARED_REMOTE:$target_name" >/dev/null 2>&1
    result=$?
    set -e
    if [ $result -eq 0 ]; then
        if $fail_on_overwrite; then
            echo "Error: '$target_name' already exists and '--no-overwrite' is set."
            replace=false
        else
            # `-n` is not set (just checked), and neither is `-y` (grandparent condition)
            while true; do
                read -p "'$target_name' already exists in shared cloud storage, would you like to replace it? (y/n): " answer
                case $answer in
                    [Yy]* )
                        replace=true
                        break
                        ;;
                    [Nn]* )
                        replace=false
                        break
                        ;;
                    * )
                        echo "Please answer y or n."
                        ;;
                esac
            done
        fi

        if ! $replace; then
            echo "Aborted."
            exit 1
        fi
    fi
fi

# We're either cleared to replace the file, or it doesn't exist yet
echo "Uploading..."
rclone copyto "$target" "$RCLONE_SHARED_REMOTE:$target_name"
# Grab a public link to it
target_url="$(rclone link "$RCLONE_SHARED_REMOTE:$target_name" | tail -n 1)"
if [ $? -ne 0 ]; then
    echo "Error: failed to get public-view link to uploaded file."
    exit 1
fi

echo ""
echo "$target_url"
