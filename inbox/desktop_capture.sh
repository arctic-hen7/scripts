#!/bin/bash
# Opens a small Alacritty window for capturing text to the inbox. This interface does
# *not* support attachments or dictation, but serves nearly all use-cases.
#
# Requirements:
#   - Alacritty
#   - (Everything `terminal_capture.py` requires)

set -e

SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

source "$ACE_MAIN_DIR/dotfiles/api_keys.sh"

alacritty \
    -o "window.dimensions.columns = 100" \
    -o "window.dimensions.lines = 2" \
    -o "colors.primary.background = '#ffffff'" \
    -o "colors.primary.foreground = '#000000'" \
    -e python "$SELF_DIR/terminal_capture.py"
