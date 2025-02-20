#!/bin/bash
# Opens a small Alacritty window for capturing text to the inbox. This interface does
# *not* support attachments or dictation, but serves nearly all use-cases.
#
# Requirements:
#   - Alacritty
#   - (Everything `capture.sh` requires)

set -e

SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

alacritty \
    -o "window.dimensions.columns = 100" \
    -o "window.dimensions.lines = 2" \
    -o "colors.primary.background = '#ffffff'" \
    -o "colors.primary.foreground = '#000000'" \
    -e bash "$SELF_DIR/terminal_capture.sh"
