#!/bin/bash
# A custom pinentry script that allows working with many GPG keys using a single master password.
# The keys must be registered in `$ACE_KEYRING` under their email key ID, followed by `.enc`. If
# the GPG agent is being used to handle SSH keys, provided their keygrips are under
# `$GNUPGHOME/sshcontrol`, this will also work for them. Any more complex tasks will be delegated
# to the system pinentry. In essence, you will only notice this program when it has something it
# knows it can do.
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
#   - gpg
#   - ssh-keygen (if using SSH keys)
#   - Bash >4 (for `coproc` support)

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

# Set up a coprocess so we can work with the system pinentry
coproc SYS_PINENTRY ( "$ACE_PINENTRY" "$@" )
SYS_PINENTRY_STDIN="${SYS_PINENTRY[1]}"
SYS_PINENTRY_STDOUT="${SYS_PINENTRY[0]}"
send_and_receive() {
    if [ ! -z "$1" ]; then
        # Send the single command line
        echo "$1" >&"$SYS_PINENTRY_STDIN"
    fi

    # Wait for as many lines as the server needs to send (ending with `OK` or `ERR`)
    local response_line
    while IFS= read -r response_line <&"$SYS_PINENTRY_STDOUT"; do
        echo "$response_line"

        # The Assuan protocol will stop sending lines through with `OK` or `ERR`
        if [[ "$response_line" == OK* || "$response_line" == ERR* ]]; then
            break
        fi
    done
}

# It will start with an `OK` message, so read first
send_and_receive
# The Assuan protocol does not yet support multiline client requests, so we will expect a single
# line from our own stdin for communication
intercept_getpin=false
intercept_complete=false
key_id=""
while IFS= read -r line; do
    # Before sending the command through, intercept to check for key cascading
    case "$line" in
        # The description of the prompt may contain key IDs if the user is being prompted for a
        # particular key's password (which we might be able to handle)
        SETDESC*)
            set +e
            # SSH keys are special: we get the SSH identifier for them and have to match it
            if echo "$line" | grep -q "ssh key"; then
                ssh_key_id="$(echo "$line" | grep -o 'SHA256:[^%]*')"
                key_id="$(match_ssh_key "$ssh_key_id")"
            else
                # Otherwise we'll get the email from inside angular brackets
                key_id=$(echo "$line" | grep -oP '(?<=<).*?(?=>)')
            fi
            set -e

            # If a corresponding file exists, we can use the master password to decrypt the key
            if [ -f "$ACE_KEYRING_DIR/$key_id.enc" ]; then
                intercept_getpin=true
            fi

            if ! $intercept_complete; then
                send_and_receive "$line"
            else
                echo "OK"
            fi
            ;;
        GETPIN*)
            if $intercept_getpin; then
                # We have up to now maintained a connection with the system pinentry, which we
                # no longer need
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

                # Don't send any future commands to the system pinentry, handle them with our shim
                intercept_complete=true
            else
                send_and_receive "$line"
            fi
            ;;
        *)
            if ! $intercept_complete; then
                send_and_receive "$line"
            else
                # Good general response
                echo "OK"
            fi
            ;;
    esac
done

exec {SYS_PINENTRY[0]}<&-
exec {SYS_PINENTRY[1]}>&-
