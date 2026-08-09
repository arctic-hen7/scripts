#!/bin/bash
# Opens a temporary Neovim window to allow the user to capture a new entry in the inbox. This
# uniquely adds all files in `$ACE_INBOX_DIR/next/` as attachments, allowing the user to
# manipulate attachments as regular files in a "sink", which is then drained straight into the
# inbox (simpler than having Nautilus scripts etc.).
#
# Requirements:
#   - nvim
#   - $ACE_INBOX_DIR

SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

mkdir -p "$ACE_INBOX_DIR/next"

# If there are files in the attachment sink, confirm with the user (if not, they'll know by the lack
# of a confirmation if they were expecting attachments, and better to keep the interface quick for
# the simple case)
if [ "$(ls -A "$ACE_INBOX_DIR/next"/* 2>/dev/null)" ]; then
    tree -i --noreport "$ACE_INBOX_DIR/next" | tail -n +2
    while true; do
        read -p "Attach the above files? (y/n): " answer
        case $answer in
            [Yy]* )
                break
                ;;
            [Nn]* )
                echo "Please modify the files in '$ACE_INBOX_DIR/next/' and then re-run the capture."
                exit 1
                ;;
            * )
                echo "Please answer y or n."
                ;;
        esac
    done
fi

# Perform the actual capture
read -p "Capture: " capture
if [[ "$capture" == "" ]]; then
    echo "Nothing to capture."
    exit
fi

capture_output="$(echo "$capture" | bash "$SELF_DIR/capture.sh" text "$ACE_INBOX_DIR/next"/*)"

if [ "$(ls -A "$ACE_INBOX_DIR/next"/* 2>/dev/null)" ]; then
    # Get the files we attached
    attached_files="$(echo "$capture_output" | grep "Attached '" | sed -E "s/^Attached '([^']+)'.*$/\1/" | sort)"
    # Get the files we *expected* to be attached
    expected_files="$(find "$ACE_INBOX_DIR/next" -mindepth 1 -maxdepth 1 -print | sort)"
    # If we've got the right ones, delete these
    if [[ "$attached_files" == "$expected_files" ]]; then
        rm -rf "$ACE_INBOX_DIR/next"/*
        echo "Pending attachments cleared."
    else
        echo "Found incorrect attachments!"
        echo "$attached_files"
        echo "---"
        echo "$expected_files"
    fi
fi
