#!/bin/bash
# Creates a new GPG-encrypted file, which will be empty.

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <output-path> <recipient-key-id>"
  exit 1
fi

out="$1"
recipient="$2"

# Append .gpg if not already present
[[ "$out" == *.gpg ]] || out="${out}.gpg"

# Create empty temp in shared memory
shm=$(mktemp /dev/shm/tmp.XXXXXX)

# Encrypt and write to your destination
gpg --batch --yes --encrypt --recipient "$recipient" --output "$out" "$shm"

# Clean up
rm -f "$shm"

echo "Created new GPG-encrypted file at '$out'."
