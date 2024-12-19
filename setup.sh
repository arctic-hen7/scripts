#!/bin/bash
# Sets up a new system, creating the main and mirror directories and instantiating them to
# prepare for syncing. Apart from setting up `rclone` and the wings, this will fully prepare
# for running `sync.sh`.
#
# This script is designed to be totally self-contained, and can be separated to instantiate
# a new repo. It's intended to keep a record of how to set my system up if I want to restart,
# and to allow others to easily mimic my setup.
#
# Requirements (need to be set, but this script will create them):
#   - $ACE_MAIN_DIR: the directory of the main repo for syncing
#   - $ACE_MAIN_MIRROR_DIR: the bare Git repo that's a remote of the main rpeo
#   - $ACE_WING_MIRRORS_DIR: the directory containing the wing mirrors
#   - $ACE_WINGS_CONFIG_DIR: the directory containing `.conf` files for each wing (left for user
#     creation)
#   - git

set -e

# Set up a bare mirror
mkdir "$ACE_MAIN_MIRROR_DIR"
git init --bare "$ACE_MAIN_MIRROR_DIR"

# Create the working repo and set the bare one up as its remote
mkdir "$ACE_MAIN_DIR"
cd "$ACE_MAIN_DIR"
git init
git remote add origin "$(realpath $ACE_MAIN_MIRROR_DIR)"

# Create a dummy commit to instantiate the `main` branch in both for syncing
touch README.md
git add -A
git commit -m "setup: init"
git push origin main

# Create the dir where we'll put the wing mirrors, but we don't know what they are yet
mkdir "$ACE_WING_MIRRORS_DIR"
echo "System set up! You should create '$ACE_WINGS_CONFIG_DIR' and fill it with '.conf' files for all the wings you want to manage."
