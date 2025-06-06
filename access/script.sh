#!/bin/bash
# A setup script template that holds both the `rclone` configuration and password, using them to
# download the main mirror to create a working copy of the user's files from the cloud. This
# script should be encrypted with a tool like [Cyst](https://github.com/arctic-hen7/cyst) to
# avoid exposing the `rclone` password.
#
# This should be run from the new ACE directory, which will have the same structure as was used
# in the minting script (all layout environment variables are copied verbatim).
#
# Requirements:
#   - rclone
#   - git

set -e

# Both base64-encoded
RCLONE_CONFIG="{{ rclone_config }}"
RCLONE_CONFIG_PASS="{{ rclone_config_pass }}"

export ACE_DIR="$(pwd)"

# Export all the environment variables later scripts will need
{{ export_commands }}

# Make sure all the directories we need exist and are empty
mkdir -p "$ACE_MAIN_DIR"
mkdir -p "$ACE_MAIN_MIRROR_DIR"
mkdir -p "$ACE_WING_MIRRORS_DIR"
if [ ! -z "$(ls -A "$ACE_MAIN_DIR")" ]; then
    echo "'$ACE_MAIN_DIR' should be empty before proceeding."
    exit 1
fi
if [ ! -z "$(ls -A "$ACE_MAIN_MIRROR_DIR")" ]; then
    echo "'$ACE_MAIN_MIRROR_DIR' should be empty before proceeding."
    exit 1
fi

# Write the `rclone` config to a temporary file
rclone_config_path=$(mktemp)
echo "$RCLONE_CONFIG" | base64 -d > "$rclone_config_path"
export RCLONE_CONFIG_PASS=$(echo "$RCLONE_CONFIG_PASS" | base64 -d)

# Use it to download the main mirror
echo "Downloading main files..."
rclone --config "$rclone_config_path" sync main-crypt:main "$ACE_MAIN_MIRROR_DIR"
rclone --config "$rclone_config_path" sync main-crypt:main/refs/heads "$ACE_MAIN_MIRROR_DIR/refs/heads" -I

rm "$rclone_config_path"

# Now clone that to instantiate the working copy
git clone "$ACE_MAIN_MIRROR_DIR" "$ACE_MAIN_DIR"

echo "Working copy instantiated in '$ACE_MAIN_DIR'! You can integrate the files with the system by running 'source $ACE_MAIN_DIR/layout.sh && bash $ACE_MAIN_DIR/scripts/init.sh'."
