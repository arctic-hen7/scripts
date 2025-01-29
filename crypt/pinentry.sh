#!/bin/bash
# A custom pinentry script that allows working with many GPG keys using a single master password.
# The keys must be registered in `$ACE_KEYRING` under their email key ID, followed by `.enc`.
#
# This can be used for GPG keys by adding the following to `$GNUPGHOME/gpg-agent.conf`:
#
# ```text
# pinentry-program /path/to/this/dir/crypt/pinentry.sh
# ```
#
# Requirements:
#   - $ACE_KEYRING_DIR
#   - openssl

set -e
SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

# Always need to open with this
echo "OK Pleased to meet you"

key_id=""
while IFS= read -r line; do
    case "$line" in
        SETDESC*)
            # Extract key ID from SETDESC (the email-form ID is in angular brackets)
            key_id=$(echo "$line" | grep -oP '(?<=<).*?(?=>)')
            echo "OK"
            ;;
        GETPIN)
            # Decrypt the file containing the key's passphrase in `$ACE_KEYRING`, using the master
            # password
            set +e
            result="$(bash "$SELF_DIR/decrypt_key.sh" "$key_id")"
            resultcode=$?
            set -e
            if [ $resultcode -eq 0 ]; then
                echo "D $result"
                echo "OK"
            else
                # Turns `Error: some message` -> `Some message`
                err=$(echo "$result" | sed -E 's/Error: (.*)/\1/' | awk '{print toupper(substr($1,1,1)) tolower(substr($1,2)) " " substr($0, index($0,$2))}')
                echo "ERR $err"
            fi
            exit 0
            ;;
        BYE)
            # Cleanly exit when BYE is received
            exit 0
            ;;
        *)
            # For all other commands, respond with OK or ignore
            echo "OK"
            ;;
    esac
done
