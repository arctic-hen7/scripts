#!/bin/bash
# Sets up the master password for the first time, or rolls it over to a new passphrase
# otherwise. Because we use a passphrase-decrypts-password structure, changing the master passphrase
# does not require re-encrypting anything, that's a separate process.
#
# Requirements:
#   - $ACE_KEYRING_DIR
#   - $ACE_PINENTRY

set -e

getpin() {
    title="$1"
    desc="$2"

    pinentry_res="$(echo -e "SETPROMPT $title\nSETDESC $desc\nGETPIN\n" | "$ACE_PINENTRY" | tail -n 2)"
    # That will either be `D pass\nOK` or `OK\nERR some error`
    if [[ $pinentry_res == *OK ]]; then
        pass_line=$(echo "$pinentry_res" | head -n 1)
        pass="${pass_line#D }"
        echo "$pass"
    else
        echo "Error: failed to get master password."
        exit 1
    fi
}

# Check if there's an old passphrase, and use that to get the underlying pass*word*, otherwise generate
# a new one
if [ -f "$ACE_KEYRING_DIR/master.enc" ]; then
    old_pass="$(getpin "Old Master Passphrase" "Please enter the previous master passphrase:")"
    master_pw="$(openssl enc -d -in "$ACE_KEYRING_DIR/master.enc" -aes-256-cbc -salt -pbkdf2 -pass fd:3 3<<<"$old_pass")"
else
    master_pw="$(openssl rand -base64 32)"
fi

# Prompt for the first time
pass1="$(getpin "Master Passphrase" "Please enter a passphrase to use for decrypting all your keys:")"
pass2="$(getpin "Master Passphrase" "Please re-enter the master passphrase to confirm:")"
if [[ "$pass1" == "$pass2" ]]; then
    master_pass="$pass1"

    echo -n "$master_pw" | openssl enc -aes-256-cbc -salt -pbkdf2 -out "$ACE_KEYRING_DIR/master.enc" -pass fd:3 3<<<"$master_pass"
    echo "New master passphrase saved."
else
    echo "Master passphrases do not match!"
    exit 1
fi
