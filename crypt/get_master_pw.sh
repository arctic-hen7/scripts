#!/bin/bash
# Gets the master password by prompting the user, with kernel keyring caching.
#
# Requirements:
#   - $ACE_KEYRING_DIR
#   - $ACE_PINENTRY
#   - keyctl (from keyutils package)
#
# To manually clear the cache: keyctl purge user ace-master-pw

# Cache timeout in minutes
CACHE_TIMEOUT_MINUTES=15

MAX_TRIES=3
CACHE_KEY_NAME="ace-master-pw"

master_pw_file="$ACE_KEYRING_DIR/master.enc"
if [ ! -f "$master_pw_file" ]; then
    echo "Error: master password not set up yet, please run 'setup_master.sh'."
    exit 1
fi

# Try to retrieve from kernel keyring cache
set +e
key_id=$(keyctl search @s user "$CACHE_KEY_NAME" 2>/dev/null)
keyctl_search_code=$?
set -e

if [ $keyctl_search_code -eq 0 ]; then
    # Key found in cache, retrieve it
    set +e
    master_pw=$(keyctl print "$key_id" 2>/dev/null)
    keyctl_print_code=$?
    set -e

    if [ $keyctl_print_code -eq 0 ]; then
        # Prompt the user before we do anything more to make sure we don't get
        # phantom ops straight after legitimately authorised ones
        pinentry_res="$(echo -e "SETPROMPT Confirm Key Access\nSETDESC Do you want to allow key access for this operation?\nSETOK Allow\nSETCANCEL Block\nCONFIRM\n" | "$ACE_PINENTRY" | tail -n 2)"
        # We either get `OK\nOK` or `OK\nERR some error`
        if [[ $pinentry_res == *OK ]]; then
            echo "$master_pw"
            exit 0
        else
            echo "Error: user denied key access."
            exit 1
        fi
    fi
fi

# Not in cache, prompt user
num_tries=0
while [ $num_tries -lt $MAX_TRIES ]; do
    if [ $num_tries -gt 0 ]; then
        pinentry_desc="Sorry, that was incorrect. Please try again:"
    else
        pinentry_desc="Please enter the master passphrase:"
    fi

    pinentry_res="$(echo -e "SETPROMPT Master Passphrase\nSETDESC $pinentry_desc\nGETPIN\n" | "$ACE_PINENTRY" | tail -n 2)"
    # That will either be `D pass\nOK` or `OK\nERR some error`
    if [[ $pinentry_res == *OK ]]; then
        pass_line=$(echo "$pinentry_res" | head -n 1)
        pass="${pass_line#D }"

        # Use that pass*phrase* to decrypt the master pass*word*
        master_pw="$(openssl enc -d -in "$master_pw_file" -aes-256-cbc -salt -pbkdf2 -pass fd:3 3<<<"$pass")"

        if [ $? -eq 0 ]; then
            # Successfully decrypted, store in kernel keyring with timeout
            set +e
            key_id=$(echo -n "$master_pw" | keyctl padd user "$CACHE_KEY_NAME" @s 2>/dev/null)
            if [ $? -eq 0 ]; then
                # Set timeout in seconds
                timeout_seconds=$((CACHE_TIMEOUT_MINUTES * 60))
                keyctl timeout "$key_id" "$timeout_seconds" 2>/dev/null
            fi
            set -e

            echo "$master_pw"
            exit 0
        else
            # A wrong passphrase can be re-prompted
            ((num_tries++))
            continue
        fi
    else
        # Propagate a pinentry error immediately
        echo "Error: failed to get master password."
        exit 1
    fi
done
