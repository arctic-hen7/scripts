#!/bin/bash
# Runs a script from the given arguments based on a config file telling us where the scripts are.
# This takes arguments of the form `bash run.sh sudo foo bar`, and it will run the script
# `foo/bar.py` in the first of the given directories where that path makes sense. The config file
# should specify legal script extensions on its first line. When there are multiple scripts with
# the same name but different extensions, the first extension alphabetically will be executed.
# Note that execution permissions will be automatically set. When the path to a script is valid in
# multiple of the specified directories, they will be considered specified in priority order, and
# the first will be executed.
#
# This script is best aliased to a single-character in a shell like so:
# ```bash
# alias ,="bash run.sh nosudo"
# alias sudo,="bash run.sh sudo"
# ```
#
# This provides aliases for executing both privileged and unprivileged scripts. Note that the first
# argument defines that the *script* will be run with `sudo`, not this executor.
#
# Requirements:
#   - $ACE_SCRIPTS_CONFIG: location of the config file for scripts

# If the first argument is `sudo`, we'll run with `sudo` to avoid in-script prompts
use_sudo="$1"
shift # Legit shift here because we'll never need this again

# Read each line of the config file, which corresponds to a directory in which to search for
# scripts
exec 3< "$ACE_SCRIPTS_CONFIG"
counter=0
while IFS= read -r line <&3; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.* ]] && continue
    [[ -z "$line" ]] && continue
    ((counter++))

    # The first non-empty and non-comment line should have the allowed extensions
    if [ $counter -eq 1 ]; then
        # Extract extensions from the line
        if [[ $line =~ ^EXTS=(.+) ]]; then
            extensions="${BASH_REMATCH[1]}"
        else
            echo "Error: first non-empty and non-comment line of config file should be of the form 'EXTS=.ext1, .ext2, ...'."
            exit 1
        fi

        # Convert to array by removing spaces and splitting by commas
        IFS=',' read -r -a allowed_extensions <<< "${extensions// /}"

        # Remove leading dots from extensions
        for i in "${!allowed_extensions[@]}"; do
            allowed_extensions[i]="${allowed_extensions[i]:1}"  # Remove the leading dot
        done

        # Don't treat this as a script directory!
        continue
    fi

    # Store the arguments locally so we can mutate and shift, letting us get arbitrarily deep
    # before we realise we need to restart on another search directory
    args=("$@")

    # Extract the path and prefix option (form: `/path/to/dir --prefix myprefix` or 
    # `/path/to/dir --no-prefix`)
    path=$(echo "$line" | awk '{print $1}')

    # Check for prefix option
    prefix=""
    if [[ "$line" == *"--prefix"* ]]; then
        # Get the prefix value
        prefix=$(echo "$line" | awk -F"--prefix " '{print $2}' | awk '{print $1}')
    fi

    if [[ "$prefix" != "" && "$prefix" == "$1" ]]; then
        # We have a matching prefix, which is *not* the name of a script
        args=("${args[@]:1}") # `shift` on an array
    elif [[ "$prefix" != "" ]]; then
        # We have a non-matching prefix, this can't be the right directory
        continue
    fi

    # Expand environment variables in the path
    path=$(echo "$path" | envsubst)

    # If we're here, `$1` contains the name of the script to search for
    while [ $# -gt 0 ]; do
        possible_script_name="${args[0]}"
        args=("${args[@]:1}") # `shift` on an array
        # Loop through every file in the directory
        for script_file in "$path"/*; do
            if [ -f "$script_file" ]; then
                # Remove the full path and the extension
                filename=$(basename "$script_file")
                script_name="${filename%.*}"
                ext="${filename##*.}"
                # Check if this is the file we want, and if its extension is legal
                if [[ "$script_name" == "$possible_script_name" && " ${allowed_extensions[@]} " =~ " ${ext} " ]]; then
                    chmod +x "$script_file"
                    if [[ "$use_sudo" == "sudo" ]]; then
                        echo "Executing script with sudo..."
                        sudo -E "$script_file" "${args[@]}"
                    else
                        "$script_file" "${args[@]}"
                    fi
                    exec 3<&-
                    exit 0
                fi
            fi
        done

        # We haven't executed a script yet, try using the script name as a directory (e.g.
        # `bash run.sh test foo` would run `test/foo.sh`). If that doesn't exist, try the next
        # directory given by the config file.
        path="$path/$possible_script_name"
        if [ ! -d "$path" ]; then
            # This breaks out of the local `while` loop and continues the reading loop
            break;
        fi
    done
done

exec 3<&-

# If we got here, this script doesn't exist
echo "Script not found using directories to search at '$ACE_SCRIPTS_CONFIG'."
exit 1
