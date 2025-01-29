#!/bin/bash
# Decrypts a key in the `openssl`-encrypted keyring using the master passphrase. This is called
# by the custom GPG pinentry script, but can also be used manually to create similar central
# authentication processes.
#
# Requirements:
#   - $ACE_KEYRING_DIR
#   - openssl

set -e
SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

key_id="$1"

if [[ "$key_id" != "" ]]; then
    if [ -f "$ACE_KEYRING_DIR/$key_id.enc" ]; then
        set +e
        # Get the master password
        master_pw="$(bash "$SELF_DIR/get_master_pw.sh")"
        master_pw_code=$?
        if [ $master_pw_code -ne 0 ]; then
            echo "Error: failed to get master password"
            exit 1
        fi
        password="$(openssl enc -d -in "$ACE_KEYRING_DIR/$key_id.enc" -aes-256-cbc -salt -pbkdf2 -pass fd:3 3<<<"$master_pw")"

        if [ $? -eq 0 ]; then
            echo "$password"
        else
            echo "Error: failed to decrypt key"
            exit 1
        fi
    else
        echo "Error: unknown/unregistered key ID"
        exit 1
    fi
else
    echo "Error: no key ID specified"
    exit 1
fi
