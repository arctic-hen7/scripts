#!/bin/bash
# A script that captures its stdin to a `README.md` or `HEARME.mp4` in a new directory in
# `$ACE_INBOX_DIR`. The first argument should be either `text` (if text is being piped through
# stdin) or `audio` (if an audio file is being piped), and any other arguments should be files
# or directories, which will be copied into the new capture folder. That folder will be named
# according to a generated UUID, and can then be synchronised through the cloud.
#
# The intended use of this system is to share this script with wing devices and then synchronise
# their captures to the main system, where they can all be handled with `process.py`.
#
# Requirements:
#   - $ACE_INBOX_DIR

set -e

mkdir -p "$ACE_INBOX_DIR"

comment_file=""
comment_source=""
if [[ "$1" == "text" ]]; then
    # Source *is* stdin
    comment_source="-"
    comment_file="README.md"
elif [[ "$1" == "audio" ]]; then
    # Source is the audio file whose name was given through stdin
    comment_source="$(cat)"
    comment_file="HEARME.mp4"
else
    echo "Invalid stdin type, expected 'text' or 'audio' as the first argument."
    exit 1
fi

id="$(uuidgen)"
mkdir "$ACE_INBOX_DIR/$id"

# Any other arguments are attachments
for arg in "${@:2}"; do
    # Check if the argument is a valid file
    if [ -e "$arg" ]; then
        # Copy the file to the target directory
        cp -r "$arg" "$ACE_INBOX_DIR/$id"
        echo "Attached '$arg'."
    else
        echo "Warning: '$arg' is not a valid file."
    fi
done

# Do this last to make sure we don't have any conflicting attachments override the comment
cat "$comment_source" > "$ACE_INBOX_DIR/$id/$comment_file"

echo "Capture complete!"
