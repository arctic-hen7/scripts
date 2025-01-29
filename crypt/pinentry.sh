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

# Matches an SSH key ID with a GPG key's email
match_ssh_key() {
    SSH_KEY_ID="$1"

    # Read keygrips from sshcontrol
    keygrips=$(cat "$GNUPGHOME/sshcontrol")

    # Loop through each keygrip and find the corresponding GPG key
    while IFS= read -r keygrip; do
        # Get the GPG key ID and its email associated with this keygrip
        gpg_info=$(gpg -K --with-keygrip --with-colons 2>/dev/null | awk -v grip="$keygrip" -F: '
        $1 == "sec" { sec = $5 }
        $1 == "ssb" { ssb = $5 }
        $1 == "uid" { uid = $10 }
        $1 == "grp" && $10 == grip { print (sec ? sec : ssb), uid }
        ')

        # Extract GPG key ID and email
        gpg_key_id=$(echo "$gpg_info" | awk '{print $1}')
        email=$(echo "$gpg_info" | grep -oE '<[^>]+>' | tr -d '<>')

        if [ -n "$gpg_key_id" ]; then
            # Export the SSH public key and generate its fingerprint
            ssh_fingerprint=$(gpg --export-ssh-key "$gpg_key_id" | ssh-keygen -lf /dev/stdin 2>/dev/null | awk '{print $2}')

            # Check if this fingerprint matches the given SSH key ID
            if [[ "$ssh_fingerprint" == "$SSH_KEY_ID" ]]; then
                echo "$email"
                return
            fi
        else
            echo "ERR GPG key info extraction failed (this is a bug)"
            exit 1
        fi
    done <<< "$keygrips"

    echo "ERR No matching GPG key for given SSH key"
    exit 1
}

# Always need to open with this
echo "OK Pleased to meet you"

key_id=""
while IFS= read -r line; do
    case "$line" in
        SETDESC*)
            if echo "$line" | grep -q "ssh key"; then
                # SSH keys are specially prompted for
                ssh_key_id="$(echo "$line" | grep -o 'SHA256:[^%]*')"
                set +e
                key_id="$(match_ssh_key "$ssh_key_id")"
                set -e
            else
                # Extract key ID from SETDESC (the email-form ID is in angular brackets)
                key_id=$(echo "$line" | grep -oP '(?<=<).*?(?=>)')
            fi
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
