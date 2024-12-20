#!/bin/bash
# Simple script that reads a config file full of symlinks to create and creates each one. This is
# designed to instantiate a system or update the cache of symlinks. Any existing correct symlinks
# will be skipped, and any incorrect ones or existing files will be skipped with an error.
#
# Requirements:
#   - $ACE_SYMLINKS_CONFIG: location of the symlinks config

while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.* ]] && continue
    [[ -z "$line" ]] && continue

    # Check for --sudo flag and extract paths
    if [[ "$line" =~ --sudo ]]; then
        use_sudo=true
        line="${line/ --sudo/}"
    else
        use_sudo=false
    fi

    # Separate the paths in the line
    IFS=':' read -r path link_path <<< "$line"

    path=$(echo "$path" | envsubst)
    link_path=$(echo "$link_path" | envsubst)

    # Check the link path out so we don't clobber something
    if [ -L "$link_path" ]; then
        if [ "$(readlink "$link_path")" = "$path" ]; then
            echo "[INFO]: Symlink from '$link_path' to '$path' already exists."
        else
            echo "[ERROR]: Symlink at '$link_path' exists (supposed to point to '$path'), but points to the wrong target!"
        fi
    elif [ -e "$link_path" ]; then
        echo "[ERROR]: File already exists at '$link_path' (supposed to be a symlink pointing to '$path')!"
        exit 1
    else
        # Create the symlink (being sure to create the folder tree first)
        if $use_sudo; then
            sudo mkdir -p "$(dirname "$link_path")"
            sudo ln -s "$path" "$link_path"
        else
            mkdir -p "$(dirname "$link_path")"
            ln -s "$path" "$link_path"
        fi
    fi
done < "${ACE_SYMLINKS_CONFIG}"
