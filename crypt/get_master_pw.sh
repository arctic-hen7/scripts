#!/bin/bash
# Gets the master password by prompting the user.
#
# Requirements:
#   - $ACE_KEYRING_DIR
#   - $ACE_PINENTRY

MAX_TRIES=3

master_pw_file="$ACE_KEYRING_DIR/master.enc"
if [ ! -f "$master_pw_file" ]; then
    echo "Error: master password not set up yet, please run 'setup_master.sh'."
    exit 1
fi

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
