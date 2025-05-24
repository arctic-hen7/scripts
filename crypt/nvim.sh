#!/bin/bash

set -e
SELF_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

python "$SELF_DIR/file.py" "$1" "nvim -n --cmd 'set noswapfile nobackup nowritebackup noundofile' %FILE"
