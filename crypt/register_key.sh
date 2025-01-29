#!/bin/bash
# Registers a new key into the `openssl`-encrypted keyring. This will allow the key's passphrase
# to be automatically retrieved by the pinentry script.
#
# Registers a new key into the `openssl`-encrypted keyring. This is designed to be called for each
# key in the GPG keyring, allowing them to all be decrypted with a master passphrase, but this
# could also be used for other keys.
#
# Requirements:
#   - $ACE_KEYRING_DIR
#   - openssl

set -e
SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

# Ensure a key ID is provided
if [ -z "$1" ]; then
    echo "Usage: register_key.sh <key-id>"
    exit 1
fi

key_id=$1
output_file="$ACE_KEYRING_DIR/${key_id}.enc"

# Prompt for the passphrase for this key
read -sp "Enter passphrase for ${key_id}: " passphrase
echo

set +e
master_pw="$(bash "$SELF_DIR/get_master_pw.sh")"
master_pw_code=$?
if [ $master_pw_code -ne 0 ]; then
    echo "Error: failed to get master pass."
    exit 1
fi

# Encrypt the passphrase for this key using the master password
echo -n "$passphrase" | openssl enc -aes-256-cbc -salt -pbkdf2 -out "$output_file" -pass fd:3 3<<<"$master_pw"

if [ $? -eq 0 ]; then
    echo "Key registered."
    exit 0
else
    echo "Failed to register key!"
    exit 1
fi
