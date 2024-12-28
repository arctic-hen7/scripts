#!/bin/bash
# A setup script template that holds both the `rclone` configuration and password, using them to
# download the main mirror to create a working copy of the user's files from the cloud. This
# script should be encrypted with a tool like [Cyst](https://github.com/arctic-hen7/cyst) to
# avoid exposing the `rclone` password.
#
# This should be run from the new ACE directory, which will have the same structure as was used
# in the minting script (all layout environment variables are copied verbatim).
#
# A setup script template for pushing and pulling to/from the primary directory on a wing device.
# This embeds both the `rclone` configuration and password (if encrypted), and acts as a full
# syncing script. Any initialisation functionality shoudl happen after an initial pull, and can
# be handled by separate user-specific scripts.
#
# Requirements:
#   - rclone

set -e

# Both base64-encoded
RCLONE_CONFIG="{{ rclone_config }}"
RCLONE_CONFIG_PASS="{{ rclone_config_pass }}"
WING_DIR="{{ wing_dir }}"
WING_NAME="{{ wing_name }}"

mkdir -p "$WING_DIR"

if [[ "$1" == "push" ]]; then
    rclone_config_path=$(mktemp)
    echo "$RCLONE_CONFIG" | base64 -d > "$rclone_config_path"
    export RCLONE_CONFIG_PASS=$(echo "$RCLONE_CONFIG_PASS" | base64 -d)

    rclone --config "$rclone_config_path" sync "$WING_DIR" "$WING_NAME-crypt":wing

    rm "$rclone_config_path"
elif [[ "$1" == "pull" ]]; then
    rclone_config_path=$(mktemp)
    echo "$RCLONE_CONFIG" | base64 -d > "$rclone_config_path"
    export RCLONE_CONFIG_PASS=$(echo "$RCLONE_CONFIG_PASS" | base64 -d)

    rclone --config "$rclone_config_path" sync "$WING_NAME-crypt":wing "$WING_DIR"

    rm "$rclone_config_path"
else
    echo "Invalid command '$1', expected 'push' or 'pull'."
fi
