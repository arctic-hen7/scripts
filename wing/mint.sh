#!/bin/bash
# Requirements:
#   - cyst
#   - $RCLONE_WING_CONFIG_PASS: the password for the wing `rclone` configuration (if it's encrypted)
#   - $ACE_WINGS_CONFIG_DIR: the directory containing `.conf` files for each wing

set -e

SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

if [ ! $# -eq 3 ]; then
    echo "Usage: bash mint.sh <wing-name> <wing-dir> <output>"
    exit 1
fi

wing_name="$1"
wing_dir="$2"
output="$3"

rclone_conf=$(cat "$ACE_WINGS_CONFIG_DIR/$wing_name.rclone.conf" | base64 -w 0)
rclone_pass=$(echo "$RCLONE_WING_CONFIG_PASS" | base64 -w 0)
script_template=$(cat "$SELF_DIR/script.sh")

script_template=${script_template/\{\{ rclone_config \}\}/$rclone_conf}
script_template=${script_template/\{\{ rclone_config_pass \}\}/$rclone_pass}
script_template=${script_template/\{\{ wing_name \}\}/$wing_name}
script_template=${script_template/\{\{ wing_dir \}\}/$wing_dir}

decrypted_path="$(mktemp)"
echo "$script_template" > "$decrypted_path"

echo "You will now be prompted to set up the encryption on this wing script."
cyst encrypt "$decrypted_path" -o "$output"
rm "$decrypted_path"
