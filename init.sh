#!/bin/bash
# Initialises the system by downloading necessary packages and code repos, and
# setting up symlinks. After this is called, opening a new shell should leave everything
# perfectly working.
#
# Requirements:
#   - $ACE_SYMLINKS_CONFIG: location of the symlinks config
#   - $ACE_PACKAGES_DIR: the directory where package configs can be found
#   - $ACE_REPOS_CONFIG: the path to the 'repos.toml' file
#   - $ACE_REPOS_DIR: the directory where repositories are stored
#   - $ACE_MAIN_DIR: the directory of the main repo for syncing
#   - $ACE_LIB_DIR: a working directory for package installations
#   - $ACE_MAIN_MIRROR_DIR: the bare Git repo that's a remote of the main rpeo
#   - $ACE_WING_MIRRORS_DIR: the directory containing the wing mirrors
#   - $ACE_WINGS_CONFIG_DIR: the directory containing `.conf` files for each wing

set -e

# We need to execute other scripts, which should be in the same dir
SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

# A local binaries folder will be needed for package installations
mkdir -p "$HOME/.local/bin"
mkdir -p "$ACE_LIB_DIR"

# First, install packages
python "$SELF_DIR/pkg.py" rebuild rust
source "$HOME/.cargo/env"
python "$SELF_DIR/pkg.py" rebuild
# Then, download needed code repos (including `scripts`)
python "$SELF_DIR/repos.py" get
# Then, set up symlinks
bash "$ACE_REPOS_DIR/scripts/setup_symlinks.sh"
# Finally, run a sync (this will prompt to pull from any wings that have changes)
bash "$ACE_REPOS_DIR/scripts/sync.sh"

echo "System initialised! Opening a new 'fish' shell will provide everything."
