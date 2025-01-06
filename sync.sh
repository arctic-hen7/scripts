#!/bin/bash
# Requirements:
#   - $ACE_MAIN_DIR: the directory of the main repo for syncing
#   - $ACE_MAIN_MIRROR_DIR: the bare Git repo that's a remote of the main rpeo
#   - $ACE_WING_MIRRORS_DIR: the directory containing the wing mirrors
#   - $ACE_WINGS_CONFIG_DIR: the directory containing `.conf` files for each wing
#   - rclone
#   - rsync
#   - git

set -e

# Build a list of all the wings from known config files
all_wings=()
for config_file in "$ACE_WINGS_CONFIG_DIR"/*.conf; do
    if [[ "$config_file" == *".rclone.conf" ]]; then
        continue;
    fi
    # This avoids checking `*.conf` if there are no wings
    [ -e "$config_file" ] || continue

    wing_name=$(basename "$config_file" .conf)
    all_wings+=("$wing_name")
done

# Parse arguments: we push to each wing by default, and can choose to pull as well or skip entirely.
# Throughout this process, we check the existence of each wing the user defines to make sure we have
# only valid wings in these arrays.
wait_in_middle=false
only_flag=false
first_time=false
use_cloud=true
pull_wings=()
skip_wings=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --first-time)
            first_time=true
            shift
            ;;
        --only)
            only_flag=true
            shift
            ;;
        -w|--wait)
            wait_in_middle=true
            shift
            ;;
        -p|--pull-wing)
            if [[ -n "$2" ]] && [[ " ${all_wings[@]} " =~ " $2 " ]]; then
                pull_wings+=("$2")
                shift 2
            elif [[ -n "$2" ]]; then
                echo "Error: unknown wing '$2'."
                exit 1
            else
                echo "Error: '--pull-wing' requires a wing name."
                exit 1
            fi
            ;;
        -s|--skip-wing)
            if [[ -n "$2" ]] && [[ " ${all_wings[@]} " =~ " $2 " ]]; then
                skip_wings+=("$2")
                shift 2
            elif [[ -n "$2" ]]; then
                echo "Error: unknown wing '$2'."
                exit 1
            else
                echo "Error: '--skip-wing' requires a wing name."
                exit 1
            fi
            ;;
        --no-cloud)
            use_cloud=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check for overlap between `pull_wings` and `skip_wings`
for skip in "${skip_wings[@]}"; do
    for pull in "${pull_wings[@]}"; do
        if [[ "$skip" == "$pull" ]]; then
            echo "Error: wing '$skip' is in both pull and skip lists."
            exit 1
        fi
    done
done

# Compute a list of wings to push to (to avoid doing every check multiple times). Note that this
# is guaranteed to be a superset of `pull_wings`. We'll take this opportunity to check that we have
# all the `rclone` remotes we'll need too.
push_wings=()
for wing_name in "${all_wings[@]}"; do
    if [[ ! " ${skip_wings[@]} " =~ " $wing_name " ]]; then
        push_wings+=("$wing_name")
        if $use_cloud && ! rclone listremotes | grep -q "^$wing_name-crypt:"; then
            echo "Remote '$wing_name-crypt:' does not exist in rclone, please create it before continuing."
            exit 1
        fi
    fi
done

# Helper function for handling any merge issues
handle_merge_conflicts() {
    # If there is an error (including merge conflicts), check for conflicts
    if [ -n "$(git ls-files -u)" ]; then
        echo "Merge conflicts detected, please resolve them manually."
        while true; do
            read -p "Have you resolved the conflicts? (y/n): " answer
            case $answer in
                [Yy]* )
                    git add -A
                    git commit -m "sync: resolved conflicts"
                    return 0
                    ;;
                [Nn]* )
                    echo "Please resolve the conflicts before proceeding."
                    ;;
                * )
                    echo "Please answer y or n."
                    ;;
            esac
        done
    else
        echo "Error: failed to pull/merge."
        return 1
    fi
}

# If the user is saying this is their first time, make sure they know what that means!
if $first_time; then
    echo "Argument '--first-time' was set, which prevents pulling from the cloud at all. If there are any changes in the cloud that you haven't accounted for, they will be totally and irrevocably overridden."
    while true; do
        read -p "Are you sure you wish to continue without pulling from the cloud? (y/n): " answer
        case $answer in
            [Yy]* )
                break
                ;;
            [Nn]* )
                echo "Aborting..."
                exit 1
                ;;
            * )
                echo "Please answer y or n."
                ;;
        esac
    done
fi

# Only pull changes if we're using the cloud and it's not our first time (if it were, the main
# mirror would get clobbered by empty space on the cloud)
if $use_cloud && ! $first_time; then
    echo "Pulling changes from the cloud..."

    rclone sync main-crypt:main "$ACE_MAIN_MIRROR_DIR" &

    # Sync all the wings in `push_wings` down (so we can make sure there haven't been any changes if
    # we aren't specifying them in `pull_wings`)
    for wing_name in "${push_wings[@]}"; do
        rclone sync "$wing_name-crypt:wing" "$ACE_WING_MIRRORS_DIR/$wing_name" &
    done

    # Wait for all those sync jobs to finish
    wait

    # Separately sync the refs because `rclone` thinks they haven't changed
    rclone sync main-crypt:main/refs/heads "$ACE_MAIN_MIRROR_DIR/refs/heads" -I
fi

cd "$ACE_MAIN_DIR"

# If we're asserting only we have made changes, make sure that's true
if $only_flag; then
    git fetch origin
    if git log main..origin/main | grep .; then
        echo "Error: '--only' flag set, but changes have been made remotely. To override this, manually commit and force-push your changes."
        exit 1
    fi
fi

# Make sure any wings in `push_wings` but not `pull_wings` haven't had any changes made
for wing_name in "${push_wings[@]}"; do
    if [[ ! " ${pull_wings[@]} " =~ " $wing_name " ]]; then
        # If the wing doesn't exist yet, this check is pointless
        if [ -e "$ACE_WING_MIRRORS_DIR/$wing_name/.wing_state" ]; then
            # We can check for changes by computing the checksum of an archive, excluding `.wing_state`
            # because the old checksum is in there
            checksum=$(tar cf - --exclude=".wing_state" "$ACE_WING_MIRRORS_DIR/$wing_name" --sort=name | sha256sum)
            prev_checksum=$(head -n 2 "$ACE_WING_MIRRORS_DIR/$wing_name/.wing_state" | tail -n 1)

            if [[ "$prev_checksum" != "$checksum" ]]; then
                echo "Changes have been made in wing '$wing_name', but it wasn't scheduled for pulling."
                while true; do
                    read -p "Would you like to pull from '$wing_name'? (y/n): " answer
                    case $answer in
                        [Yy]* )
                            pull_wings+=("$wing_name")
                            break
                            ;;
                        [Nn]* )
                            break
                            ;;
                        * )
                            echo "Please answer y or n."
                            ;;
                    esac
                done
            fi
        else
            mkdir -p "$ACE_WING_MIRRORS_DIR/$wing_name"
        fi
    fi
done

# Commit local changes if there are any
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "sync: commit local changes"
fi

# If others might have made changes, pull from the remote and resolve conflicts
if ! $only_flag; then
    git pull origin main || {
        handle_merge_conflicts || exit 1
    }
fi

# Pull from all the wings in `pull_wings`
for wing_name in "${pull_wings[@]}"; do
    branch_name="$wing_name-pull"
    # We saved the point in the main repo at which we last pushed out to the wing, check out a new
    # branch at that point now so we're guaranteed not to overwrite any other changes
    ref=$(head -n 1 "$ACE_WING_MIRRORS_DIR/$wing_name/.wing_state")
    git checkout -b "$branch_name" "$ref"

    # Copy everything from the wing remote into the local directory, except the state file
    rsync -a --exclude=".wing_state" "$ACE_WING_MIRRORS_DIR/$wing_name/" .

    # Commit all the changes from the wing, if there are any
    if [ -n "$(git status --porcelain)" ]; then
        git add -A
        git commit -m "sync: commit local changes"
    fi

    # Now merge them in: any conflicts will be registered with respect to the point when the
    # wing's files were originally exported. We force this checkout in case Starling interferes!
    git checkout -f main
    git merge "$branch_name" || {
        handle_merge_conflicts || exit 1
    }
    git branch -d "$branch_name"
done

# The user might want to do some work between pulling and pushing
if $wait_in_middle; then
    echo
    echo "Make any changes you need, and then press enter to continue..."
    read
    # Commit local changes if there are any
    if [ -n "$(git status --porcelain)" ]; then
        git add -A
        git commit -m "sync: commit local changes"
    fi
fi

# Now push to all the wings not in `skip_wings`
for wing_name in "${push_wings[@]}"; do
    # Copy everything the wing repo wants (according to its filter) over, deleting everything else
    rm -rf "$ACE_WING_MIRRORS_DIR/$wing_name"/*
    rsync -a --delete --filter="merge $ACE_WINGS_CONFIG_DIR/$wing_name.conf" . "$ACE_WING_MIRRORS_DIR/$wing_name"
    # Save the current point in the repo so we can sync from the wing properly next time
    git rev-parse HEAD > "$ACE_WING_MIRRORS_DIR/$wing_name/.wing_state"
    # And take a checksum of the remote, excluding the state, so we can check for changes next time
    tar cf - --exclude=".wing_state" "$ACE_WING_MIRRORS_DIR/$wing_name" --sort=name | sha256sum >> "$ACE_WING_MIRRORS_DIR/$wing_name/.wing_state"
done

# Push everything to the remote
git push origin main

if $use_cloud; then
    echo "Pushing changes to the cloud..."

    rclone sync "$ACE_MAIN_MIRROR_DIR" main-crypt:main &

    # Sync all the wings in `push_wings` up
    for wing_name in "${push_wings[@]}"; do
        rclone sync "$ACE_WING_MIRRORS_DIR/$wing_name" "$wing_name-crypt:wing" &
    done

    # Wait for all those sync jobs to finish
    wait

    # Separately sync the refs because `rclone` thinks they haven't changed
    rclone sync "$ACE_MAIN_MIRROR_DIR/refs/heads" main-crypt:main/refs/heads -I
fi
