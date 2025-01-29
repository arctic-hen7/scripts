#!/bin/bash
# Gets the master password by prompting the user.
#
# Requirements:
#   - $ACE_KEYRING_DIR
#   - $ACE_PINENTRY

master_pw_file="$ACE_KEYRING_DIR/master.enc"
if [ ! -f "$master_pw_file" ]; then
    echo "Error: master password not set up yet, please run 'setup_master.sh'."
    exit 1
fi

pinentry_res="$(echo -e "SETPROMPT Master Passphrase\nSETDESC Please enter the master passphrase:\nGETPIN\n" | "$ACE_PINENTRY" | tail -n 2)"
# That will either be `D pass\nOK` or `OK\nERR some error`
if [[ $pinentry_res == *OK ]]; then
    pass_line=$(echo "$pinentry_res" | head -n 1)
    pass="${pass_line#D }"

    # Use that pass*phrase* to decrypt the master pass*word*
    master_pw="$(openssl enc -d -in "$master_pw_file" -aes-256-cbc -salt -pbkdf2 -pass fd:3 3<<<"$pass")"

    if [ $? -eq 0 ]; then
        echo "$master_pw"
    else
        echo "Error: incorrect master passphrase."
        exit 1
    fi
else
    echo "Error: failed to get master password."
    exit 1
fi
