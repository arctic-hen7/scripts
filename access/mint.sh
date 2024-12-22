#!/bin/bash
# Requirements:
#   - cyst
#   - $RCLONE_CONFIG_PASS: the password for the `rclone` configuration (if it's encrypted)
#   - $ACE_DIR: the root ACE directory (all other paths in ACE should be relative to this)
#   - $ACE_SYMLINKS_CONFIG: location of the symlinks config
#   - $ACE_PACKAGES_DIR: the directory where package configs can be found
#   - $ACE_REPOS_CONFIG: the path to the 'repos.toml' file
#   - $ACE_REPOS_DIR: the directory where repositories are stored
#   - $ACE_MAIN_DIR: the directory of the main repo for syncing
#   - $ACE_MAIN_MIRROR_DIR: the bare Git repo that's a remote of the main rpeo
#   - $ACE_WING_MIRRORS_DIR: the directory containing the wing mirrors
#   - $ACE_WINGS_CONFIG_DIR: the directory containing `.conf` files for each wing

set -e

SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

if [ ! $# -eq 1 ]; then
    echo "Please provide an output path."
    exit 1
fi

# Find every single `$ACE_*` environment variable that's a path and get them all relative
# to `$ACE_DIR` (ignoring that one itself). This allows us to set the directory layout
# inside the access script, inferring `$ACE_DIR` from where it's executed. That way, the user
# doesn't need to provide a dozen environment variables.
for var in $(compgen -v | grep '^ACE_'); do
    # Skip ACE_DIR itself
    if [ "$var" == "ACE_DIR" ]; then
        continue
    fi

    # Get the value of the environment variable
    value="${!var}"

    # Check if it's a valid path
    if [ -e "$value" ]; then
        # Get the relative path
        relative_path=$(realpath --relative-to="$ACE_DIR" "$value")

        # Add to the export commands string
        export_commands+="export $var=\"\$ACE_DIR/$relative_path\"\n"
    fi
done
formatted_export_commands=$(printf '%s\n' "$export_commands")

output="$1"

rclone_conf=$(cat "$HOME/.config/rclone/rclone.conf" | base64 -w 0)
rclone_pass=$(echo "$RCLONE_CONFIG_PASS" | base64 -w 0)
script_template=$(cat "$SELF_DIR/script.sh")

script_template=${script_template/\{\{ rclone_config \}\}/$rclone_conf}
script_template=${script_template/\{\{ rclone_config_pass \}\}/$rclone_pass}
# This handles the multi-line export commands properly
script_template=$(awk -v commands="$export_commands" '
{
  gsub(/\{\{ export_commands \}\}/, commands)
}
1' <<< "$script_template")

decrypted_path="$(mktemp)"
echo "$script_template" > "$decrypted_path"

echo "You will now be prompted to set up the encryption on this access script."
cyst encrypt "$decrypted_path" -o "$1"
rm "$decrypted_path"
